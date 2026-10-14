"""Tipos y utilidades comunes a todas las fuentes."""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Safari/605.1.15")


@dataclass
class Listing:
    """Un anuncio tal y como lo publica una fuente concreta."""
    source: str                     # athome | wortimmo | trovit | immotop
    source_id: str | None
    url: str | None
    title: str
    price: int | None
    surface: float | None
    rooms: int | None               # dormitorios
    zone: str | None = None         # barrio normalizado (Belair, Kirchberg…)
    baths: int | None = None
    floor: int | None = None
    lat: float | None = None
    lon: float | None = None
    photos: list[str] = field(default_factory=list)
    agency: str | None = None
    agency_site: str | None = None
    via: str | None = None          # portal original cuando la fuente es un agregador
    kind: str | None = None
    new_build: bool = False
    street: str | None = None
    description: str | None = None
    features: dict = field(default_factory=dict)  # terrace, balcony, elevator, parking, garden
    seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SourceResult:
    name: str
    listings: list[Listing] = field(default_factory=list)
    pages: int = 0
    total_reported: int | None = None
    complete: bool = False          # ¿se recorrieron todas las páginas?
    error: str | None = None
    seconds: float = 0.0

    def stats(self) -> dict:
        return {"name": self.name, "items": len(self.listings), "pages": self.pages,
                "total_reported": self.total_reported, "complete": self.complete,
                "error": self.error, "seconds": round(self.seconds, 1)}


# ───────────────────────── texto ─────────────────────────

def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("﻿", "").replace("\xa0", " ")).strip()


def fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", clean(s)).encode("ascii", "ignore").decode()
    return s.lower()


def parse_int(text) -> int | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    m = re.search(r"\d[\d\s  .']*", str(text))
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(0))
    return int(digits) if digits else None


def parse_surface(text) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text) or None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m", str(text))
    return float(m.group(1).replace(",", ".")) if m else None


ZONE_ALIASES = {
    "centre ville": "Ville Haute", "centre-ville": "Ville Haute", "centre": "Ville Haute",
    "ville haute": "Ville Haute", "gasperich-cloche d'or": "Gasperich", "cloche d'or": "Cloche d'Or",
    "neudorf-weimershof": "Neudorf", "weimershof": "Neudorf", "muhlenbach": "Muhlenbach",
    "pulvermuhl": "Pulvermuhl", "verlorenkost": "Bonnevoie", "bonnevoie-nord": "Bonnevoie",
    "bonnevoie-sud": "Bonnevoie", "bonnevoie nord": "Bonnevoie", "bonnevoie sud": "Bonnevoie",
    "rollingergrund": "Rollingergrund", "luxembourg": "Luxembourg", "pfaffenthall": "Pfaffenthal",
    "gasperich-cloche dor": "Gasperich", "gasperich cloche dor": "Gasperich", "cloche dor": "Cloche d'Or",
    "ville-haute": "Ville Haute", "gare": "Gare", "hamm": "Hamm", "eich": "Eich", "cents": "Cents",
}


def norm_zone(raw: str | None) -> str | None:
    """'Luxembourg-Belair' / 'Belair' / '1529, Cents, Luxembourg' → 'Belair' / 'Cents'."""
    if not raw:
        return None
    z = clean(raw)
    z = re.sub(r"^\d{4},\s*", "", z)                 # código postal delante
    z = z.split(",")[0].strip()
    z = re.sub(r"\s*-\s*", "-", z)
    z = re.sub(r"^luxembourg[-\s]+", "", z, flags=re.I).strip() or "Luxembourg"
    key = fold(z).replace("’", "'")
    for k in (key, key.replace("-", " ")):
        if k in ZONE_ALIASES:
            return ZONE_ALIASES[k]
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in z.split(" "))


# ───────────────────────── red ─────────────────────────

class Fetcher:
    """Peticiones educadas: un retardo por dominio, reintentos ante 429/5xx."""

    def __init__(self, delay: float = 1.5, timeout: float = 25):
        import requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "fr-LU,fr;q=0.9,en;q=0.8",
                               "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})
        self.delay = delay
        self.timeout = timeout
        self._last: dict[str, float] = {}

    def get(self, url: str, **kw):
        host = urlparse(url).netloc
        for attempt in range(3):
            wait = self.delay - (time.time() - self._last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.time()
            r = self.s.get(url, timeout=self.timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(4 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()
        return r
