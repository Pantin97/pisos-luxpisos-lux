"""Sonda temporal: descarga páginas de los portales desde GitHub Actions y las guarda."""
import pathlib, sys, time, requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
      "Accept-Language": "fr-LU,fr;q=0.9,en;q=0.8", "Accept": "text/html,application/xhtml+xml"}
URLS = {
 "wort_slug": "https://www.wortimmo.lu/fr/get-location-slug-from-keyword?keyword=Luxembourg",
 "wort_centre_lux": "https://www.wortimmo.lu/fr/vente/appartement/centre/luxembourg",
 "wort_lux": "https://www.wortimmo.lu/fr/vente/appartement/luxembourg-ville",
 "vivi_app": "https://www.vivi.lu/fr/achat/appartement",
 "trovit_immo": "https://immo.trovit.lu/",
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
