"""Password hashing (scrypt, stdlib), signed access tokens (JWT, HS256), login throttling."""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the username does not exist, so timing does not reveal valid usernames.
DUMMY_HASH = hash_password("not-a-real-password")


def create_token(username: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict[str, object] | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


class LoginThrottle:
    """Refuse further attempts after too many failures for the same username from one address.

    In-memory and per process: enough for the single-container deployment. Keying on
    username + client address means an attacker cannot lock a real user out from elsewhere.
    """

    def __init__(self, max_failures: int = 5, window_s: float = 300) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self._failures.setdefault(key, deque())
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int | None:
        """Seconds to wait before another attempt, or None if allowed now."""
        now = time.monotonic()
        with self._lock:
            q = self._recent(key, now)
            if len(q) < self.max_failures:
                return None
            return max(1, int(self.window_s - (now - q[0])) + 1)

    def failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._recent(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()
