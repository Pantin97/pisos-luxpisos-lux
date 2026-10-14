"""athome.lu: lee la página de resultados, que trae todos los anuncios en
`window.__INITIAL_STATE__` (precio, superficie, coordenadas, fotos, agencia…)."""
from __future__ import annotations

import json
import re
import time

from .base import Fetcher, Listing, SourceResult, clean, norm_zone, parse_int

BASE = "https://www.athome.lu"
IMG = "https://i1.static.athome.eu/images/annonces2/image_/"


def extract_state(html: str) -> dict:
    i = html.find("window.__INITIAL_STATE__")
    if i < 0:
        raise ValueError("no __INITIAL_STATE__")
    start = html.index("{", i)
    text = html[start:]
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(text)
    except json.JSONDecodeError:
        end = text.find("</script>")
        obj, _ = dec.raw_decode(re.sub(r":\s*undefined\b", ":null", text[:end]))
    return obj


def _bool(v) -> bool:
    return bool(v) and v not in ("0", "-1", "false")


def to_listing(x: dict) -> Listing | None:
    if x.get("children") or not x.get("price"):
        return None  # ficha de promoción: sus unidades aparecen como anuncios propios
    ch = x.get("characteristic") or {}
    geo = x.get("geo") or {}
    pub = x.get("publisher") or {}
    photos = [IMG + m["uri"] for m in (x.get("media") or {}).get("items", [])
              if m.get("type") == "photo" and m.get("uri")][:6]
    floor = parse_int(ch.get("floor_number") or x.get("floorNumber"))
    kind = (x.get("propertySubType") or (x.get("immotype") or {}).get("label") or "Apartment")
    kind = {"Apartment": "Apartamento", "Penthouse": "Ático", "Duplex": "Dúplex", "Studio": "Estudio",
            "Triplex": "Tríplex", "Loft": "Loft", "Ground floor apartment": "Bajo"}.get(kind, kind)
    zone = norm_zone(geo.get("cityName"))
    rooms = x.get("bedroomsCount")
    try:
        lat, lon = float(geo.get("lat")), float(geo.get("lon"))
    except (TypeError, ValueError):
        lat = lon = None
    permalink = ((x.get("meta") or {}).get("permalink") or {}).get("fr")
    return Listing(
        source="athome", source_id=str(x["id"]),
        url=BASE + permalink if permalink else f"{BASE}/id-{x['id']}.html",
        title=f"{kind} {rooms} dorm. · {zone}" if rooms else f"{kind} · {zone}",
        price=int(x["price"]), surface=float(x.get("propertySurface") or 0) or None,
        rooms=rooms, baths=x.get("bathroomsCount") or None, floor=floor,
        zone=zone, lat=lat, lon=lon, photos=photos,
        agency=clean(pub.get("name")) or None, agency_site=pub.get("website") or None,
        kind=kind, new_build=bool(x.get("isNewBuild")),
        street=clean(geo.get("streetAddress")) or None,
        description=clean(x.get("description"))[:400] or None,
        features={
            "terrace": (x.get("terraceesCount") or 0) > 0,
            "balcony": (x.get("balconiesCount") or 0) > 0,
            "elevator": _bool(x.get("hasElevator")) or _bool(ch.get("elevator")),
            "parking": (x.get("carparksCount") or 0) + (x.get("garagesCount") or 0) > 0
                       or bool(x.get("parkingsList")) or _bool(ch.get("garage_carpark")),
            "garden": _bool(x.get("hasPrivateGarden")) or _bool(ch.get("has_garden")),
        },
    )


def parse_page(html: str) -> tuple[list[Listing], int | None, int | None]:
    state = extract_state(html)
    s = state["search"]
    items = [to_listing(x) for x in s.get("list") or []]
    pages = (s.get("paginator") or {}).get("totalPages")
    return [i for i in items if i], s.get("total"), pages


def scan(cfg: dict, fetcher: Fetcher, max_pages: int) -> SourceResult:
    res = SourceResult("athome")
    t0 = time.time()
    seen = set()
    try:
        page, pages = 1, 1
        while page <= min(pages or 1, max_pages):
            url = cfg["url"] + ("&" if "?" in cfg["url"] else "?") + f"page={page}"
            items, total, pages = parse_page(fetcher.get(url).text)
            res.total_reported = total
            res.pages = page
            fresh = [i for i in items if i.source_id not in seen]
            if not items:
                break
            seen.update(i.source_id for i in fresh)
            res.listings.extend(fresh)
            page += 1
        res.complete = res.pages >= (pages or 1)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"[:300]
    res.seconds = time.time() - t0
    return res
