"""Fusión con el historial, deduplicado y puntuación."""
from __future__ import annotations

import hashlib
import statistics
from datetime import datetime, timezone

from .geo import Geocoder, haversine_km
from .immotop import RawListing, fold, norm_street


def _key_for(raw: RawListing) -> str:
    if raw.immotop_id:
        return f"immotop:{raw.immotop_id}"
    basis = f"{raw.price}|{raw.surface}|{raw.rooms}|{norm_street(raw.street) or fold(raw.zone)}"
    return "fp:" + hashlib.sha1(basis.encode()).hexdigest()[:12]


def _same_listing(raw: RawListing, rec: dict) -> bool:
    """¿Es `raw` el mismo inmueble que el registro `rec` ya conocido?"""
    if raw.immotop_id and raw.immotop_id in rec.get("immotop_ids", []):
        return True
    if raw.surface != rec.get("surface") or raw.rooms != rec.get("rooms"):
        return False
    s_new, s_old = norm_street(raw.street), rec.get("street_norm")
    if s_new and s_old:
        if s_new != s_old:
            return False
        # misma calle, misma superficie: mismo piso aunque cambie el precio (±15 %)
        old = rec.get("price") or 0
        return bool(old and raw.price and abs(raw.price - old) / old <= 0.15)
    # sin calle: solo si el precio es idéntico y la zona coincide
    return raw.price == rec.get("price") and fold(raw.zone) in [fold(z) for z in rec.get("zones", [])]


def merge(history: dict, raws: list[RawListing]) -> list[str]:
    """Incorpora anuncios al historial. Devuelve las claves que son nuevas."""
    listings: dict = history.setdefault("listings", {})
    new_keys: list[str] = []
    for raw in sorted(raws, key=lambda r: r.received_at):
        day = raw.received_at.date().isoformat()
        rec = next((r for r in listings.values() if _same_listing(raw, r)), None)
        if rec is None:
            key = _key_for(raw)
            rec = listings[key] = {
                "id": key, "source": "immotop", "title": raw.title, "titles": [raw.title],
                "kind": raw.kind, "zone": raw.zone, "zones": [raw.zone] if raw.zone else [],
                "street": raw.street, "street_norm": norm_street(raw.street), "floor": raw.floor,
                "surface": raw.surface, "rooms": raw.rooms, "baths": raw.baths,
                "price": raw.price, "price_history": [{"date": day, "price": raw.price}],
                "first_seen": day, "last_seen": day, "alert_days": [day],
                "immotop_ids": [raw.immotop_id] if raw.immotop_id else [],
                "url": raw.final_url or raw.tracking_url, "image": raw.image,
            }
            new_keys.append(key)
            continue
        # ya conocido: actualizar
        rec["last_seen"] = max(rec["last_seen"], day)
        if day not in rec["alert_days"]:
            rec["alert_days"].append(day)
        if raw.title not in rec["titles"]:
            rec["titles"].append(raw.title)
        if raw.zone and raw.zone not in rec["zones"]:
            rec["zones"].append(raw.zone)
        if raw.immotop_id and raw.immotop_id not in rec["immotop_ids"]:
            rec["immotop_ids"].append(raw.immotop_id)
        if raw.price and raw.price != rec["price"]:
            rec["price_history"].append({"date": day, "price": raw.price})
            rec["price"] = raw.price
        if raw.street and not rec.get("street"):
            rec["street"], rec["street_norm"] = raw.street, norm_street(raw.street)
        if raw.final_url:
            rec["url"] = raw.final_url
        elif raw.tracking_url and day >= rec["last_seen"]:
            rec["url"] = raw.tracking_url  # el enlace más reciente es el que menos caduca
        rec["image"] = rec.get("image") or raw.image
        if rec.get("floor") is None and raw.floor is not None:
            rec["floor"] = raw.floor
    return new_keys


def _clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


def score_all(history: dict, cfg: dict, geocoder: Geocoder, today: datetime,
              new_keys: set[str]) -> list[dict]:
    search, sc, work = cfg["search"], cfg["scoring"], cfg["work"]
    work_pt = (work["lat"], work["lon"])
    refs = {fold(k): v for k, v in (sc.get("reference_eur_m2") or {}).items()}
    kw = {fold(k): v for k, v in (sc.get("keywords") or {}).items()}
    w = sc["weights"]
    wsum = sum(w.values()) or 1

    visible = []
    for rec in history.get("listings", {}).values():
        if not rec.get("price") or not rec.get("surface"):
            continue
        if rec["price"] > search["max_price"] or rec["price"] < search.get("min_price", 0) or rec["surface"] < search.get("min_surface", 0):
            continue
        if rec.get("rooms") is not None and rec["rooms"] < search.get("min_rooms", 0):
            continue
        age = (today.date() - datetime.fromisoformat(rec["first_seen"]).date()).days
        if age > search.get("max_age_days", 9999):
            continue
        visible.append((rec, age))

    eur_m2_all = [r["price"] / r["surface"] for r, _ in visible]
    median = statistics.median(eur_m2_all) if eur_m2_all else None

    out = []
    for rec, age in visible:
        if "lat" not in rec or rec.get("geo_precision") == "desconocida":
            pt, prec = geocoder.locate(rec.get("street"), rec.get("zone"))
            rec["lat"], rec["lon"] = (pt if pt else (None, None))
            rec["geo_precision"] = prec
        km = (round(haversine_km((rec["lat"], rec["lon"]), work_pt), 1)
              if rec.get("lat") is not None else None)

        eur_m2 = rec["price"] / rec["surface"]
        ref = refs.get(fold(rec.get("zone"))) or median
        ref_kind = "zona" if fold(rec.get("zone")) in refs else "mediana"

        value = _clamp(50 + 250 * (ref - eur_m2) / ref) if ref else 50
        size = _clamp(100 * rec["surface"] / sc["ideal_surface"])
        commute = _clamp(100 * (1 - km / sc["max_commute_km"])) if km is not None else 50

        text = fold(" ".join(rec.get("titles", [rec["title"]])))
        extras, reasons = 50.0, []
        for word, pts in kw.items():
            if word in text:
                extras += pts
                reasons.append(f"{word} {'+' if pts > 0 else ''}{pts}")
        floor = rec.get("floor")
        if floor is not None and floor >= 2:
            extras += 5
            reasons.append("planta alta +5")
        prices = [p["price"] for p in rec["price_history"] if p["price"]]
        drop = (prices[0] - prices[-1]) / prices[0] if len(prices) > 1 and prices[0] else 0
        if drop > 0:
            bonus = min(25, round(drop * 250))
            extras += bonus
            reasons.append(f"bajada de precio +{bonus}")
        extras = _clamp(extras)

        total = (w["value"] * value + w["size"] * size + w["commute"] * commute + w["extras"] * extras) / wsum

        badges = []
        is_new = age <= 1 or (rec["id"] in new_keys and not history.get("_backfill"))
        if is_new:
            badges.append("nuevo")
        if drop > 0:
            badges.append("bajada")
        if len(rec["alert_days"]) >= 2:
            badges.append("reanunciado")
        if len(rec["titles"]) >= 2 or len(rec["zones"]) >= 2:
            badges.append("duplicado")

        out.append({
            "id": rec["id"], "title": rec["title"], "titles": rec["titles"], "kind": rec.get("kind"),
            "zone": rec.get("zone"), "zones": rec["zones"], "street": rec.get("street"),
            "floor": floor, "surface": rec["surface"], "rooms": rec.get("rooms"), "baths": rec.get("baths"),
            "price": rec["price"], "price_history": rec["price_history"],
            "eur_m2": round(eur_m2), "eur_m2_ref": round(ref) if ref else None, "ref_kind": ref_kind,
            "first_seen": rec["first_seen"], "last_seen": rec["last_seen"], "days_listed": age,
            "alert_count": len(rec["alert_days"]), "url": rec.get("url"), "image": rec.get("image"),
            "lat": rec.get("lat"), "lon": rec.get("lon"), "geo_precision": rec.get("geo_precision"),
            "km_to_work": km, "is_new": is_new, "badges": badges,
            "score": round(total), "score_parts": {
                "value": round(value), "size": round(size), "commute": round(commute), "extras": round(extras),
            }, "extras_reasons": reasons,
        })
    out.sort(key=lambda x: (-x["score"], x["price"]))
    return out
