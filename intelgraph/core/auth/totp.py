from __future__ import annotations

import hashlib
import json
import os
import secrets
from typing import Any

import pyotp

_RECOVERY_CODE_COUNT = 8
_RECOVERY_CODE_BYTES = 6


def generate_recovery_codes() -> list[str]:
    codes: list[str] = []
    for _ in range(_RECOVERY_CODE_COUNT):
        code = secrets.token_hex(_RECOVERY_CODE_BYTES)
        # Format as XXXX-XXXX
        formatted = f"{code[:4].upper()}-{code[4:8].upper()}"
        codes.append(formatted)
    return codes


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _verify_recovery_code(code: str, stored_hash: str) -> bool:
    return _hash_recovery_code(code) == stored_hash


class TOTPManager:
    """Manages TOTP 2FA for users.

    State is stored in a JSON file, keyed by user_id:
      {user_id: {"secret": "...", "recovery_hashes": [...], "enabled": bool}}
    """

    def __init__(self, state_path: str = ""):
        self._state_path = state_path or os.environ.get(
            "INTELGRAPH_TOTP_STATE",
            "/tmp/opencode/totp_state.json",
        )
        self._state: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path) as f:
                    self._state = json.load(f)
        except Exception:
            self._state = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w") as f:
                json.dump(self._state, f, default=str)
        except Exception:
            pass

    def enable(self, user_id: str, issuer: str = "IntelGraph") -> dict[str, Any]:
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=user_id, issuer_name=issuer)
        recovery_codes = generate_recovery_codes()
        recovery_hashes = [_hash_recovery_code(c) for c in recovery_codes]
        self._state[user_id] = {
            "secret": secret,
            "recovery_hashes": recovery_hashes,
            "enabled": True,
            "used_recovery_codes": [],
        }
        self._save()
        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "recovery_codes": recovery_codes,
        }

    def disable(self, user_id: str) -> bool:
        if user_id not in self._state:
            return False
        self._state.pop(user_id, None)
        self._save()
        return True

    def is_enabled(self, user_id: str) -> bool:
        entry = self._state.get(user_id)
        return bool(entry and entry.get("enabled", False))

    def verify(self, user_id: str, code: str) -> bool:
        entry = self._state.get(user_id)
        if not entry or not entry.get("enabled", False):
            return True  # no 2FA = always OK
        secret = entry.get("secret", "")
        if not secret:
            return False

        # TOTP verification
        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):
            return True

        # Recovery code check
        code_normalized = code.strip().upper()
        for _i, stored_hash in enumerate(entry.get("recovery_hashes", [])):
            if _verify_recovery_code(code_normalized, stored_hash):
                if code_normalized not in entry.get("used_recovery_codes", []):
                    used = entry.get("used_recovery_codes", [])
                    used.append(code_normalized)
                    self._state[user_id]["used_recovery_codes"] = used
                    self._save()
                return True
        return False

    def get_provisioning_uri(self, user_id: str, issuer: str = "IntelGraph") -> str | None:
        entry = self._state.get(user_id)
        if not entry or not entry.get("enabled", False):
            return None
        secret = entry.get("secret", "")
        if not secret:
            return None
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=user_id, issuer_name=issuer)

    def get_status(self, user_id: str) -> dict[str, Any]:
        return {
            "enabled": self.is_enabled(user_id),
            "user_id": user_id,
        }
