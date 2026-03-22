"""HMAC signing for wlanpi-core internal API calls.

Replicates the signing logic from wlanpi_core/core/auth.py:verify_hmac().

Canonical string format:
    f"{method}\\n{path}\\n{query_string}\\n{body}"

Header: X-Request-Signature: <sha256_hex_digest>

Secret location: /home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import urllib.parse
from functools import lru_cache
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_DEFAULT_SECRET_PATH = Path(
    os.environ.get(
        "WLANPI_CORE_SECRET_PATH",
        "/home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin",
    )
)

_SECRET_CACHE: bytes | None = None


def _load_secret(path: Path = _DEFAULT_SECRET_PATH) -> bytes:
    """Load the shared secret from disk. Cached in-process."""
    global _SECRET_CACHE
    if _SECRET_CACHE is not None:
        return _SECRET_CACHE
    try:
        _SECRET_CACHE = path.read_bytes()
        log.debug("Loaded wlanpi-core shared secret from %s", path)
        return _SECRET_CACHE
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read wlanpi-core shared secret from {path}: {exc}"
        ) from exc


def invalidate_secret_cache() -> None:
    """Force reload of the shared secret on next request (e.g. after key rotation)."""
    global _SECRET_CACHE
    _SECRET_CACHE = None


def sign_request(
    method: str,
    path: str,
    query_params: dict | None = None,
    body: bytes = b"",
    secret: bytes | None = None,
) -> str:
    """Compute HMAC-SHA256 signature for a wlanpi-core request.

    Args:
        method: HTTP method (GET, POST, etc.) — uppercase.
        path: URL path (e.g. "/api/v1/system/device/info").
        query_params: Optional dict of query parameters.
        body: Request body bytes.
        secret: Optional override for the shared secret (used in tests).

    Returns:
        Hex digest string to use as X-Request-Signature header value.
    """
    if secret is None:
        secret = _load_secret()

    query_string = (
        urllib.parse.urlencode(query_params) if query_params else ""
    )
    canonical = f"{method.upper()}\n{path}\n{query_string}\n{body.decode('utf-8', errors='replace')}"

    log.debug("HMAC canonical string: %r", canonical)
    return hmac.new(secret, canonical.encode(), hashlib.sha256).hexdigest()


class HmacAuth(httpx.Auth):
    """httpx Auth implementation that adds HMAC signature header."""

    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret  # None means load from disk at request time

    def auth_flow(self, request: httpx.Request):
        secret = self._secret or _load_secret()
        body = request.content or b""
        query_params = dict(request.url.params) or None
        sig = sign_request(
            method=request.method,
            path=request.url.path,
            query_params=query_params,
            body=body,
            secret=secret,
        )
        request.headers["X-Request-Signature"] = sig
        yield request
