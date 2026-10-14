"""Sonda temporal: descarga páginas de los portales desde GitHub Actions y las guarda."""
import pathlib, sys, time, requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
      "Accept-Language": "fr-LU,fr;q=0.9,en;q=0.8", "Accept": "text/html,application/xhtml+xml"}
URLS = {
 "trovit_search": "https://immo.trovit.lu/index.php/cod.search_homes/type.1/what_d.luxembourg/isUserSearch.1",
 "wort_filtered": "https://www.wortimmo.lu/fr/vente/appartement/centre/luxembourg?qs%5BlocationId%5D=90&qs%5BpriceTo%5D=1100000&qs%5BbedroomsFrom%5D=2",
 "newimmo_buy": "https://www.newimmo.lu/fr/acheter/",
}
out = pathlib.Path("probe"); out.mkdir(exist_ok=True)
sys.stdout.reconfigure(line_buffering=True)
s = requests.Session(); s.headers.update(UA)
for name, url in URLS.items():
    try:
        r = s.get(url, timeout=25, allow_redirects=True)
        (out / f"{name}.html").write_text(r.text, encoding="utf-8")
        print(f"{name}: {r.status_code} {len(r.text)} bytes -> {r.url}")
    except Exception as e:
        print(f"{name}: ERROR {e}")
    time.sleep(2)
