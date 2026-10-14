"""Avisos inteligentes.

Cada ejecución compara el estado con lo ya avisado y genera eventos:
  chollo     piso nuevo o rebajado muy por debajo de la mediana del barrio
  nuevo      piso nuevo en tus barrios
  bajada     baja de precio en tus barrios o en un guardado
  retirado   un guardado ya no está publicado en ningún portal
  compromiso un guardado tiene compromiso de venta firmado
Los eventos se guardan (la app los muestra en Actividad) y se mandan en una
sola notificación por ejecución, con los chollos primero.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .sources.base import fold


def load_watch(path: Path) -> set[str]:
    """Guardados sincronizados desde la app: {"saved": {id: ts}, "removed": {id: ts}}."""
    try:
        w = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    saved, removed = w.get("saved", {}), w.get("removed", {})
    return {i for i, ts in saved.items() if ts > removed.get(i, 0)}


def _fmt(n: int) -> str:
    return f"{n:,.0f} €".replace(",", " ")


def _dropped_today(rec: dict, day: str) -> int:
    ph = [p for p in rec.get("price_history", []) if p.get("price")]
    if len(ph) >= 2 and ph[-1]["date"] == day and ph[-1]["price"] < ph[-2]["price"]:
        return ph[-2]["price"] - ph[-1]["price"]
    return 0


def compute_events(history: dict, ranked: list[dict], new_keys: set[str], cfg: dict,
                   watched: set[str], now: datetime, backfill: bool) -> list[dict]:
    if backfill:
        return []
    acfg = cfg.get("notify", {})
    zones = {fold(z) for z in (acfg.get("zones") or [])}
    deal_zones = {fold(z) for z in (acfg.get("deal_zones") or acfg.get("zones") or [])}
    deal_discount = acfg.get("deal_discount", 0.15)
    deal_score = acfg.get("deal_score", 85)
    min_score = acfg.get("min_score", 0)
    day = now.date().isoformat()
    recs = history.get("listings", {})
    notified: dict = history.setdefault("notified", {})
    in_zone = lambda r, zs: not zs or fold(r.get("zone")) in zs  # noqa: E731

    events = []

    def add(kind: str, r: dict, key: str, title: str, body: str):
        if key in notified:
            return
        notified[key] = day
        events.append({"type": kind, "id": r["id"], "at": now.isoformat(timespec="minutes"),
                       "zone": r.get("zone"), "price": r["price"], "title": title, "body": body})

    for r in ranked:
        rec = recs.get(r["id"], {})
        watched_r = r["id"] in watched
        under_offer = "compromiso" in r["badges"]
        drop = _dropped_today(rec, day)
        fresh = r["id"] in new_keys
        if r["active"] and not under_offer and (fresh or drop) and in_zone(r, deal_zones) \
                and (r.get("discount", 0) >= deal_discount or r["score"] >= deal_score):
            pct = round(r.get("discount", 0) * 100)
            add("chollo", r, f"chollo:{r['id']}:{r['price']}",
                f"Chollo en {r['zone']}: {_fmt(r['price'])}",
                f"{r['surface']:.0f} m² · {pct} % bajo la mediana del barrio · {r['score']} pts")
            continue
        if fresh and r["active"] and in_zone(r, zones) and r["score"] >= min_score:
            add("nuevo", r, f"nuevo:{r['id']}", f"Nuevo en {r['zone']}: {_fmt(r['price'])}",
                f"{r['surface']:.0f} m² · {r['rooms'] or '?'} dorm. · {r['score']} pts")
        if drop and r["active"] and (watched_r or in_zone(r, zones)):
            add("bajada", r, f"bajada:{r['id']}:{r['price']}", f"Baja {_fmt(drop)} en {r['zone']}",
                f"Ahora {_fmt(r['price'])}{' · guardado' if watched_r else ''}")
        if watched_r and not r["active"]:
            add("retirado", r, f"retirado:{r['id']}", f"Retirado: {r['zone']} {_fmt(r['price'])}",
                "Uno de tus guardados ya no aparece en ningún portal.")
        if watched_r and under_offer:
            add("compromiso", r, f"compromiso:{r['id']}", f"Con compromiso: {r['zone']} {_fmt(r['price'])}",
                "Uno de tus guardados tiene compromiso de venta.")

    # guardados que ya ni siquiera están en la lista visible (retirados hace tiempo o filtrados)
    seen = {r["id"] for r in ranked}
    for wid in watched - seen:
        rec = recs.get(wid)
        if rec and rec.get("gone") and f"retirado:{wid}" not in notified:
            notified[f"retirado:{wid}"] = day

    log = history.setdefault("events", [])
    log.extend(events)
    cutoff = (now - timedelta(days=60)).isoformat()
    history["events"] = [e for e in log if e["at"] >= cutoff][-300:]
    if len(notified) > 5000:
        keep = sorted(notified.items(), key=lambda kv: kv[1])[-4000:]
        history["notified"] = dict(keep)
    return events


ORDER = {"chollo": 0, "compromiso": 1, "retirado": 2, "bajada": 3, "nuevo": 4}
WORD = {"chollo": ("chollo", "chollos"), "nuevo": ("nuevo", "nuevos"), "bajada": ("bajada", "bajadas"),
        "retirado": ("retirado", "retirados"), "compromiso": ("con compromiso", "con compromiso")}


def compose(events: list[dict]) -> dict | None:
    """Una notificación por ejecución."""
    if not events:
        return None
    ev = sorted(events, key=lambda e: ORDER[e["type"]])
    if len(ev) == 1:
        e = ev[0]
        return {"title": e["title"], "body": e["body"], "url": f"./?id={e['id']}", "tag": e["type"]}
    counts: dict = {}
    for e in ev:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    summary = " · ".join(f"{n} {WORD[k][n > 1]}" for k, n in sorted(counts.items(), key=lambda kv: ORDER[kv[0]]))
    top = ev[0]
    title = top["title"] if top["type"] == "chollo" else f"Pisos Lux: {summary}"
    body = f"{summary}. {top['title']}" if top["type"] == "chollo" else top["title"] + " · " + top["body"]
    return {"title": title, "body": body, "url": "./?tab=actividad", "tag": "pisos"}
