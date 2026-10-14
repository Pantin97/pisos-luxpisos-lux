"""Genera el par de claves VAPID para las notificaciones.

    python tools/gen_vapid.py

Copia cada valor en un secreto de GitHub (Settings → Secrets and variables → Actions).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.push import generate_vapid_keys  # noqa: E402

priv, pub = generate_vapid_keys()
print("VAPID_PUBLIC_KEY =", pub)
print("VAPID_PRIVATE_KEY =", priv)
print("VAPID_SUBJECT = mailto:tu-correo@ejemplo.com")
