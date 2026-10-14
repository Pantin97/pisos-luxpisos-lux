# Pisos Lux

PWA personal que cada mañana lee tus alertas de Immotop en Gmail, quita duplicados,
puntúa cada piso (€/m², superficie, distancia al trabajo, extras) y te avisa en el iPhone.

```
Gmail (alertas Immotop) ──IMAP──▶ GitHub Actions (cada mañana)
                                   backend/run.py
                                   ├─ parsea los emails
                                   ├─ fusiona con data/history.json (dedupe, bajadas de precio)
                                   ├─ puntúa según config.yaml
                                   ├─ escribe docs/listings.json
                                   └─ Web Push ──▶ iPhone
GitHub Pages (docs/) ──▶ PWA instalada en pantalla de inicio
```

## Puesta en marcha (una vez, ~20 min)

1. **Repositorio.** Crea un repo en GitHub y sube esta carpeta. GitHub Pages gratis
   necesita repo público: el código y `docs/listings.json` (pisos y precios) serán visibles.
   No contiene tu correo ni tus credenciales.

2. **Acceso de solo lectura a Gmail.** Con la verificación en dos pasos activada, crea una
   contraseña de aplicación en <https://myaccount.google.com/apppasswords>. En el repo,
   *Settings → Secrets and variables → Actions → New repository secret*:
   - `GMAIL_USER` → tu dirección de Gmail
   - `GMAIL_APP_PASSWORD` → la contraseña de 16 letras

3. **Claves de notificación.** En tu ordenador: `pip install cryptography && python tools/gen_vapid.py`.
   Crea los secretos `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` y `VAPID_SUBJECT` con lo que imprime.

4. **Publicar la app.** *Settings → Pages → Build and deployment*: rama `main`, carpeta `/docs`.
   La dirección será `https://TU-USUARIO.github.io/NOMBRE-REPO/`.

5. **Primera carga.** *Actions → Pisos diarios → Run workflow*. Lee los últimos 120 días de
   alertas y no envía avisos (todo sería "nuevo").

6. **Instalar en el iPhone.** Abre la dirección en Safari → Compartir → *Añadir a pantalla de
   inicio*. Abre Pisos Lux desde el icono → ⚙ → *Activar avisos* → *Copiar*, y pega el texto
   en el secreto `PUSH_SUBSCRIPTIONS`. Para varios móviles, pon un array JSON: `[{…}, {…}]`.

A partir de ahí se ejecuta solo cada mañana.

## Afinar resultados

- **Alertas más amplias = mejores resultados.** La app puntúa y ordena, así que conviene que
  las alertas de Immotop filtren poco (más barrios, sin exigir ascensor o parking) y dejar el
  filtrado fino a `config.yaml`.
- **`config.yaml`**: presupuesto, superficie mínima, pesos de la puntuación, palabras clave
  (terrasse, balcon…) y €/m² de referencia por barrio (`reference_eur_m2`). Sin referencias,
  compara con la mediana de los pisos vistos, que con pocos anuncios es una referencia débil.
- **Aviso extra por ntfy** (opcional): secreto `NTFY_TOPIC` con un nombre difícil de adivinar
  y la app ntfy suscrita a ese tema.

## Desarrollo local

```bash
pip install -r requirements.txt
python tests/test_all.py                      # pruebas
python tests/make_fixtures.py                 # alertas de ejemplo
python -m backend.run --html-dir tests/fixtures --no-notify
cd docs && python -m http.server 8000         # http://localhost:8000
```

## Añadir otra fuente (athome.lu, wortimmo…)

Cada portal manda alertas con su propio HTML. Escribe un `parse_alert_html` equivalente al
de `backend/immotop.py` para ese remitente y añádelo en `backend/run.py`; el resto
(deduplicado, puntuación, avisos) ya es común.

## Limitaciones conocidas

- Una alerta dice cuándo aparece un piso, no cuándo se vende: los pisos se ocultan a los
  `max_age_days` de haberse visto por primera vez.
- La distancia es en línea recta, desde la calle si el título la trae o desde el centro
  del barrio si no.
- Guardados y descartados se quedan en el dispositivo (no se sincronizan entre móviles).
- Si Immotop cambia el diseño de sus emails, la ejecución avisa en el log de Actions con
  "no se reconoció ningún anuncio".
