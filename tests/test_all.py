"""Pruebas: python tests/test_all.py

Las páginas de los portales se reproducen con su estructura real (mismas
claves JSON y clases CSS) pero con datos mínimos, para no guardar en el repo
datos personales de agentes."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from backend import push  # noqa: E402
from backend.alerts import compose, compute_events  # noqa: E402
from backend.enrich import parse_athome_detail, parse_generic_detail  # noqa: E402
from backend.geo import Geocoder  # noqa: E402
from backend.pipeline import ingest, is_active, mark_gone, score_all  # noqa: E402
from backend.sources import athome, immotop_email, trovit, wortimmo  # noqa: E402
from backend.sources.base import Listing, norm_zone, parse_int  # noqa: E402
from tests.make_fixtures import build  # noqa: E402

CFG = {
    "search": {"min_price": 150000, "max_price": 1100000, "min_rooms": 2, "min_surface": 55, "max_age_days": 120},
    "work": {"label": "Trabajo", "lat": 49.6466, "lon": 5.9893},
    "scoring": {"weights": {"value": .4, "size": .2, "commute": .25, "extras": .15},
                "ideal_surface": 95, "max_commute_km": 20, "reference_eur_m2": {}, "keywords": {}},
}
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)
GEO = Geocoder(Path("/tmp/pl_geo.json"), use_nominatim=False)


def athome_html(items, total=2):
    state = {"config": {}, "search": {"list": items, "listings": items, "total": total,
                                      "paginator": {"totalPages": 1}}}
    return f"<script>window.__INITIAL_STATE__={json.dumps(state)};(function(){{}})()</script>"


def athome_item(i, price, surface, rooms, city, lat=49.61, lon=6.11):
    return {"id": i, "price": price, "propertySurface": surface, "bedroomsCount": rooms,
            "propertySubType": "Apartment", "isNewBuild": False, "bathroomsCount": 1,
            "geo": {"cityName": city, "lat": str(lat), "lon": str(lon)},
            "media": {"items": [{"type": "photo", "uri": "/aa/bb/x.jpg"}]},
            "meta": {"permalink": {"fr": f"/vente/appartement/luxembourg/id-{i}.html"}},
            "publisher": {"name": "Agence Test", "website": "http://agence.lu"},
            "characteristic": {"floor_number": "3"}, "carparksCount": 1, "terraceesCount": 1}


WORT = """<div class="items-count-search-head">2 bien(s) trouvé(s)</div><div class="card"><div class="img">
<img data-src="https://static.wortimmo.lu/3/property/1/2/3/123_m.jpg"></div><div class="list-content">
<p class="serp-agency-title"> AGENCE W </p><h2><a class="js-ad-click property-box-4-title" data-ad-id="123"
href="/fr/vente-appartement-centre-luxembourg-merl-id_123">Appartement 2 chambre(s) à vendre à Luxembourg-Merl</a></h2>
<div class="price-property-box-4"> 840 000 € </div><p class="serp-ads-d-i">82m<sup>2</sup></p>
<p class="serp-ads-bed-d-b">2</p></div></div>"""

TROVIT = """<p>1-25 de 12 635 logements</p>
<div class="js-item" data-city="Luxembourg" data-id="abc" data-price="840000" data-property-type="Appartement">
<div class="snippet-gallery"><a class="rd-link" href="https://rd.example/abc"><img src="//img.trovit/abc.jpg"></a></div>
<div class="item-address"><span> 2550, Merl, Luxembourg, Canton Luxembourg </span></div>
<div class="item-rooms"><span>2 pièces</span></div><div class="item-baths"><span>1 s de bains</span></div>
<div class="item-size"><span>82 m²</span></div>
<div class="snippet-content-footer">Il y a 5 jours Immotop Signaler Voir l'annonce</div></div>
<div class="js-item" data-city="Esch-sur-Alzette" data-id="zzz" data-price="500000" data-property-type="Appartement"></div>"""


def test_parsers():
    items, total, _ = athome.parse_page(athome_html([athome_item(1, 840000, 82, 2, "Luxembourg-Merl"),
                                                     {"id": 9, "price": 0, "children": [{}]}]))
    assert total == 2 and len(items) == 1  # la ficha de promoción se ignora
    a = items[0]
    assert (a.price, a.surface, a.rooms, a.zone, a.floor) == (840000, 82, 2, "Merl", 3)
    assert a.photos[0].endswith("image_//aa/bb/x.jpg") and a.features["parking"] and a.features["terrace"]
    w, total = wortimmo.parse_page(WORT)
    assert total == 2 and w[0].price == 840000 and w[0].surface == 82 and w[0].zone == "Merl"
    assert w[0].photos and w[0].agency == "AGENCE W" and w[0].source_id == "123"
    t, total, raw = trovit.parse_page(TROVIT)
    assert total == 12635 and raw == 2 and len(t) == 1  # Esch se filtra por ciudad
    assert (t[0].price, t[0].surface, t[0].rooms, t[0].zone, t[0].via) == (840000, 82, 2, "Merl", "Immotop")


def test_zone_names():
    assert norm_zone("Luxembourg-Centre ville") == "Ville Haute"
    assert norm_zone("Gasperich - Cloche D'or") == "Gasperich"
    assert norm_zone("1529, Cents, Luxembourg, Canton Luxembourg") == "Cents"
    assert parse_int("€ 1 047 740") == 1047740


def test_cross_source_merge_and_gone():
    a = athome.parse_page(athome_html([athome_item(1, 840000, 82, 2, "Luxembourg-Merl"),
                                       athome_item(2, 840000, 82, 2, "Luxembourg-Merl")]))[0]
    w = wortimmo.parse_page(WORT)[0]
    t = trovit.parse_page(TROVIT)[0]
    h = {"listings": {}}
    assert len(ingest(h, a, NOW)) == 2          # dos unidades iguales de athome: pisos distintos
    assert ingest(h, w, NOW) == [] and ingest(h, t, NOW) == []  # mismo piso en wortimmo y Trovit
    rec = h["listings"]["athome:1"]
    assert set(rec["refs"]) == {"athome", "wortimmo", "trovit"} and rec["vias"] == ["Immotop"]
    # al día siguiente athome ya no lo tiene, pero wortimmo sí
    later = NOW + timedelta(days=1)
    ingest(h, [athome.parse_page(athome_html([athome_item(2, 840000, 82, 2, "Luxembourg-Merl")]))[0][0]], later)
    ingest(h, w, later)
    assert mark_gone(h, "athome", later) == 1 and is_active(rec)
    mark_gone(h, "wortimmo", later + timedelta(days=1))
    mark_gone(h, "trovit", later + timedelta(days=1))
    assert not is_active(rec)


def test_price_drop_and_scoring():
    mk = lambda p: Listing("athome", "7", "u", "Apartamento", p, 90, 2, zone="Merl", lat=49.605, lon=6.106)
    h = {"listings": {}}
    ingest(h, [mk(1000000)], NOW - timedelta(days=20))
    ingest(h, [mk(950000)], NOW)
    (rec,) = h["listings"].values()
    assert [p["price"] for p in rec["price_history"]] == [1000000, 950000]
    ranked = score_all(h, CFG, GEO, NOW, set())
    assert "bajada" in ranked[0]["badges"] and 0 <= ranked[0]["score"] <= 100


def test_immotop_email(tmp=Path("/tmp/pl_fx")):
    files = build(tmp)
    items = immotop_email.parse_alert_html(files[1].read_text(), NOW, "m1")
    assert len(items) == 2 and items[0].price == 1047740 and items[0].street == "Rue Josephine Jacquemart-jaans"


def test_webpush_roundtrip():
    ua = ec.generate_private_key(ec.SECP256R1())
    p256dh = push.b64u(push._pub_bytes(ua.public_key()))
    auth = push.b64u(b"0123456789abcdef")
    msg = json.dumps({"title": "3 pisos nuevos"}).encode()
    assert push.decrypt(push.encrypt(msg, p256dh, auth), ua, auth) == msg
    priv, pub = push.generate_vapid_keys()
    hdr = push.vapid_header("https://web.push.apple.com/abc", push.load_vapid_private(priv), "mailto:a@b.c")
    assert hdr.startswith("vapid t=") and hdr.endswith(pub)


def test_athome_detail():
    app = {"preloadedState": {"listing": {"listing": {
        "address": {"street": "Rue Jean L'aveugle", "floor": 2}, "charges": 1200, "chargesPaymentFrequency": "yearly",
        "characteristic": {"constructionYear": 1972, "hasLift": True, "balconySurface": 4, "hasCellar": True, "garages": 1},
        "energy": {"energyEfficiency": {"energyClass": "F"}, "thermalInsulation": {"insulationClass": "G"}, "hasGasHeating": True},
        "createdAt": "20251024T135411Z", "status": "active", "media": {"photos": ["/cd/7c/x.jpg"], "virtualVisit": "https://tour"}},
        "listingOld": {"underSalesAgreement": False}}}}
    d = parse_athome_detail(f"<script>window.AT_HOME_APP = {json.dumps(app)};</script>")
    assert (d["energy_class"], d["insulation_class"], d["construction_year"], d["charges_month"]) == ("F", "G", 1972, 100)
    assert d["lift"] and d["balcony_m2"] == 4 and d["parking"] == 1 and d["cellar"] and d["heating"] == ["gas"]
    assert d["listed_since"] == "2025-10-24" and not d["under_offer"] and d["photos"][0].endswith("image_//cd/7c/x.jpg")
    g = parse_generic_detail("<p>Classe énergétique : C</p><p>Année de construction : 2019</p><p>Ascenseur</p><p>Terrasse 12 m²</p>")
    assert g["energy_class"] == "C" and g["construction_year"] == 2019 and g["lift"] and g["terrace_m2"] == 12


def test_alerts():
    cfg = {"notify": {"zones": ["Merl"], "deal_discount": 0.15, "deal_score": 99, "min_score": 0}}
    mk = lambda i, zone, disc, active=True, badges=(): {"id": i, "zone": zone, "price": 800000, "surface": 90, "rooms": 2,
                                                     "score": 60, "discount": disc, "active": active, "badges": list(badges)}
    h = {"listings": {"a": {"price_history": [{"date": "2026-10-14", "price": 800000}]},
                      "b": {"price_history": [{"date": "2026-10-01", "price": 850000}, {"date": "2026-10-14", "price": 800000}]},
                      "c": {}, "d": {}, "e": {}}}
    ranked = [mk("a", "Merl", 0.2), mk("b", "Merl", 0.0), mk("c", "Gare", 0.3), mk("d", "Gare", 0, active=False),
              mk("e", "Gare", 0, badges=["compromiso"])]
    ev = compute_events(h, ranked, {"a", "c"}, cfg, {"d", "e"}, NOW, backfill=False)
    assert sorted(e["type"] for e in ev) == ["bajada", "chollo", "compromiso", "retirado"]  # c: fuera de zona
    assert compute_events(h, ranked, {"a", "c"}, cfg, {"d", "e"}, NOW, backfill=False) == []  # no repite
    p = compose(ev)
    assert p["title"].startswith("Chollo en Merl") and "1 bajada" in p["body"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
