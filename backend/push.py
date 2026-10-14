"""Web Push sin dependencias externas (solo `cryptography` y `requests`).

Implementa el cifrado aes128gcm de RFC 8291 y la autenticación VAPID de
RFC 8292, que es lo que necesita Safari en iOS (16.4+) para entregar
notificaciones a una PWA instalada en la pantalla de inicio.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _pub_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _hmac(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


# ───────────────────────── VAPID ─────────────────────────

def generate_vapid_keys() -> tuple[str, str]:
    """(clave_privada_b64url, clave_publica_b64url)"""
    priv = ec.generate_private_key(ec.SECP256R1())
    d = priv.private_numbers().private_value.to_bytes(32, "big")
    return b64u(d), b64u(_pub_bytes(priv.public_key()))


def load_vapid_private(b64: str) -> ec.EllipticCurvePrivateKey:
    d = int.from_bytes(b64u_dec(b64), "big")
    return ec.derive_private_key(d, ec.SECP256R1())


def vapid_header(endpoint: str, priv: ec.EllipticCurvePrivateKey, subject: str) -> str:
    u = urlparse(endpoint)
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                              "sub": subject}, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    r, s = decode_dss_signature(priv.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    jwt = f"{header}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={b64u(_pub_bytes(priv.public_key()))}"


# ───────────────────────── cifrado RFC 8291 ─────────────────────────

def encrypt(payload: bytes, p256dh: str, auth: str, *, _salt: bytes | None = None,
            _eph: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    ua_pub_bytes = b64u_dec(p256dh)
    auth_secret = b64u_dec(auth)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    eph = _eph or ec.generate_private_key(ec.SECP256R1())
    as_pub_bytes = _pub_bytes(eph.public_key())
    shared = eph.exchange(ec.ECDH(), ua_pub)

    prk_key = _hmac(auth_secret, shared)
    ikm = _hmac(prk_key, b"WebPush: info\x00" + ua_pub_bytes + as_pub_bytes + b"\x01")
    salt = _salt or os.urandom(16)
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]

    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!I", 4096) + bytes([len(as_pub_bytes)]) + as_pub_bytes
    return header + ciphertext


def decrypt(body: bytes, ua_priv: ec.EllipticCurvePrivateKey, auth: str) -> bytes:
    """Lado del navegador; solo se usa en los tests para verificar el cifrado."""
    salt, idlen = body[:16], body[20]
    as_pub_bytes = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    as_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub_bytes)
    shared = ua_priv.exchange(ec.ECDH(), as_pub)
    ua_pub_bytes = _pub_bytes(ua_priv.public_key())
    prk_key = _hmac(b64u_dec(auth), shared)
    ikm = _hmac(prk_key, b"WebPush: info\x00" + ua_pub_bytes + as_pub_bytes + b"\x01")
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    plain = AESGCM(cek).decrypt(nonce, ciphertext, None)
    return plain.rstrip(b"\x00")[:-1]  # quita el delimitador 0x02


# ───────────────────────── envío ─────────────────────────

def send(subscription: dict, data: dict, vapid_private_b64: str, subject: str, ttl: int = 86400) -> int:
    import requests
    endpoint = subscription["endpoint"]
    keys = subscription["keys"]
    body = encrypt(json.dumps(data, ensure_ascii=False).encode(), keys["p256dh"], keys["auth"])
    priv = load_vapid_private(vapid_private_b64)
    r = requests.post(endpoint, data=body, timeout=15, headers={
        "Authorization": vapid_header(endpoint, priv, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl),
        "Urgency": "normal",
    })
    return r.status_code


def parse_subscriptions(raw: str | None) -> list[dict]:
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]
