"""Ficha completa de los pisos candidatos.

La lista de resultados no trae clase energética, gastos ni año. Para los pisos
que importan (barrios elegidos, guardados y los mejor puntuados) se descarga
la ficha una vez y se refresca cada pocos días o si cambia el precio.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime

from bs4 import BeautifulSoup

from .sources.base import Fetcher, clean, fold, parse_int

ENERGY_ORDER = "ABCDEFGHI"


def _json_after(html: str, marker: str) -> dict:
    i = html.find(marker)
    if i < 0:
        raise ValueError(f"no {marker}")
    start = html.index("{", i)
    obj, _ = json.JSONDecoder().raw_decode(html[start:])
    return obj


def _cls(v) -> str | None:
    v = (v or "").strip().upper()
    return v if len(v) == 1 and v in ENERGY_ORDER else None


def parse_athome_detail(html: str) -> dict:
    app = _json_after(html, "window.AT_HOME_APP")
    lst = app["preloadedState"]["listing"]
    x, old = lst["listing"], lst.get("listingOld") or {}
    ch = x.get("characteristic") or {}
    en = x.get("energy") or {}
    addr = x.get("address") or {}
    heating = [lbl for key, lbl in (("hasGasHeating", "gas"), ("hasPumpHeating", "bomba de calor"),
                                    ("hasGeoThermalHeating", "geotermia"), ("hasOilHeating", "gasóleo"),
                                    ("hasElectricHeating", "eléctrica"), ("hasPelletsHeating", "pellets"),
                                    ("hasFloorHeating", "suelo radiante")) if en.get(key)]
    created = x.get("createdAt") or ""
    listed = f"{created[:4]}-{created[4:6]}-{created[6:8]}" if re.match(r"\d{8}", created) else None
    charges, freq = x.get("charges") or 0, x.get("chargesPaymentFrequency") or "monthly"
    parking = sum(int(ch.get(k) or 0) for k in ("garages", "indoorParking", "outdoorParking"))
    photos = [("https://i1.static.athome.eu/images/annonces2/image_/" + p) if isinstance(p, str) and p.startswith("/") else p
              for p in ((x.get("media") or {}).get("photos") or []) if isinstance(p, str)]
    street = clean(addr.get("street"))
    return {
        "energy_class": _cls((en.get("energyEfficiency") or {}).get("energyClass")) or _cls(old.get("energyClass")),
        "insulation_class": _cls((en.get("thermalInsulation") or {}).get("insulationClass")) or _cls(old.get("thermalInsulationClass")),
        "construction_year": ch.get("constructionYear") or None,
        "renovation_year": ch.get("renovationYear") or None,
        "charges_month": round(charges / 12) if freq == "yearly" and charges else (charges or None),
        "heating": heating,
        "lift": bool(ch.get("hasLift")),
        "balcony_m2": ch.get("balconySurface") or (1 if ch.get("hasBalcony") else None),
        "terrace_m2": ch.get("terraceSurface") or (1 if ch.get("hasTerrace") else None),
        "garden_m2": ch.get("gardenSurface") or (1 if ch.get("hasGarden") else None),
        "parking": parking or None,
        "cellar": bool(ch.get("hasCellar") or ch.get("basement")),
        "floor": addr.get("floor"),
        "street": street if len(street) > 3 and street.upper() not in ("NC", "N.C.") else None,
        "listed_since": listed,
        "under_offer": bool(old.get("underSalesAgreement")) or x.get("status") not in (None, "active"),
        "exclusive_mandate": bool(x.get("hasExclusiveMandate")),
        "virtual_visit": (x.get("media") or {}).get("virtualVisit") or None,
        "photos": photos[:12],
        "description": clean(x.get("description"))[:900] or None,
    }


def parse_generic_detail(html: str) -> dict:
    """Ficha de wortimmo u otra web: extracción por texto, sin estructura garantizada."""
    text = clean(BeautifulSoup(html, "html.parser").get_text(" "))
    t = fold(text)
    out: dict = {}
    if m := re.search(r"(?:classe|classe de performance) energetique\s*:?\s*([a-i])\b", t):
        out["energy_class"] = m.group(1).upper()
    if m := re.search(r"(?:isolation thermique|classe d'isolation thermique|isolation)\s*:?\s*([a-i])\b", t):
        out["insulation_class"] = m.group(1).upper()
    if m := re.search(r"annee de construction\s*:?\s*(1[89]\d\d|20\d\d)", t):
        out["construction_year"] = int(m.group(1))
    if m := re.search(r"charges[^0-9€]{0,25}([\d .]{2,7})\s*€", t):
        out["charges_month"] = parse_int(m.group(1))
    if m := re.search(r"terrasse[^0-9]{0,15}(\d{1,3}(?:[.,]\d+)?)\s*m", t):
        out["terrace_m2"] = float(m.group(1).replace(",", "."))
    if m := re.search(r"balcon[^0-9]{0,15}(\d{1,3}(?:[.,]\d+)?)\s*m", t):
        out["balcony_m2"] = float(m.group(1).replace(",", "."))
    out["lift"] = "ascenseur" in t
    out["cellar"] = bool(re.search(r"\bcave\b", t))
    if re.search(r"(garage|emplacement|parking)", t):
        out["parking"] = 1
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def candidates(history: dict, cfg: dict, watched: set[str], ranked: list[dict]) -> list[dict]:
    dcfg = cfg.get("details", {})
    zones = {fold(z) for z in (dcfg.get("zones") or cfg.get("notify", {}).get("zones") or [])}
    recs = history.get("listings", {})
    picked: dict = {}
    for r in ranked:
        rec = recs.get(r["id"])
        if not rec or not r["active"]:
            continue
        if r["id"] in watched or (zones and fold(r.get("zone")) in zones):
            picked[r["id"]] = rec
    for r in ranked[: dcfg.get("top_n", 25)]:
        if r["active"] and r["id"] in recs:
            picked.setdefault(r["id"], recs[r["id"]])
    return list(picked.values())


def needs_refresh(rec: dict, today: date, max_age_days: int) -> bool:
    d = rec.get("details") or {}
    if not d.get("fetched"):
        return True
    if d.get("price") != rec.get("price"):
        return True
    return (today - date.fromisoformat(d["fetched"])).days >= max_age_days


def enrich(history: dict, cfg: dict, watched: set[str], ranked: list[dict], fetcher: Fetcher,
           now: datetime, budget: int) -> dict:
    """Descarga fichas hasta `budget` páginas. Devuelve estadísticas."""
    today = now.date()
    stats = {"name": "fichas", "items": 0, "pages": 0, "total_reported": None, "complete": True,
             "error": None, "seconds": 0.0}
    t0 = time.time()
    todo = [r for r in candidates(history, cfg, watched, ranked)
            if needs_refresh(r, today, cfg.get("details", {}).get("refresh_days", 7))]
    stats["total_reported"] = len(todo)
    for rec in todo[:budget]:
        urls = rec.get("urls", {})
        try:
            if urls.get("athome"):
                d = parse_athome_detail(fetcher.get(urls["athome"]).text)
            elif urls.get("wortimmo"):
                d = parse_generic_detail(fetcher.get(urls["wortimmo"]).text)
            else:
                continue
        except Exception as e:  # noqa: BLE001
            stats["error"] = f"{type(e).__name__}: {e}"[:200]
            continue
        stats["pages"] += 1
        d["fetched"] = today.isoformat()
        d["price"] = rec.get("price")
        rec["details"] = d
        # la ficha manda sobre la lista en los datos que comparten
        if d.get("photos") and len(d["photos"]) > len(rec.get("photos", [])):
            rec["photos"] = d["photos"]
        if d.get("street") and not rec.get("street"):
            rec["street"] = d["street"]
        if d.get("floor") is not None and rec.get("floor") is None:
            rec["floor"] = d["floor"]
        if d.get("description") and len(d["description"]) > len(rec.get("description") or ""):
            rec["description"] = d["description"]
        feats = rec.setdefault("features", {})
        for k, key in (("terrace", "terrace_m2"), ("balcony", "balcony_m2"), ("garden", "garden_m2"),
                       ("parking", "parking"), ("elevator", "lift")):
            if d.get(key):
                feats[k] = True
        stats["items"] += 1
    stats["complete"] = len(todo) <= budget
    stats["seconds"] = round(time.time() - t0, 1)
    return stats
