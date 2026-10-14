"""Escaneo de todas las fuentes.

    python -m backend.run --mode full      # cada mañana: recorre todo y detecta retirados
    python -m backend.run --mode quick     # botón "Escanear" de la app: solo lo más reciente
    python -m backend.run --html-dir DIR   # pruebas: alertas de Immotop guardadas en ficheros

Variables de entorno (secretos de GitHub):
    GMAIL_USER, GMAIL_APP_PASSWORD          alertas de Immotop por IMAP (solo lectura)
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY     Web Push
    VAPID_SUBJECT, PUSH_SUBSCRIPTIONS
    NTFY_TOPIC                              opcional
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import push
from .geo import Geocoder
from .pipeline import ingest, mark_gone, score_all, zone_stats
from .sources import athome, immotop_email, trovit, wortimmo
from .sources.base import Fetcher, Listing, SourceResult, norm_zone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
HISTORY = DATA / "history_v2.json"
SCANNERS = {"athome": athome.scan, "wortimmo": wortimmo.scan, "trovit": trovit.scan}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fmt_eur(n: int) -> str:
    return f"{n:,.0f} €".replace(",", " ")


def immotop_alerts(cfg: dict, history: dict, now: datetime, first_run: bool, html_dir: str | None) -> SourceResult:
    res = SourceResult("immotop")
    t0 = time.time()
    processed = set(history.get("processed", []))
    try:
        if html_dir:
            messages = immotop_email.load_html_dir(html_dir, processed)
        else:
            user, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
            if not (user and pwd):
                res.error = "faltan GMAIL_USER / GMAIL_APP_PASSWORD"
                return res
            since = now - timedelta(days=cfg.get("lookback_days", 120) if first_run else 10)
            messages = immotop_email.fetch_imap(user, pwd, cfg["sender"], since, processed)
        for mid, when, html in messages:
            for r in immotop_email.parse_alert_html(html, when, mid):
                res.listings.append(Listing(
                    source="immotop", source_id=r.immotop_id, url=r.final_url or r.tracking_url,
                    title=r.title, price=r.price, surface=r.surface, rooms=r.rooms, baths=r.baths,
                    zone=norm_zone(r.zone), floor=r.floor, street=r.street,
                    kind={"Appartement": "Apartamento"}.get(r.kind or "", r.kind), seen_at=when))
            processed.add(mid)
        res.pages = len(messages)
        res.complete = True
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"[:300]
    history["processed"] = sorted(processed)
    res.seconds = time.time() - t0
    return res


def notify(fresh: list[dict], cfg: dict, app_url: str | None) -> list[str]:
    log = []
    items = [x for x in fresh if x["score"] >= cfg.get("notify", {}).get("min_score", 0)]
    if not items:
        return ["sin novedades que avisar"]
    best = items[0]
    n = len(items)
    title = f"{n} piso{'s' if n > 1 else ''} nuevo{'s' if n > 1 else ''}"
    body = f"Mejor: {best['zone']} · {best['surface']:.0f} m² · {fmt_eur(best['price'])} · {best['score']} pts"
    payload = {"title": title, "body": body, "url": "./?tab=nuevos", "tag": "pisos"}
    priv = os.environ.get("VAPID_PRIVATE_KEY")
    for sub in push.parse_subscriptions(os.environ.get("PUSH_SUBSCRIPTIONS")):
        if not priv:
            log.append("push: falta VAPID_PRIVATE_KEY")
            break
        try:
            code = push.send(sub, payload, priv, os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com"))
            log.append(f"push: HTTP {code}")
        except Exception as e:  # noqa: BLE001
            log.append(f"push: error {e}")
    if topic := os.environ.get("NTFY_TOPIC"):
        try:
            import requests
            requests.post(f"https://ntfy.sh/{topic}", data=body.encode(), timeout=10,
                          headers={"Title": title, "Click": app_url or "", "Tags": "house"})
            log.append("ntfy: enviado")
        except Exception as e:  # noqa: BLE001
            log.append(f"ntfy: error {e}")
    return log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["full", "quick"], default="full")
    ap.add_argument("--html-dir", help="alertas de Immotop en ficheros en vez de IMAP")
    ap.add_argument("--only", help="fuentes separadas por comas (pruebas)")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--out", default=str(DOCS / "listings.json"))
    args = ap.parse_args(argv)

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    src_cfg = cfg["sources"]
    now = datetime.now(timezone.utc)
    history = load_json(HISTORY, {"version": 2, "processed": [], "listings": {}, "runs": []})
    first_run = not history.get("listings")
    only = set(args.only.split(",")) if args.only else None
    fetcher = Fetcher(delay=1.5)
    results: list[SourceResult] = []
    new_keys: list[str] = []

    for name, scan in SCANNERS.items():
        if not src_cfg.get(name, {}).get("enabled") or (only and name not in only):
            continue
        res = scan(src_cfg[name], fetcher, src_cfg["pages"][args.mode][name])
        results.append(res)
        new_keys += ingest(history, res.listings, now, backfill=first_run)
        if args.mode == "full" and res.complete and not res.error and res.listings:
            mark_gone(history, name, now)
        print(f"· {name}: {len(res.listings)} anuncios, {res.pages} págs, "
              f"{'completo' if res.complete else 'parcial'}{', ERROR ' + res.error if res.error else ''}")

    if src_cfg.get("immotop_email", {}).get("enabled") and (not only or "immotop" in only):
        res = immotop_alerts(src_cfg["immotop_email"], history, now, first_run, args.html_dir)
        results.append(res)
        new_keys += ingest(history, res.listings, now, alert_source=True, backfill=first_run)
        print(f"· immotop (email): {len(res.listings)} anuncios de {res.pages} alertas"
              f"{', ERROR ' + res.error if res.error else ''}")

    # "solo en agencia" solo es fiable si athome se ha recorrido entero en las últimas 48 h
    recent_full = [r for r in history.get("runs", []) if r.get("mode") == "full"
                   and r.get("at", "") >= (now - timedelta(hours=48)).isoformat()]
    athome_full = any(s["name"] == "athome" and s["complete"] and not s["error"]
                      for r in recent_full for s in r.get("sources", []))
    athome_full = athome_full or any(r.name == "athome" and r.complete and not r.error for r in results)
    geocoder = Geocoder(DATA / "geocache.json", src_cfg.get("geocoding", {}).get("use_nominatim", True))
    ranked = score_all(history, cfg, geocoder, now, set(new_keys), backfill=first_run,
                       exclusive_trusted=athome_full)
    geocoder.save()

    run_info = {"at": now.isoformat(timespec="seconds"), "mode": args.mode, "new": len(new_keys),
                "sources": [r.stats() for r in results]}
    history["runs"] = (history.get("runs", []) + [run_info])[-30:]
    DATA.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    active = [x for x in ranked if x["active"]]
    m2 = [x["eur_m2"] for x in active]
    output = {
        "generated_at": now.isoformat(timespec="minutes"),
        "mode": args.mode,
        "search": cfg["search"], "work": cfg["work"], "weights": cfg["scoring"]["weights"],
        "vapid_public_key": os.environ.get("VAPID_PUBLIC_KEY"),
        "repo": os.environ.get("GITHUB_REPOSITORY"),
        "stats": {
            "count": len(active), "new_count": sum(1 for x in active if x["is_new"]),
            "median_eur_m2": round(statistics.median(m2)) if m2 else None,
            "multi_source": sum(1 for x in active if "multi" in x["badges"]),
            "exclusive": sum(1 for x in active if "exclusivo" in x["badges"]),
            "retired": sum(1 for x in ranked if not x["active"]),
        },
        "sources": [r.stats() for r in results],
        "zones": zone_stats(ranked)[:25],
        "listings": ranked,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"· {len(active)} pisos activos, {len(new_keys)} nuevos en esta ejecución → {out.name}")

    if not args.no_notify and not first_run:
        fresh_ids = set(new_keys)
        fresh = [x for x in ranked if x["id"] in fresh_ids and x["active"]]
        for line in notify(fresh, cfg, os.environ.get("APP_URL")):
            print("·", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
