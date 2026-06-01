import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from flask import request, session
from werkzeug.security import check_password_hash, generate_password_hash

from app.config import (
    API_TOKEN,
    AUTH_PASSWORD,
    AUTH_PASSWORD_HASH,
    AUTH_USERNAME,
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
)

_CSRF_SESSION_KEY = "_csrf_token"
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))
_failed_logins = defaultdict(deque)
_blocked_until = {}
_login_lock = threading.Lock()


def get_csrf_token() -> str:
    token = session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return token


def is_csrf_token_valid() -> bool:
    expected = session.get(_CSRF_SESSION_KEY, "")
    supplied = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def is_api_token_valid() -> bool:
    authorization = request.headers.get("Authorization", "")
    scheme, _, supplied_token = authorization.partition(" ")
    return bool(
        API_TOKEN
        and scheme.lower() == "bearer"
        and supplied_token
        and hmac.compare_digest(API_TOKEN, supplied_token)
    )


def is_safe_redirect_target(target: str) -> bool:
    if not target:
        return False
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/") and not target.startswith("//")


def verify_credentials(username: str, password: str) -> bool:
    username_valid = hmac.compare_digest(username, AUTH_USERNAME)
    if AUTH_PASSWORD_HASH:
        password_valid = check_password_hash(AUTH_PASSWORD_HASH, password)
    elif AUTH_PASSWORD:
        password_valid = hmac.compare_digest(password, AUTH_PASSWORD)
    else:
        password_valid = check_password_hash(_DUMMY_PASSWORD_HASH, password)
    return username_valid and password_valid


def _login_key(username: str) -> str:
    return f"{request.remote_addr or 'unknown'}:{username.casefold()[:128]}"


def is_login_blocked(username: str) -> bool:
    now = time.monotonic()
    key = _login_key(username)
    with _login_lock:
        blocked_until = _blocked_until.get(key, 0)
        if blocked_until > now:
            return True
        _blocked_until.pop(key, None)
        return False


def register_login_failure(username: str) -> None:
    now = time.monotonic()
    key = _login_key(username)
    with _login_lock:
        failures = _failed_logins[key]
        while failures and failures[0] <= now - LOGIN_WINDOW_SECONDS:
            failures.popleft()
        failures.append(now)
        if len(failures) >= LOGIN_MAX_ATTEMPTS:
            _blocked_until[key] = now + LOGIN_LOCKOUT_SECONDS
            failures.clear()


def clear_login_failures(username: str) -> None:
    key = _login_key(username)
    with _login_lock:
        _failed_logins.pop(key, None)
        _blocked_until.pop(key, None)
