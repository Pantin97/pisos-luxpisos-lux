"""Fuente Immotop.lu: lee los emails de alerta y extrae los anuncios.

Las alertas de Immotop traen un bloque <table class="realEstateBlock"> por
anuncio con título, zona, precio y características. Los enlaces son de
seguimiento (clicks.immotop.lu) y redirigen a la ficha real; si
`resolve_links` está activo se siguen para obtener el ID estable.
"""
from __future__ import annotations

import email
import imaplib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup

ORDINALS = {
    "rez-de-chaussee": 0, "premier": 1, "1er": 1, "deuxieme": 2, "2eme": 2,
    "troisieme": 3, "3eme": 3, "quatrieme": 4, "4eme": 4, "cinquieme": 5,
    "5eme": 5, "sixieme": 6, "6eme": 6, "septieme": 7, "huitieme": 8,
}
STREET_RE = re.compile(
    r"((?:rue|avenue|av\.|boulevard|bd|route|all[ée]e|place|val|mont[ée]e|chemin|c[ôo]te|"
    r"impasse|rond-point|square|cit[ée])\s[^,]+)",
    re.I,
)


@dataclass
class RawListing:
    title: str
    zone: str | None
    price: int | None
    surface: float | None
    rooms: int | None
    baths: int | None
    tracking_url: str | None
    image: str | None
    received_at: datetime
    message_id: str
    kind: str | None = None
    floor: int | None = None
    street: str | None = None
    immotop_id: str | None = None
    final_url: str | None = None
    extra: dict = field(default_factory=dict)


# ───────────────────────── helpers ─────────────────────────

def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("﻿", "")).strip()


def fold(s: str | None) -> str:
    """minúsculas sin acentos, para comparar."""
    s = unicodedata.normalize("NFKD", clean(s)).encode("ascii", "ignore").decode()
    return s.lower()


def parse_price(text: str | None) -> int | None:
    m = re.search(r"\d[\d\s  .']*", text or "")
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(0))
    return int(digits) if digits else None


def parse_features(text: str | None) -> tuple[float | None, int | None, int | None]:
    t = clean(text)
    surface = rooms = baths = None
    if m := re.search(r"([\d.,]+)\s*m\s*(?:²|2|&sup2;)", t):
        surface = float(m.group(1).replace(".", "").replace(",", "."))
    if m := re.search(r"(\d+)\s*chambre", t, re.I):
        rooms = int(m.group(1))
    if m := re.search(r"(\d+)\s*salle", t, re.I):
        baths = int(m.group(1))
    return surface, rooms, baths


def parse_title(title: str) -> dict:
    f = fold(title)
    out: dict = {"kind": clean(title).split(" ")[0] if title else None}
    if "rez-de-chaussee" in f:
        out["floor"] = 0
    else:
        for word, n in ORDINALS.items():
            if re.search(rf"\b{word}\s+etage", f):
                out["floor"] = n
                break
        if "dernier etage" in f:
            out["floor"] = out.get("floor", 99)
    if m := STREET_RE.search(clean(title)):
        street = re.sub(r"[.\s]*L-\d{4}.*$", "", clean(m.group(1)))
        out["street"] = street.rstrip(". ")
    return out


def norm_street(street: str | None) -> str | None:
    if not street:
        return None
    s = fold(street)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip() or None


# ───────────────────────── parsing ─────────────────────────

def parse_alert_html(html: str, received_at: datetime, message_id: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawListing] = []
    for block in soup.select("table.realEstateBlock"):
        title_td = block.select_one("td.realEstateBlock__title")
        if not title_td or not title_td.find("a"):
            continue
        a = title_td.find("a")
        title = clean(a.get("title") or a.get_text())
        sub = block.select_one("td.realEstateBlock__subtitle")
        price_td = block.select_one("td.realEstateBlock__price")
        feat_td = block.select_one("td.realEstateBlock__features")
        img = block.select_one("img.realEstateBlock__image")
        surface, rooms, baths = parse_features(feat_td.get_text(" ") if feat_td else "")
        image = img.get("src") if img else None
        if image and "placeholder" in image:
            image = None
        meta = parse_title(title)
        out.append(RawListing(
            title=title,
            zone=clean(sub.get_text()) if sub else None,
            price=parse_price(price_td.get_text() if price_td else None),
            surface=surface, rooms=rooms, baths=baths,
            tracking_url=a.get("href"),
            image=image,
            received_at=received_at,
            message_id=message_id,
            kind=meta.get("kind"), floor=meta.get("floor"), street=meta.get("street"),
        ))
    return out


# ───────────────────────── fetching ─────────────────────────

def _all_mail_folder(M: imaplib.IMAP4_SSL) -> str:
    """Busca la carpeta 'Todos' de Gmail por su flag \\All (el nombre cambia con el idioma)."""
    typ, data = M.list()
    for raw in data or []:
        line = raw.decode(errors="ignore")
        if "\\All" in line:
            name = line.rsplit(' "/" ', 1)[-1].strip()
            return name if name.startswith('"') else f'"{name}"'
    return "INBOX"


def fetch_imap(user: str, password: str, sender: str, since: datetime,
               skip_ids: set[str], host: str = "imap.gmail.com") -> list[tuple[str, datetime, str]]:
    """Devuelve (message_id, fecha, html) de las alertas nuevas. Solo lectura: no marca nada como leído."""
    M = imaplib.IMAP4_SSL(host)
    M.login(user, password)
    try:
        M.select(_all_mail_folder(M), readonly=True)
        typ, data = M.search(None, "FROM", f'"{sender}"', "SINCE", since.strftime("%d-%b-%Y"))
        results = []
        for num in (data[0].split() if data and data[0] else []):
            typ, msg_data = M.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(msg_data[0][1])
            mid = clean(msg.get("Message-ID")) or f"imap-{num.decode()}"
            if mid in skip_ids:
                continue
            try:
                when = parsedate_to_datetime(msg.get("Date"))
            except Exception:
                when = datetime.now(timezone.utc)
            html = None
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
            if html:
                results.append((mid, when, html))
        return results
    finally:
        try:
            M.logout()
        except Exception:
            pass


def load_html_dir(path: str | Path, skip_ids: set[str]) -> list[tuple[str, datetime, str]]:
    """Modo local/pruebas: ficheros YYYY-MM-DD_*.html (o .eml) en una carpeta."""
    results = []
    for p in sorted(Path(path).glob("*")):
        if p.suffix not in (".html", ".eml") or p.name in skip_ids:
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
        when = (datetime.fromisoformat(m.group(1)).replace(hour=9, tzinfo=timezone.utc)
                if m else datetime.now(timezone.utc))
        raw = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix == ".eml":
            msg = email.message_from_string(raw)
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    raw = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
        results.append((p.name, when, raw))
    return results


def resolve_link(url: str | None, timeout: float = 10) -> tuple[str | None, str | None]:
    """Sigue el enlace de seguimiento. Devuelve (url_final, id_immotop) o (None, None)."""
    if not url:
        return None, None
    try:
        import requests
        r = requests.get(url, allow_redirects=True, timeout=timeout, stream=True,
                         headers={"User-Agent": "Mozilla/5.0 (pisos-lux personal alert reader)"})
        final = r.url
        r.close()
    except Exception:
        return None, None
    m = re.search(r"/(?:annonces|annunci|listing)/(\d+)", final)
    return final, (m.group(1) if m else None)
