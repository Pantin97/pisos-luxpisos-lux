"""Pruebas: python -m pytest tests  (o simplemente: python tests/test_all.py)"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from backend import immotop, push  # noqa: E402
from backend.geo import Geocoder  # noqa: E402
from backend.pipeline import merge, score_all  # noqa: E402
from tests.make_fixtures import build  # noqa: E402

CFG = {
    "search": {"max_price": 1100000, "min_rooms": 2, "min_surface": 55, "max_age_days": 120},
    "work": {"label": "NSPA", "lat": 49.6466, "lon": 5.9893},
    "scoring": {"weights": {"value": .4, "size": .2, "commute": .25, "extras": .15},
                "ideal_surface": 95, "max_commute_km": 20, "reference_eur_m2": {}, "keywords": {"terrasse": 12}},
}


def test_parse_real_structure(tmp_path=Path("/tmp/pl_fx")):
    files = build(tmp_path)
    when = datetime(2026, 9, 14, tzinfo=timezone.utc)
    items = immotop.parse_alert_html(files[1].read_text(), when, "m1")
    assert len(items) == 2
    a, b = items
    assert a.price == 1047740 and a.surface == 77 and a.rooms == 2 and a.baths is None
    assert a.zone == "Limpertsberg" and a.street == "Rue Josephine Jacquemart-jaans"
    assert b.street == "Rue Joséphine Jacquemart-Jaans" and b.baths == 1
    assert a.image is None  # placeholder descartado
    k = immotop.parse_alert_html(files[0].read_text(), when, "m0")[0]
    assert k.floor == 3 and k.kind == "Appartement" and k.price == 920000 and k.surface == 88


def test_price_and_features():
    assert immotop.parse_price("€ 1 047 740") == 1047740
    assert immotop.parse_price("Prix sur demande") is None
    assert immotop.parse_features("68 m² | 2 chambres/pièces | 1 salle de bain") == (68.0, 2, 1)


def test_dedupe_and_score(tmp_path=Path("/tmp/pl_fx2")):
    files = build(tmp_path)
    raws = []
    for mid, when, html in immotop.load_html_dir(tmp_path, set()):
        raws += immotop.parse_alert_html(html, when, mid)
    assert len(raws) == 7
    history = {"listings": {}, "_backfill": True}
    new = merge(history, raws)
    # 7 apariciones → 4 inmuebles (Limpertsberg ×3 + su duplicado en Belair = 1)
    assert len(new) == 4, [r["title"] for r in history["listings"].values()]
    limp = next(r for r in history["listings"].values() if "Limpertsberg" in r["zones"])
    assert set(limp["zones"]) == {"Limpertsberg", "Belair"} and len(limp["alert_days"]) == 3

    geo = Geocoder(tmp_path / "geo.json", use_nominatim=False)
    ranked = score_all(history, CFG, geo, datetime(2026, 10, 14, tzinfo=timezone.utc), set(new))
    assert ranked[0]["zone"] == "Kirchberg", [(r["zone"], r["score"]) for r in ranked]
    assert "reanunciado" in next(r for r in ranked if r["zone"] == "Limpertsberg")["badges"]
    assert all(r["km_to_work"] for r in ranked)
    assert not any(r["is_new"] for r in ranked)  # primera carga: nada es "nuevo"


def test_price_drop_detected():
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    mk = lambda p, t: immotop.RawListing("Appartement 2 chambres 5, Rue de Test, Merl", "Merl", p, 90, 2, 1,
                                         "u", None, t, "m", street="Rue de Test")
    history = {"listings": {}}
    merge(history, [mk(1000000, t0)])
    merge(history, [mk(950000, t1)])
    (rec,) = history["listings"].values()
    assert [p["price"] for p in rec["price_history"]] == [1000000, 950000]
    ranked = score_all(history, CFG, Geocoder(Path("/tmp/g.json"), False), t1, set())
    assert "bajada" in ranked[0]["badges"]


def test_webpush_roundtrip():
    ua = ec.generate_private_key(ec.SECP256R1())
    p256dh = push.b64u(push._pub_bytes(ua.public_key()))
    auth = push.b64u(b"0123456789abcdef")
    msg = json.dumps({"title": "3 pisos nuevos"}).encode()
    body = push.encrypt(msg, p256dh, auth)
    assert push.decrypt(body, ua, auth) == msg
    priv, pub = push.generate_vapid_keys()
    hdr = push.vapid_header("https://web.push.apple.com/abc", push.load_vapid_private(priv), "mailto:a@b.c")
    assert hdr.startswith("vapid t=") and hdr.endswith(pub)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
