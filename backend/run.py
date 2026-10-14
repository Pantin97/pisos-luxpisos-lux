"""Ejecución diaria.

    python -m backend.run                       # lee Gmail por IMAP (GitHub Actions)
    python -m backend.run --html-dir carpeta    # lee alertas guardadas en ficheros
    python -m backend.run --no-notify           # sin notificaciones

Variables de entorno (secretos de GitHub):
    GMAIL_USER, GMAIL_APP_PASSWORD          acceso IMAP de solo lectura
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY     claves de Web Push (tools/gen_vapid.py)
    VAPID_SUBJECT                           mailto: de contacto para VAPID
    PUSH_SUBSCRIPTIONS                      JSON copiado desde los ajustes de la app
    NTFY_TOPIC                              opcional, aviso también por ntfy.sh
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import immotop, push
from .geo import Geocoder
from .pipeline import merge, score_all

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fmt_eur(n: int) -> str:
    return f"{n:,.0f} €".replace(",", " ")


def notify(new_items: list[dict], cfg: dict, app_url: str | None) -> None:
    ncfg = cfg.get("notify", {})
    items = [x for x in new_items if x["score"] >= ncfg.get("min_score", 0)]
    if not items:
        print("· Sin anuncios nuevos que notificar")
        return
    best = items[0]
    title = f"{len(items)} piso{'s' if len(items) > 1 else ''} nuevo{'s' if len(items) > 1 else ''}"
    body = (f"Mejor: {best['zone']} · {best['surface']:.0f} m² · {fmt_eur(best['price'])} "
            f"· puntuación {best['score']}")
    payload = {"title": title, "body": body, "url": "./?tab=hoy", "tag": "pisos-diario"}

    subs = push.parse_subscriptions(os.environ.get("PUSH_SUBSCRIPTIONS"))
    priv = os.environ.get("VAPID_PRIVATE_KEY")
    subject = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")
    for sub in subs:
        if not priv:
            print("! Falta VAPID_PRIVATE_KEY, no se envía push")
            break
        try:
            code = push.send(sub, payload, priv, subject)
            msg = {201: "enviado", 404: "suscripción caducada (vuelve a activarla en la app)",
                   410: "suscripción caducada (vuelve a activarla en la app)"}.get(code, f"HTTP {code}")
            print(f"· Push: {msg}")
        except Exception as e:  # noqa: BLE001
            print(f"! Push falló: {e}")

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        try:
            import requests
            requests.post(f"https://ntfy.sh/{topic}", data=body.encode(), timeout=10,
                          headers={"Title": title, "Click": app_url or "", "Tags": "house"})
            print("· ntfy: enviado")
        except Exception as e:  # noqa: BLE001
            print(f"! ntfy falló: {e}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-dir", help="carpeta con alertas .html/.eml en vez de IMAP")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--today", help="fecha simulada YYYY-MM-DD (pruebas)")
    ap.add_argument("--out", default=str(DOCS / "listings.json"))
    args = ap.parse_args(argv)

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    src = cfg["sources"]["immotop_email"]
    history_path = DATA / "history.json"
    history = load_json(history_path, {"processed": [], "listings": {}})
    first_run = not history.get("listings")
    history["_backfill"] = first_run
    today = (datetime.fromisoformat(args.today).replace(tzinfo=timezone.utc)
             if args.today else datetime.now(timezone.utc))
    processed = set(history.get("processed", []))

    # 1 · leer alertas
    if args.html_dir:
        messages = immotop.load_html_dir(args.html_dir, processed)
    else:
        user, pwd = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
        if not (user and pwd):
            print("! Faltan GMAIL_USER / GMAIL_APP_PASSWORD")
            return 1
        since = today - timedelta(days=src.get("lookback_days", 120) if first_run else 7)
        messages = immotop.fetch_imap(user, pwd, src["sender"], since, processed)
    print(f"· {len(messages)} alerta(s) nueva(s)")

    raws = []
    for mid, when, html in messages:
        items = immotop.parse_alert_html(html, when, mid)
        if not items:
            print(f"! {mid}: no se reconoció ningún anuncio (¿ha cambiado el formato del email?)")
        raws.extend(items)
        processed.add(mid)
    print(f"· {len(raws)} anuncio(s) extraído(s)")

    # 2 · resolver enlaces de seguimiento → ID real del anuncio
    if src.get("resolve_links") and not args.html_dir:
        for r in raws:
            r.final_url, r.immotop_id = immotop.resolve_link(r.tracking_url)

    # 3 · fusionar, geolocalizar, puntuar
    new_keys = merge(history, raws)
    geocoder = Geocoder(DATA / "geocache.json", cfg["sources"].get("geocoding", {}).get("use_nominatim", True))
    ranked = score_all(history, cfg, geocoder, today, set(new_keys))
    geocoder.save()

    history["processed"] = sorted(processed)
    history["last_run"] = today.isoformat()
    history.pop("_backfill", None)
    DATA.mkdir(exist_ok=True)
    history_path.write_text(json.dumps(history, indent=1, ensure_ascii=False), encoding="utf-8")

    eur_m2 = [x["eur_m2"] for x in ranked]
    output = {
        "generated_at": today.isoformat(timespec="minutes"),
        "search": cfg["search"],
        "work": cfg["work"],
        "weights": cfg["scoring"]["weights"],
        "vapid_public_key": os.environ.get("VAPID_PUBLIC_KEY"),
        "stats": {
            "count": len(ranked),
            "new_count": sum(1 for x in ranked if x["is_new"]),
            "median_eur_m2": round(statistics.median(eur_m2)) if eur_m2 else None,
        },
        "listings": ranked,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"· {len(ranked)} piso(s) en {out.name}; {len(new_keys)} nuevo(s) en esta ejecución")

    # 4 · avisar (no en la primera ejecución, que solo carga el histórico)
    if not args.no_notify and not first_run:
        fresh = [x for x in ranked if x["id"] in set(new_keys)]
        notify(fresh, cfg, os.environ.get("APP_URL"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
