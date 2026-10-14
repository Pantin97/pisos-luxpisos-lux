"""wortimmo.lu: tarjetas de resultados en HTML (div.list-content)."""
from __future__ import annotations

import math
import re
import time

from bs4 import BeautifulSoup

from .base import Fetcher, Listing, SourceResult, clean, norm_zone, parse_int, parse_surface

BASE = "https://www.wortimmo.lu"


def _photo(card) -> str | None:
    node = card
    for _ in range(6):
        node = node.parent
        if node is None:
            return None
        for img in node.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if "/property/" in src:
                return src
    return None


def parse_page(html: str) -> tuple[list[Listing], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    total = None
    if (h := soup.select_one(".items-count-search-head")):
        total = parse_int(h.get_text())
    out = []
    for card in soup.select(".list-content"):
        a = card.select_one("a[class*=property-box][class*=-title]") or card.select_one("a[data-ad-id]")
        if not a:
            continue
        title = clean(a.get_text())
        href = a.get("href") or ""
        ad_id = a.get("data-ad-id") or (re.search(r"id_(\d+)", href) or [None, None])[1]
        price_el = card.select_one(".n-d-price") or card.select_one("[class*=price-property-box]")
        surf_el = card.select_one(".serp-ads-d-i")
        bed_el = card.select_one(".serp-ads-bed-d-b")
        agency_el = card.select_one(".serp-agency-title")
        m = re.search(r"à vendre à (.+)$", title)
        zone = norm_zone(m.group(1)) if m else None
        kind = title.split(" ")[0] if title else None
        out.append(Listing(
            source="wortimmo", source_id=str(ad_id) if ad_id else None,
            url=BASE + href if href.startswith("/") else href, title=title,
            price=parse_int(price_el.get_text()) if price_el else None,
            surface=parse_surface(surf_el.get_text(" ")) if surf_el else None,
            rooms=parse_int(bed_el.get_text()) if bed_el else None,
            zone=zone, kind={"Appartement": "Apartamento", "Penthouse": "Ático", "Duplex": "Dúplex"}.get(kind, kind),
            agency=clean(agency_el.get_text()) if agency_el else None,
            photos=[p] if (p := _photo(card)) else [],
        ))
    return out, total


def scan(cfg: dict, fetcher: Fetcher, max_pages: int) -> SourceResult:
    res = SourceResult("wortimmo")
    t0 = time.time()
    seen = set()
    try:
        page, pages = 1, 1
        while page <= min(pages, max_pages):
            url = cfg["url"] + ("&" if "?" in cfg["url"] else "?") + f"page={page}"
            items, total = parse_page(fetcher.get(url).text)
            res.total_reported = total
            res.pages = page
            if not items:
                break
            if page == 1:
                pages = math.ceil((total or len(items)) / max(len(items), 1))
            fresh = [i for i in items if i.source_id not in seen]
            if not fresh:
                break
            seen.update(i.source_id for i in fresh)
            res.listings.extend(fresh)
            page += 1
        res.complete = res.pages >= pages
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"[:300]
    res.seconds = time.time() - t0
    return res
