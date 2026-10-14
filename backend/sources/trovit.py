"""Trovit: agregador que recoge anuncios de portales y webs de agencias.
Sirve también para cubrir Immotop, que bloquea las descargas desde GitHub."""
from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from .base import Fetcher, Listing, SourceResult, clean, fold, norm_zone, parse_int, parse_surface

SKIP_TYPES = {"projet", "terrain", "garage", "parking", "bureau", "commerce", "villa", "maison"}


def parse_page(html: str, city: str = "Luxembourg") -> tuple[list[Listing], int | None, int]:
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" "))
    m = re.search(r"\d+\s*-\s*\d+\s*de\s*([\d\s  .]+)", text)
    total = parse_int(m.group(1)) if m else None
    out, raw_count = [], 0
    for it in soup.select(".js-item"):
        raw_count += 1
        if city and fold(it.get("data-city")) != fold(city):
            continue
        ptype = fold(it.get("data-property-type"))
        if any(t in ptype for t in SKIP_TYPES):
            continue
        link = it.select_one("a.rd-link")
        img = it.select_one(".snippet-gallery img")
        addr = clean(it.select_one(".item-address").get_text()) if it.select_one(".item-address") else ""
        rooms_el, baths_el, size_el = (it.select_one(f".item-{k} span") for k in ("rooms", "baths", "size"))
        footer = clean(it.select_one(".snippet-content-footer").get_text(" ")) if it.select_one(".snippet-content-footer") else ""
        via = None
        if fm := re.search(r"Il y a .*?(?:jours?|heures?|minutes?|semaines?)\s+(.+?)\s+Signaler", footer):
            via = fm.group(1).strip()
        src = (img.get("src") or "") if img else ""
        out.append(Listing(
            source="trovit", source_id=it.get("data-id"),
            url=link.get("href") if link else None,
            title=f"{clean(it.get('data-property-type')) or 'Piso'} · {norm_zone(addr) or 'Luxembourg'}",
            price=parse_int(it.get("data-price")),
            surface=parse_surface(size_el.get_text()) if size_el else None,
            rooms=parse_int(rooms_el.get_text()) if rooms_el else None,
            baths=parse_int(baths_el.get_text()) if baths_el else None,
            zone=norm_zone(addr), kind=clean(it.get("data-property-type")) or None,
            photos=[("https:" + src) if src.startswith("//") else src] if src and "no-photo" not in src else [],
            via=via, description=clean(it.select_one(".item-description").get_text())[:300]
            if it.select_one(".item-description") else None,
        ))
    return out, total, raw_count


def scan(cfg: dict, fetcher: Fetcher, max_pages: int) -> SourceResult:
    res = SourceResult("trovit")
    t0 = time.time()
    seen = set()
    try:
        for page in range(1, max_pages + 1):
            url = cfg["url"].rstrip("/") + f"/page.{page}"
            items, total, raw = parse_page(fetcher.get(url).text, cfg.get("city", "Luxembourg"))
            res.total_reported = total
            res.pages = page
            if raw == 0:
                res.complete = True
                break
            fresh = [i for i in items if i.source_id not in seen]
            seen.update(i.source_id for i in fresh)
            res.listings.extend(fresh)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"[:300]
    res.seconds = time.time() - t0
    return res
