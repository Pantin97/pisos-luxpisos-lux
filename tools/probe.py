"""Sonda temporal: descarga páginas de los portales desde GitHub Actions y las guarda."""
import pathlib, sys, time, requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
      "Accept-Language": "fr-LU,fr;q=0.9,en;q=0.8", "Accept": "text/html,application/xhtml+xml"}
URLS = {
 "athome_p1": "https://www.athome.lu/srp/?tr=buy&q=d8380e34&ptypes=flat,4,7,5,6,42,32,41,43&price_max=1100000&bedrooms_min=2&sort=date_desc",
 "athome_p2": "https://www.athome.lu/srp/?tr=buy&q=d8380e34&ptypes=flat,4,7,5,6,42,32,41,43&price_max=1100000&bedrooms_min=2&sort=date_desc&page=2",
 "immotop_p1": "https://www.immotop.lu/vente-appartements/luxembourg/?prezzoMassimo=1100000&criterio=dataModifica&ordine=desc",
 "immotop_p2": "https://www.immotop.lu/vente-appartements/luxembourg/?prezzoMassimo=1100000&criterio=dataModifica&ordine=desc&pag=2",
 "wortimmo": "https://www.wortimmo.lu/fr/vente/appartement/luxembourg",
 "wortimmo_search": "https://www.wortimmo.lu/fr/recherche?transaction=vente&type=appartement&localite=luxembourg",
 "luxbazar": "https://www.luxbazar.lu/fr/immobilier/appartements/a-vendre",
 "weckbecker": "http://www.weckbecker.lu",
 "glesener": "https://www.glesener.lu",
}
out = pathlib.Path("probe"); out.mkdir(exist_ok=True)
s = requests.Session(); s.headers.update(UA)
for name, url in URLS.items():
    try:
        r = s.get(url, timeout=25, allow_redirects=True)
        (out / f"{name}.html").write_text(r.text, encoding="utf-8")
        print(f"{name}: {r.status_code} {len(r.text)} bytes -> {r.url}")
    except Exception as e:
        print(f"{name}: ERROR {e}")
    time.sleep(2)
