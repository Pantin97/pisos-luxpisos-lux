"""Fusión de fuentes, historial, detección de retirados y puntuación.

Un mismo piso suele aparecer en varios portales con fotos y textos distintos.
Se considera el mismo inmueble cuando coinciden dormitorios, superficie
(±1,5 %), precio (±3 %) y barrio o posición. Dos anuncios distintos de una
misma fuente nunca se fusionan, salvo que el antiguo haya desaparecido
(reanuncio).
"""
from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from .geo import Geocoder, haversine_km
from .sources.base import Listing, fold

MAJOR = {"athome", "immotop"}
SOURCE_LABEL = {"athome": "athome", "wortimmo": "Wortimmo", "trovit": "Trovit", "immotop": "Immotop"}


def _today(dt: datetime) -> str:
    return dt.date().isoformat()


def _zone_ok(l: Listing, rec: dict) -> bool:
    z_new, z_old = fold(l.zone), [fold(z) for z in rec.get("zones", [])]
    if not z_new or z_new == "luxembourg" or not z_old or "luxembourg" in z_old or z_new in z_old:
        return True
    if l.street and rec.get("street") and fold(l.street) == fold(rec["street"]):
        return True
    if l.lat and rec.get("lat") and rec.get("geo_precision") == "exacta":
        return haversine_km((l.lat, l.lon), (rec["lat"], rec["lon"])) < 1.2
    return False


def _match(l: Listing, rec: dict) -> float | None:
    """None si no es el mismo piso; si lo es, una distancia (menor = mejor)."""
    refs = rec.get("refs", {})
    if l.source_id and l.source_id in refs.get(l.source, []):
        return -1.0
    if l.source_id and refs.get(l.source):
        gone = rec.get("gone", {})
        if l.source not in gone:
            return None  # otro anuncio vivo de la misma fuente: piso distinto
    if not (l.surface and rec.get("surface") and l.price and rec.get("price")):
        return None
    if l.rooms is not None and rec.get("rooms") is not None and l.rooms != rec["rooms"]:
        return None
    ds = abs(l.surface - rec["surface"]) / rec["surface"]
    if abs(l.surface - rec["surface"]) > max(1.0, 0.015 * rec["surface"]):
        return None
    dp = abs(l.price - rec["price"]) / rec["price"]
    if dp > 0.03:
        return None
    # precio y superficie casi idénticos (p. ej. 1 047 740 € y 77,07 m²) identifican el piso
    # aunque cada portal lo sitúe en un barrio vecino distinto
    if not (dp == 0 and ds < 0.005) and not _zone_ok(l, rec):
        return None
    return ds + dp


def _new_key(l: Listing) -> str:
    if l.source_id:
        return f"{l.source}:{l.source_id}"
    basis = f"{l.source}|{l.price}|{l.surface}|{l.rooms}|{fold(l.zone)}|{fold(l.street)}"
    return "fp:" + hashlib.sha1(basis.encode()).hexdigest()[:12]


def ingest(history: dict, listings: list[Listing], now: datetime, alert_source: bool = False,
           backfill: bool = False) -> list[str]:
    """Mete los anuncios en el historial. Devuelve las claves de pisos nuevos."""
    recs: dict = history.setdefault("listings", {})
    day = _today(now)
    buckets: dict = defaultdict(list)
    for r in recs.values():
        buckets[r.get("rooms")].append(r)
    new_keys: list[str] = []

    for l in sorted(listings, key=lambda x: (x.seen_at, x.source)):
        day_l = _today(l.seen_at) if alert_source else day
        cands = buckets.get(l.rooms, []) + (buckets.get(None, []) if l.rooms is not None else
                                            [r for v in buckets.values() for r in v])
        best, best_d = None, None
        for r in cands:
            d = _match(l, r)
            if d is not None and (best_d is None or d < best_d):
                best, best_d = r, d
        if best is None:
            key = _new_key(l)
            while key in recs:
                key += "+"
            best = recs[key] = {
                "id": key, "title": l.title, "kind": l.kind, "zone": l.zone, "zones": [],
                "street": l.street, "floor": l.floor, "surface": l.surface, "rooms": l.rooms,
                "baths": l.baths, "price": l.price, "price_history": [{"date": day_l, "price": l.price}],
                "first_seen": day_l, "last_seen": day_l, "refs": {}, "urls": {}, "vias": [],
                "agencies": [], "agency_sites": [], "photos": [], "features": {},
                "new_build": l.new_build, "description": l.description, "src_seen": {}, "gone": {},
                "alert_days": [], "relisted": 0, "backfill": backfill,
            }
            buckets[l.rooms].append(best)
            new_keys.append(key)
        _update(best, l, day_l, alert_source)
    return new_keys


def _update(rec: dict, l: Listing, day: str, alert_source: bool) -> None:
    refs = rec.setdefault("refs", {})
    ids = refs.setdefault(l.source, [])
    if l.source_id and l.source_id not in ids:
        if ids and l.source in rec.get("gone", {}):
            rec["relisted"] = rec.get("relisted", 0) + 1
        ids.append(l.source_id)
    rec.setdefault("gone", {}).pop(l.source, None)
    rec.setdefault("src_seen", {})[l.source] = day
    rec["last_seen"] = max(rec["last_seen"], day)
    if alert_source and day not in rec.setdefault("alert_days", []):
        rec["alert_days"].append(day)
    if l.url:
        rec.setdefault("urls", {})[l.source] = l.url
    if l.zone and l.zone not in rec["zones"]:
        rec["zones"].append(l.zone)
    if l.zone and (not rec.get("zone") or rec["zone"] == "Luxembourg"):
        rec["zone"] = l.zone
    for attr, key in ((l.via, "vias"), (l.agency, "agencies"), (l.agency_site, "agency_sites")):
        if attr and attr not in rec.setdefault(key, []):
            rec[key].append(attr)
    if l.price and l.price != rec.get("price"):
        rec["price_history"].append({"date": day, "price": l.price})
        rec["price"] = l.price
    # el dato más rico gana: athome trae coordenadas exactas, fotos y características
    if l.lat and (rec.get("geo_precision") != "exacta"):
        rec["lat"], rec["lon"], rec["geo_precision"] = l.lat, l.lon, "exacta"
    if l.photos and (l.source == "athome" or len(l.photos) > len(rec.get("photos", []))):
        rec["photos"] = l.photos[:6]
    for k, v in (l.features or {}).items():
        if v:
            rec.setdefault("features", {})[k] = True
    for k in ("floor", "baths", "street", "description", "kind"):
        if rec.get(k) in (None, "") and getattr(l, k):
            rec[k] = getattr(l, k)
    if l.source == "athome" or not rec.get("title"):
        rec["title"] = l.title
    rec["new_build"] = rec.get("new_build") or l.new_build


def mark_gone(history: dict, source: str, now: datetime) -> int:
    """Tras recorrer completa una fuente: lo que no se vio hoy ha sido retirado de ella."""
    day = _today(now)
    n = 0
    for rec in history.get("listings", {}).values():
        if source in rec.get("refs", {}) and rec.get("src_seen", {}).get(source, "") < day:
            if source not in rec.setdefault("gone", {}):
                rec["gone"][source] = day
                n += 1
    return n


def is_active(rec: dict) -> bool:
    scanned = [s for s in rec.get("refs", {}) if s != "immotop"]
    if not scanned:
        return True  # solo visto en emails: no sabemos si sigue publicado
    return any(s not in rec.get("gone", {}) for s in scanned)


# ───────────────────────── puntuación ─────────────────────────

ENERGY_PTS = {"A": 12, "B": 8, "C": 4, "D": 0, "E": -4, "F": -8, "G": -12, "H": -12, "I": -12}
NEGOTIABLE_DAYS = 120
DETAIL_KEYS = ("energy_class", "insulation_class", "construction_year", "renovation_year", "charges_month",
               "heating", "lift", "balcony_m2", "terrace_m2", "garden_m2", "parking", "cellar",
               "listed_since", "under_offer", "exclusive_mandate", "virtual_visit")


def _clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


FEATURE_PTS = {"terrace": ("terraza", 12), "balcony": ("balcón", 7), "garden": ("jardín", 10),
               "parking": ("parking", 6), "elevator": ("ascensor", 3)}
FEATURE_WORDS = {"terrace": ("terrasse", "terrace"), "balcony": ("balcon", "loggia"),
                 "garden": ("jardin", "garden"), "parking": ("parking", "garage", "emplacement"),
                 "elevator": ("ascenseur", "elevator")}


def score_all(history: dict, cfg: dict, geocoder: Geocoder, now: datetime, new_keys: set[str],
              backfill: bool = False, exclusive_trusted: bool = True) -> list[dict]:
    search, sc, work = cfg["search"], cfg["scoring"], cfg["work"]
    work_pt = (work["lat"], work["lon"])
    refs_cfg = {fold(k): v for k, v in (sc.get("reference_eur_m2") or {}).items()}
    kw = {fold(k): v for k, v in (sc.get("keywords") or {}).items()}
    w = sc["weights"]
    wsum = sum(w.values()) or 1
    today = now.date()

    visible = []
    for rec in history.get("listings", {}).values():
        if not rec.get("price") or not rec.get("surface"):
            continue
        if not (search.get("min_price", 0) <= rec["price"] <= search["max_price"]):
            continue
        if rec["surface"] < search.get("min_surface", 0):
            continue
        if rec.get("rooms") is not None and rec["rooms"] < search.get("min_rooms", 0):
            continue
        active = is_active(rec)
        last = date.fromisoformat(rec["last_seen"])
        if not active and (today - max([date.fromisoformat(d) for d in rec["gone"].values()] or [last])).days > 21:
            continue
        if (today - last).days > search.get("max_age_days", 9999):
            continue
        visible.append((rec, active))

    # referencias de €/m²: mediana del barrio si hay muestra suficiente, si no la general
    by_zone: dict = defaultdict(list)
    for rec, active in visible:
        if active:
            by_zone[fold(rec.get("zone"))].append(rec["price"] / rec["surface"])
    all_m2 = [v for vs in by_zone.values() for v in vs]
    median_all = statistics.median(all_m2) if all_m2 else None
    zone_ref = {z: statistics.median(vs) for z, vs in by_zone.items() if len(vs) >= 6}

    out = []
    for rec, active in visible:
        if rec.get("lat") is None:
            pt, prec = geocoder.locate(rec.get("street"), rec.get("zone"))
            rec["lat"], rec["lon"] = pt if pt else (None, None)
            rec["geo_precision"] = prec
        km = round(haversine_km((rec["lat"], rec["lon"]), work_pt), 1) if rec.get("lat") is not None else None

        eur_m2 = rec["price"] / rec["surface"]
        z = fold(rec.get("zone"))
        if z in refs_cfg:
            ref, ref_kind = refs_cfg[z], "config"
        elif z in zone_ref:
            ref, ref_kind = zone_ref[z], "barrio"
        else:
            ref, ref_kind = median_all, "ciudad"

        value = _clamp(50 + 250 * (ref - eur_m2) / ref) if ref else 50
        size = _clamp(100 * rec["surface"] / sc["ideal_surface"])
        commute = _clamp(100 * (1 - km / sc["max_commute_km"])) if km is not None else 50

        text = fold(" ".join([rec.get("title") or "", rec.get("description") or ""]))
        extras, reasons = 50.0, []
        for feat, (label, pts) in FEATURE_PTS.items():
            if rec.get("features", {}).get(feat) or any(wd in text for wd in FEATURE_WORDS[feat]):
                extras += pts
                reasons.append(f"{label} +{pts}")
        for word, pts in kw.items():
            if word in text and not any(word in ws for ws in FEATURE_WORDS.values()):
                extras += pts
                reasons.append(f"{word} {'+' if pts > 0 else ''}{pts}")
        if (rec.get("floor") or 0) >= 2:
            extras += 5
            reasons.append("planta alta +5")
        det = rec.get("details") or {}
        if (ec := det.get("energy_class")):
            pts = ENERGY_PTS.get(ec, 0)
            if pts:
                extras += pts
                reasons.append(f"clase energética {ec} {'+' if pts > 0 else ''}{pts}")
        if det.get("cellar"):
            extras += 2
            reasons.append("trastero +2")
        prices = [p["price"] for p in rec["price_history"] if p["price"]]
        drop = (max(prices) - prices[-1]) / max(prices) if len(prices) > 1 else 0
        if drop > 0:
            bonus = min(25, round(drop * 250))
            extras += bonus
            reasons.append(f"bajada de precio +{bonus}")
        extras = _clamp(extras)
        total = (w["value"] * value + w["size"] * size + w["commute"] * commute + w["extras"] * extras) / wsum

        sources = sorted(rec.get("refs", {}))
        age = (today - date.fromisoformat(rec["first_seen"])).days
        is_new = not rec.get("backfill") and age <= 1
        badges = []
        if is_new:
            badges.append("nuevo")
        if drop > 0:
            badges.append("bajada")
        if rec.get("relisted") or len(rec.get("alert_days", [])) >= 3:
            badges.append("reanunciado")
        if len(sources) >= 2:
            badges.append("multi")
        only = None
        if exclusive_trusted and not (set(sources) & MAJOR) and not any(fold(v) in ("immotop", "athome") for v in rec.get("vias", [])):
            only = rec.get("vias", [None])[0] if rec.get("vias") else SOURCE_LABEL.get(sources[0], sources[0])
            badges.append("exclusivo")
        if rec.get("new_build"):
            badges.append("obra nueva")
        if not active:
            badges.append("retirado")
        listed = det.get("listed_since")
        on_market = (today - date.fromisoformat(listed)).days if listed else age
        if on_market >= NEGOTIABLE_DAYS:
            badges.append("negociable")
        if det.get("under_offer"):
            badges.append("compromiso")
        discount = (ref - eur_m2) / ref if ref else 0

        out.append({
            "id": rec["id"], "title": rec.get("title"), "kind": rec.get("kind"), "zone": rec.get("zone"),
            "street": rec.get("street"), "floor": rec.get("floor"), "surface": rec["surface"],
            "rooms": rec.get("rooms"), "baths": rec.get("baths"), "price": rec["price"],
            "price_history": rec["price_history"][-6:], "eur_m2": round(eur_m2),
            "eur_m2_ref": round(ref) if ref else None, "ref_kind": ref_kind,
            "first_seen": rec["first_seen"], "last_seen": rec["last_seen"], "days_listed": age,
            "sources": [{"name": SOURCE_LABEL.get(s, s), "key": s, "url": rec.get("urls", {}).get(s)} for s in sources],
            "vias": rec.get("vias", []), "only_on": only, "agencies": rec.get("agencies", [])[:3],
            "photos": rec.get("photos", [])[:8 if rec.get("details") else 5],
            "description": (rec.get("description") or "")[:700 if rec.get("details") else 280],
            "lat": rec.get("lat"), "lon": rec.get("lon"), "geo_precision": rec.get("geo_precision"),
            "km_to_work": km, "is_new": is_new, "active": active, "badges": badges,
            "features": [FEATURE_PTS[f][0] for f in FEATURE_PTS if rec.get("features", {}).get(f)],
            "score": round(total), "score_parts": {"value": round(value), "size": round(size),
                                                    "commute": round(commute), "extras": round(extras)},
            "extras_reasons": reasons, "days_on_market": on_market,
            "discount": round(discount, 3),
            "details": {k: det.get(k) for k in DETAIL_KEYS if det.get(k) not in (None, False, [], "")} or None,
        })
    out.sort(key=lambda x: (not x["active"], -x["score"], x["price"]))
    return out


def zone_stats(ranked: list[dict]) -> list[dict]:
    by: dict = defaultdict(list)
    for x in ranked:
        if x["active"]:
            by[x["zone"] or "?"].append(x["eur_m2"])
    rows = [{"zone": z, "n": len(v), "median_eur_m2": round(statistics.median(v))} for z, v in by.items()]
    return sorted(rows, key=lambda r: -r["n"])
