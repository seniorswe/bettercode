import json
import os
from urllib import request

try:
    import keyring
except ImportError:  # pragma: no cover - depends on local environment
    class _FallbackKeyring:
        def __init__(self):
            self._store: dict[tuple[str, str], str] = {}

        def set_password(self, service_name: str, username: str, password: str) -> None:
            self._store[(service_name, username)] = password

        def get_password(self, service_name: str, username: str) -> str | None:
            return self._store.get((service_name, username))

    keyring = _FallbackKeyring()

SERVICE_NAME = "bettercode-cli-sub"
PROXY_API_BASE_ENV = "BETTERCODE_PROXY_API_BASE"
PROXY_TOKEN_ENV = "BETTERCODE_PROXY_TOKEN"


def _proxy_api_base() -> str:
    return os.environ.get(PROXY_API_BASE_ENV, "").rstrip("/")


def _proxy_request(path: str, payload: dict) -> dict:
    base = _proxy_api_base()
    if not base:
        return {}

    req = request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10.0) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

def login(username: str, password: str) -> bool:
    """Authenticate against a real BetterCode proxy if configured."""
    if not username or not password:
        return False

    try:
        payload = _proxy_request("/login", {"username": username, "password": password})
    except Exception:
        return False

    token = payload.get("token") or payload.get("proxy_token") or ""
    if not isinstance(token, str) or not token.strip():
        return False

    keyring.set_password(SERVICE_NAME, "proxy_token", token.strip())
    return True

def get_proxy_token() -> str | None:
    """Gets the proxy token for subscription users who don't bring keys."""
    env_token = os.environ.get(PROXY_TOKEN_ENV)
    if env_token:
        return env_token

    try:
        return keyring.get_password(SERVICE_NAME, "proxy_token")
    except Exception:
        return None
