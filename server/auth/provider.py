from __future__ import annotations

import base64
import json
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from server.utils.settings import get_settings


class ApiKeySource(str, Enum):
    ENV = "ANTHROPIC_API_KEY"
    API_KEY_HELPER = "apiKeyHelper"
    MANAGED_KEY = "/login managed key"
    NONE = "none"


class ApiKeyResult:
    def __init__(self, key: Optional[str], source: ApiKeySource) -> None:
        self.key = key
        self.source = source


class ApiKeyStore:
    _SALT_FILE = ".key_salt"
    _KEY_FILE = ".secure_keys"
    _ITERATIONS = 600_000

    def __init__(self) -> None:
        settings = get_settings()
        self._config_dir: Path = settings.config_dir

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self._ITERATIONS,
        )
        machine_id = (
            os.environ.get("COMPUTERNAME", "")
            or os.environ.get("HOSTNAME", "")
            or os.uname().nodename
        )
        return base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))

    def _get_key(self) -> bytes:
        salt_path = self._config_dir / self._SALT_FILE
        if salt_path.exists():
            salt = salt_path.read_bytes()
        else:
            salt = os.urandom(16)
            self._config_dir.mkdir(parents=True, exist_ok=True)
            salt_path.write_bytes(salt)
        return self._derive_key(salt)

    def save(self, vendor: str, api_key: str) -> None:
        key_path = self._config_dir / self._KEY_FILE
        self._config_dir.mkdir(parents=True, exist_ok=True)

        data: dict[str, str] = {}
        if key_path.exists():
            try:
                fernet = Fernet(self._get_key())
                content = key_path.read_bytes()
                if content:
                    decrypted = fernet.decrypt(content)
                    data = json.loads(decrypted)
            except Exception:
                data = {}

        data[vendor] = api_key
        fernet = Fernet(self._get_key())
        encrypted = fernet.encrypt(json.dumps(data).encode())
        key_path.write_bytes(encrypted)
        if sys.platform != "win32":
            os.chmod(key_path, 0o600)

    def load(self, vendor: str) -> Optional[str]:
        key_path = self._config_dir / self._KEY_FILE
        if not key_path.exists():
            return None
        try:
            fernet = Fernet(self._get_key())
            content = key_path.read_bytes()
            if not content:
                return None
            decrypted = fernet.decrypt(content)
            data = json.loads(decrypted)
            return data.get(vendor)
        except Exception:
            return None

    def delete(self, vendor: str) -> None:
        key_path = self._config_dir / self._KEY_FILE
        if not key_path.exists():
            return
        try:
            fernet = Fernet(self._get_key())
            content = key_path.read_bytes()
            if not content:
                return
            decrypted = fernet.decrypt(content)
            data = json.loads(decrypted)
            data.pop(vendor, None)
            encrypted = fernet.encrypt(json.dumps(data).encode())
            key_path.write_bytes(encrypted)
        except Exception:
            pass


_api_key_store: Optional[ApiKeyStore] = None


def get_api_key_store() -> ApiKeyStore:
    global _api_key_store
    if _api_key_store is None:
        _api_key_store = ApiKeyStore()
    return _api_key_store


def reset_api_key_store_for_testing() -> None:
    global _api_key_store
    _api_key_store = None


def is_valid_api_key(api_key: str) -> bool:
    import re

    return bool(re.match(r"^[a-zA-Z0-9\-_]+$", api_key))


def get_anthropic_api_key_with_source() -> ApiKeyResult:
    settings = get_settings()
    api_key_env = settings.anthropic_api_key

    if api_key_env:
        return ApiKeyResult(key=api_key_env, source=ApiKeySource.ENV)

    api_key_helper = os.environ.get("API_KEY_HELPER")
    if api_key_helper:
        return ApiKeyResult(key=api_key_helper, source=ApiKeySource.API_KEY_HELPER)

    store = get_api_key_store()
    stored_key = store.load("anthropic")
    if stored_key:
        return ApiKeyResult(key=stored_key, source=ApiKeySource.MANAGED_KEY)

    return ApiKeyResult(key=None, source=ApiKeySource.NONE)


def get_anthropic_api_key() -> Optional[str]:
    return get_anthropic_api_key_with_source().key


def get_openai_api_key() -> Optional[str]:
    settings = get_settings()
    if settings.openai_api_key:
        return settings.openai_api_key
    return get_api_key_store().load("openai")


def get_deepseek_api_key() -> Optional[str]:
    settings = get_settings()
    if settings.deepseek_api_key:
        return settings.deepseek_api_key
    return get_api_key_store().load("deepseek")


def get_google_api_key() -> Optional[str]:
    settings = get_settings()
    if settings.google_api_key:
        return settings.google_api_key
    return get_api_key_store().load("google")


def save_api_key(vendor: str, api_key: str) -> None:
    if not is_valid_api_key(api_key):
        raise ValueError(
            "Invalid API key format. "
            "API key must contain only alphanumeric characters, dashes, and underscores."
        )
    get_api_key_store().save(vendor, api_key)


def remove_api_key(vendor: str) -> None:
    get_api_key_store().delete(vendor)


def reset_api_key_store_for_testing() -> None:
    global _api_key_store
    _api_key_store = None
