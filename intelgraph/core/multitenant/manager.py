from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

MULTITENANT_SCHEMA_VERSION = "2.0"


def _hash_api_key(api_key: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", api_key.encode(), salt.encode(), 600000)
    return f"{salt}:{dk.hex()}"


def _verify_api_key(api_key: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", api_key.encode(), salt.encode(), 600000)
    return dk.hex() == expected


def _generate_api_key() -> str:
    return "igt_" + secrets.token_hex(24)


_DEFAULT_TENANT_CONFIG: dict[str, Any] = {
    "thresholds": {
        "c2_detection": {
            "enabled": True,
            "metric_key": "overall_confidence",
            "max": 0.4,
            "severity": "critical",
        },
        "attack_path_found": {
            "enabled": True,
            "metric_key": "attack_path_found",
            "max": 0,
            "severity": "high",
        },
    },
    "playbooks": {
        "auto_apply": True,
        "default_playbooks": [
            "c2_ip_detected",
            "high_risk_cve",
            "ransomware_cve",
            "malware_domain",
        ],
    },
    "rate_limits": {
        "read": 500,
        "write": 100,
        "auth": 20,
        "health": 1000,
    },
}


_GRACE_PERIOD_HOURS = int(os.environ.get("INTELGRAPH_KEY_GRACE_HOURS", "24"))


@dataclass
class Tenant:
    tenant_id: str
    name: str
    api_key_hash: str = ""
    created_at: str = ""
    is_active: bool = True
    config: dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_TENANT_CONFIG))
    previous_key_hash: str = ""
    key_rotated_at: str = ""
    rotation_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, include_key: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "created_at": self.created_at,
            "is_active": self.is_active,
            "config": self.config,
            "key_rotated_at": self.key_rotated_at,
            "rotation_count": len(self.rotation_history),
        }
        if include_key:
            d["api_key_hash"] = self.api_key_hash
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tenant:
        cfg = data.get("config", {})
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except (json.JSONDecodeError, TypeError):
                cfg = dict(_DEFAULT_TENANT_CONFIG)
        rh = data.get("rotation_history", [])
        if isinstance(rh, str):
            try:
                rh = json.loads(rh)
            except (json.JSONDecodeError, TypeError):
                rh = []
        return cls(
            tenant_id=data["tenant_id"],
            name=data["name"],
            api_key_hash=data.get("api_key_hash", ""),
            created_at=data.get("created_at", ""),
            is_active=bool(data.get("is_active", True)),
            config=cfg,
            previous_key_hash=data.get("previous_key_hash", ""),
            key_rotated_at=data.get("key_rotated_at", ""),
            rotation_history=rh,
        )

    def is_key_in_grace_period(self) -> bool:
        if not self.key_rotated_at:
            return False
        try:
            rotated = datetime.fromisoformat(self.key_rotated_at)
            return datetime.now(UTC) - rotated < timedelta(hours=_GRACE_PERIOD_HOURS)
        except ValueError:
            return False


class TenantManager:
    def __init__(self, db_path: str = "") -> None:
        self._tenants: dict[str, Tenant] = {}
        self._usage: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._db_path = db_path or os.environ.get("INTELGRAPH_DB_PATH", "intelgraph.db")
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id   TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                api_key_hash TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                config      TEXT NOT NULL DEFAULT '{}',
                previous_key_hash TEXT NOT NULL DEFAULT '',
                key_rotated_at TEXT NOT NULL DEFAULT '',
                rotation_history TEXT NOT NULL DEFAULT '[]'
            )
        """)
        # Migrate: add columns if missing
        for col, default in [
            ("previous_key_hash", ""),
            ("key_rotated_at", ""),
            ("rotation_history", "[]"),
        ]:
            try:
                conn.execute(
                    f"ALTER TABLE tenants ADD COLUMN {col} TEXT NOT NULL DEFAULT '{default}'"
                )
            except Exception:
                pass
        conn.commit()
        conn.close()
        self._load_from_db()

    def _load_from_db(self) -> None:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM tenants").fetchall()
        for r in rows:
            tenant = Tenant.from_dict(dict(r))
            self._tenants[tenant.tenant_id] = tenant
        conn.close()

    def _save_to_db(self, tenant: Tenant) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO tenants
               (tenant_id, name, api_key_hash, created_at, is_active, config,
                previous_key_hash, key_rotated_at, rotation_history)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tenant.tenant_id,
                tenant.name,
                tenant.api_key_hash,
                tenant.created_at,
                1 if tenant.is_active else 0,
                json.dumps(tenant.config),
                tenant.previous_key_hash,
                tenant.key_rotated_at,
                json.dumps(tenant.rotation_history),
            ),
        )
        conn.commit()
        conn.close()

    def _remove_from_db(self, tenant_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM tenants WHERE tenant_id = ?", (tenant_id,))
        conn.commit()
        conn.close()

    def create_tenant(self, name: str, config: dict[str, Any] | None = None) -> tuple[Tenant, str]:
        tenant_id = "tnt_" + uuid.uuid4().hex[:12]
        api_key = _generate_api_key()
        api_key_hash = _hash_api_key(api_key)
        now = datetime.now(UTC).isoformat()
        cfg = dict(_DEFAULT_TENANT_CONFIG)
        if config:
            cfg.update(config)
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            api_key_hash=api_key_hash,
            created_at=now,
            is_active=True,
            config=cfg,
        )
        self._tenants[tenant_id] = tenant
        self._save_to_db(tenant)
        return tenant, api_key

    def get(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def get_by_api_key(self, api_key: str) -> Tenant | None:
        for tenant in self._tenants.values():
            if _verify_api_key(api_key, tenant.api_key_hash):
                return tenant
            # Check previous key during grace period
            if tenant.previous_key_hash and _verify_api_key(api_key, tenant.previous_key_hash):
                if tenant.is_key_in_grace_period():
                    return tenant
        return None

    def verify_api_key(self, api_key: str) -> Tenant | None:
        return self.get_by_api_key(api_key)

    def delete_tenant(self, tenant_id: str) -> bool:
        if tenant_id not in self._tenants:
            return False
        del self._tenants[tenant_id]
        self._remove_from_db(tenant_id)
        return True

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    def update_config(self, tenant_id: str, config: dict[str, Any]) -> Tenant | None:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None
        tenant.config.update(config)
        self._save_to_db(tenant)
        return tenant

    def rotate_api_key(self, tenant_id: str, rotated_by: str = "") -> tuple[str, str] | None:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None
        now = datetime.now(UTC).isoformat()
        # Move current key to previous_key_hash for grace period
        if tenant.api_key_hash:
            tenant.previous_key_hash = tenant.api_key_hash
        tenant.key_rotated_at = now
        # Generate new key
        new_key = _generate_api_key()
        tenant.api_key_hash = _hash_api_key(new_key)
        # Record rotation history
        tenant.rotation_history.append(
            {
                "rotated_at": now,
                "rotated_by": rotated_by or "api",
            }
        )
        self._save_to_db(tenant)
        return tenant_id, new_key

    def record_usage(self, tenant_id: str, metric: str, value: float) -> None:
        self._usage[tenant_id][metric] += value

    def check_quota(self, tenant_id: str, metric: str, limit: float) -> bool:
        used = self._usage[tenant_id].get(metric, 0)
        return used < limit

    def quota_usage(self, tenant_id: str) -> dict[str, float]:
        return dict(self._usage.get(tenant_id, {}))

    def enforce_isolation(self, data: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        data["_tenant_id"] = tenant_id
        return data

    def verify_isolation(self, data: dict[str, Any], tenant_id: str) -> bool:
        return data.get("_tenant_id") == tenant_id

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}
        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "created_at": tenant.created_at,
            "is_active": tenant.is_active,
            "usage": dict(self._usage.get(tenant_id, {})),
            "config": tenant.config,
        }


class MultiTenantRouter:
    """Legacy router class for backward compatibility with Phase 28 tests."""

    def __init__(self) -> None:
        self._routes: dict[str, str] = {}

    def register_route(self, tenant_id: str, route: str) -> None:
        self._routes[tenant_id] = route

    def route(self, tenant_id: str) -> str | None:
        return self._routes.get(tenant_id)

    def partition_key(self, tenant_id: str, base_key: str) -> str:
        return f"{tenant_id}:{base_key}"


# Global singleton accessor
_tenant_manager: TenantManager | None = None


def get_tenant_manager(db_path: str = "") -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager(db_path)
    return _tenant_manager


def reset_tenant_manager() -> None:
    global _tenant_manager
    _tenant_manager = None
