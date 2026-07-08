"""Autenticación con scrypt + sesión Flask (sin contraseña en texto plano)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SECRETS_DIR = BASE_DIR / "secrets"
AUTH_FILE = SECRETS_DIR / "auth.json"
SECRET_FILE = SECRETS_DIR / "flask_secret.txt"

# Anti fuerza bruta en memoria (por proceso)
_fail_log: dict[str, list[float]] = {}
MAX_FAILS = 5
LOCK_SECONDS = 300


def ensure_secrets() -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")


def load_flask_secret() -> str:
    ensure_secrets()
    return SECRET_FILE.read_text(encoding="utf-8").strip()


def load_auth() -> dict:
    if not AUTH_FILE.exists():
        raise RuntimeError(
            "Falta secrets/auth.json. Crea el archivo con usuario y hash scrypt."
        )
    with AUTH_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _scrypt_hash(password: str, salt: bytes, *, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
        maxmem=64 * 1024 * 1024,
    )


def verify_credentials(username: str, password: str) -> bool:
    """Compara usuario y contraseña de forma constante en el tiempo relativo."""
    try:
        auth = load_auth()
    except Exception:
        return False

    expected_user = str(auth.get("username") or "")
    user_ok = hmac.compare_digest(
        (username or "").strip().encode("utf-8"),
        expected_user.encode("utf-8"),
    )

    try:
        salt = base64.b64decode(auth["password_salt"])
        expected = base64.b64decode(auth["password_hash"])
        n = int(auth.get("n", 16384))
        r = int(auth.get("r", 8))
        p = int(auth.get("p", 1))
        dklen = int(auth.get("dklen", 64))
        got = _scrypt_hash(password or "", salt, n=n, r=r, p=p, dklen=dklen)
        pass_ok = hmac.compare_digest(got, expected)
    except Exception:
        pass_ok = False

    return bool(user_ok and pass_ok)


def client_key() -> str:
    # IP + User-Agent reducido
    from flask import request

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    ua = (request.headers.get("User-Agent") or "")[:80]
    return f"{ip}|{ua}"


def is_locked(key: str | None = None) -> bool:
    key = key or client_key()
    now = time.time()
    fails = [t for t in _fail_log.get(key, []) if now - t < LOCK_SECONDS]
    _fail_log[key] = fails
    return len(fails) >= MAX_FAILS


def register_fail(key: str | None = None) -> None:
    key = key or client_key()
    _fail_log.setdefault(key, []).append(time.time())


def clear_fails(key: str | None = None) -> None:
    key = key or client_key()
    _fail_log.pop(key, None)


def lock_remaining(key: str | None = None) -> int:
    key = key or client_key()
    now = time.time()
    fails = [t for t in _fail_log.get(key, []) if now - t < LOCK_SECONDS]
    if len(fails) < MAX_FAILS:
        return 0
    oldest_in_window = min(fails)
    return max(0, int(LOCK_SECONDS - (now - oldest_in_window)))
