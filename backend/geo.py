"""Coordenadas de los anuncios y distancia al trabajo.

Primero intenta geocodificar la calle (si el título la trae) con Nominatim
(OpenStreetMap, 1 petición/s, con caché en data/geocache.json). Si no puede,
usa el centro aproximado del barrio/commune de la tabla de abajo.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .immotop import fold

# Centros aproximados de barrios de Luxemburgo ciudad y communes cercanas.
ZONES = {
    "ville haute": (49.6116, 6.1300), "centre": (49.6116, 6.1300),
    "gare": (49.6000, 6.1335), "limpertsberg": (49.6210, 6.1230),
    "belair": (49.6110, 6.1120), "merl": (49.6040, 6.1060),
    "kirchberg": (49.6290, 6.1600), "bonnevoie": (49.5950, 6.1400),
    "bonnevoie-nord": (49.5990, 6.1420), "bonnevoie-sud": (49.5900, 6.1410),
    "cessange": (49.5900, 6.1000), "hollerich": (49.5990, 6.1150),
    "rollingergrund": (49.6200, 6.1000), "muhlenbach": (49.6270, 6.1150),
    "beggen": (49.6430, 6.1300), "dommeldange": (49.6360, 6.1380),
    "eich": (49.6300, 6.1300), "weimerskirch": (49.6260, 6.1400),
    "clausen": (49.6130, 6.1400), "pfaffenthal": (49.6170, 6.1330),
    "grund": (49.6090, 6.1350), "neudorf": (49.6170, 6.1580),
    "cents": (49.6100, 6.1650), "hamm": (49.6050, 6.1800),
    "pulvermuhl": (49.6050, 6.1550), "gasperich": (49.5850, 6.1250),
    "cloche d'or": (49.5800, 6.1200), "kalchesbreck": (49.6240, 6.1700),
    "bertrange": (49.6110, 6.0500), "strassen": (49.6200, 6.0700),
    "mamer": (49.6270, 6.0230), "capellen": (49.6453, 5.9897),
    "howald": (49.5830, 6.1450), "hesperange": (49.5700, 6.1500),
    "helmsange": (49.6650, 6.1380), "walferdange": (49.6600, 6.1330),
    "steinsel": (49.6770, 6.1240), "luxembourg": (49.6116, 6.1300),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


class Geocoder:
    def __init__(self, cache_path: Path, use_nominatim: bool = True):
        self.cache_path = cache_path
        self.use_nominatim = use_nominatim
        self._last = 0.0
        self._offline = False
        try:
            self.cache = json.loads(cache_path.read_text())
        except Exception:
            self.cache = {}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False))

    def _nominatim(self, query: str) -> tuple[float, float] | None:
        if query in self.cache:
            v = self.cache[query]
            return tuple(v) if v else None
        if not self.use_nominatim or self._offline:
            return None
        try:
            import requests
            wait = 1.1 - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "countrycodes": "lu"},
                headers={"User-Agent": "pisos-lux/1.0 (personal flat-search tool)"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            val = (float(data[0]["lat"]), float(data[0]["lon"])) if data else None
        except Exception:
            self._offline = True  # sin red: no insistir en esta ejecución
            return None
        self.cache[query] = list(val) if val else None
        return val

    def locate(self, street: str | None, zone: str | None) -> tuple[tuple[float, float] | None, str]:
        """Devuelve (coords, precisión) con precisión 'calle', 'barrio' o 'desconocida'."""
        if street:
            hit = self._nominatim(f"{street}, {zone + ', ' if zone else ''}Luxembourg")
            if hit:
                return hit, "calle"
        z = fold(zone)
        if z in ZONES:
            return ZONES[z], "barrio"
        for key, val in ZONES.items():
            if key in z or (z and z in key):
                return val, "barrio"
        if zone:
            hit = self._nominatim(f"{zone}, Luxembourg")
            if hit:
                return hit, "barrio"
        return None, "desconocida"
