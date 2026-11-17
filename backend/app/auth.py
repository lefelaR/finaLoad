"""Small HMAC JWT for the optional local login. Off unless AUTH_REQUIRED=true."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me")


def mint(subject: str, ttl_seconds: int = 60 * 60 * 12) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(
        json.dumps(
            {"sub": subject, "exp": int(time.time()) + ttl_seconds},
            separators=(",", ":"),
        ).encode()
    )
    sig = hmac.new(secret().encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(sig)}"


def verify(token: str) -> dict | None:
    try:
        header, body, sig = token.split(".")
    except ValueError:
        return None
    expected = hmac.new(secret().encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(expected), sig):
        return None
    payload = json.loads(_unb64(body))
    if int(payload.get("exp", 0)) < time.time():
        return None
    return payload
