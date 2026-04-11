import os

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

        def delete_password(self, service_name: str, username: str) -> None:
            self._store.pop((service_name, username), None)

    keyring = _FallbackKeyring()

SERVICE_NAME = "bettercode-cli"

def set_api_key(provider: str, api_key: str):
    """Securely store API key using OS keychain to prevent plaintext exposure on disk."""
    if not api_key:
        raise ValueError("API key cannot be empty")
    # Basic safety check to prevent credential injections
    if " " in api_key or "\n" in api_key:
        raise ValueError("Invalid API key format")
    keyring.set_password(SERVICE_NAME, provider.lower(), api_key)

def get_api_key(provider: str) -> str | None:
    """Retrieve API key securely, prioritizing env vars over keyring."""
    # Prioritize environment variables if set (useful for CI or docker securely passing keys)
    env_key = f"{provider.upper()}_API_KEY"
    if env_key in os.environ:
        return os.environ[env_key]
        
    try:
        return keyring.get_password(SERVICE_NAME, provider.lower())
    except Exception:
        return None

def delete_api_key(provider: str):
    try:
        keyring.delete_password(SERVICE_NAME, provider.lower())
    except Exception:
        return
