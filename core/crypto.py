"""Cryptographic utilities for protecting sensitive credentials at rest.

Encrypts tokens stored in SQLite using an Encrypt-then-MAC counter-mode stream cipher
derived from the app SECRET_KEY using PBKDF2-HMAC-SHA256. Transparently handles legacy
plaintext tokens for backwards compatibility.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from core.settings import SECRET_KEY

PREFIX = "enc:v1:"


def encrypt_token(token: str | None, secret: str = SECRET_KEY) -> str | None:
    """Encrypt a plaintext credential string with authenticated encryption."""
    if not token:
        return token
    if token.startswith(PREFIX):
        return token

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 2000, 64)
    k_enc, k_mac = derived[:32], derived[32:]

    data = token.encode("utf-8")
    keystream = bytearray()
    for i in range((len(data) + 31) // 32):
        keystream.extend(hmac.new(k_enc, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest())

    ciphertext = bytes(a ^ b for a, b in zip(data, keystream[: len(data)]))
    tag = hmac.new(k_mac, salt + nonce + ciphertext, hashlib.sha256).digest()

    payload = base64.urlsafe_b64encode(salt + nonce + tag + ciphertext).decode("ascii")
    return f"{PREFIX}{payload}"


def decrypt_token(payload: str | None, secret: str = SECRET_KEY) -> str | None:
    """Decrypt an encrypted token, or return as-is if unencrypted."""
    if not payload:
        return payload
    if not payload.startswith(PREFIX):
        return payload

    try:
        raw = base64.urlsafe_b64decode(payload[len(PREFIX) :].encode("ascii"))
        if len(raw) < 64:
            return payload
        salt = raw[:16]
        nonce = raw[16:32]
        tag = raw[32:64]
        ciphertext = raw[64:]

        derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 2000, 64)
        k_enc, k_mac = derived[:32], derived[32:]

        expected_tag = hmac.new(k_mac, salt + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            return payload

        keystream = bytearray()
        for i in range((len(ciphertext) + 31) // 32):
            keystream.extend(hmac.new(k_enc, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest())

        plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream[: len(ciphertext)])).decode("utf-8")
        return plaintext
    except Exception:
        return payload
