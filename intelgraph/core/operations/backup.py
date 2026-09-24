from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BackupResult:
    path: str
    timestamp: str
    size_bytes: int
    checksum: str
    backend: str
    success: bool
    error: str = ""


class BackupManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        storage = config.get("storage", {})
        self._backend = storage.get("backend", "sqlite")
        self._db_path = storage.get("path", "intelgraph.db")
        backup_cfg = config.get("backup", {})
        self._output_dir = Path(backup_cfg.get("output_dir", "./backups"))
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, label: str = "") -> BackupResult:
        ts = datetime.now(UTC)
        ts_str = ts.strftime("%Y%m%dT%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label) if label else ""
        suffix = f"_{safe_label}" if safe_label else ""
        filename = f"intelgraph_{self._backend}_{ts_str}{suffix}.backup"

        if self._backend == "sqlite":
            return self._backup_sqlite(filename, ts)
        elif self._backend == "postgres":
            return self._backup_postgres(filename, ts)
        else:
            return BackupResult(
                path="",
                timestamp=ts.isoformat(),
                size_bytes=0,
                checksum="",
                backend=self._backend,
                success=False,
                error=f"Unsupported backend: {self._backend}",
            )

    def _backup_sqlite(self, filename: str, ts: datetime) -> BackupResult:
        src_path = Path(self._db_path)
        if not src_path.exists():
            return BackupResult(
                path="",
                timestamp=ts.isoformat(),
                size_bytes=0,
                checksum="",
                backend="sqlite",
                success=False,
                error=f"Database not found: {self._db_path}",
            )
        dst_path = self._output_dir / filename
        try:
            shutil.copy2(str(src_path), str(dst_path))
            size = dst_path.stat().st_size
            checksum = self._checksum(dst_path)
            return BackupResult(
                path=str(dst_path),
                timestamp=ts.isoformat(),
                size_bytes=size,
                checksum=checksum,
                backend="sqlite",
                success=True,
            )
        except Exception as exc:
            return BackupResult(
                path="",
                timestamp=ts.isoformat(),
                size_bytes=0,
                checksum="",
                backend="sqlite",
                success=False,
                error=str(exc),
            )

    def _backup_postgres(self, filename: str, ts: datetime) -> BackupResult:
        dst_path = self._output_dir / filename
        storage_cfg = self._config.get("storage", {})
        pg_dump = self._config.get("backup", {}).get("pg_dump_path", "pg_dump")
        dbname = storage_cfg.get("dbname", "intelgraph")
        user = storage_cfg.get("user", "intelgraph")
        host = storage_cfg.get("host", "localhost")
        port = str(storage_cfg.get("port", 5432))
        try:
            cmd = [
                pg_dump,
                "--no-password",
                "--format=custom",
                f"--file={dst_path}",
                f"--host={host}",
                f"--port={port}",
                f"--username={user}",
                dbname,
            ]
            env = dict(os.environ)
            if "password" in storage_cfg:
                env["PGPASSWORD"] = storage_cfg["password"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if result.returncode != 0:
                return BackupResult(
                    path="",
                    timestamp=ts.isoformat(),
                    size_bytes=0,
                    checksum="",
                    backend="postgres",
                    success=False,
                    error=result.stderr.strip(),
                )
            size = dst_path.stat().st_size
            checksum = self._checksum(dst_path)
            return BackupResult(
                path=str(dst_path),
                timestamp=ts.isoformat(),
                size_bytes=size,
                checksum=checksum,
                backend="postgres",
                success=True,
            )
        except Exception as exc:
            return BackupResult(
                path="",
                timestamp=ts.isoformat(),
                size_bytes=0,
                checksum="",
                backend="postgres",
                success=False,
                error=str(exc),
            )

    def verify_backup(self, backup_path: str) -> dict[str, Any]:
        path = Path(backup_path)
        if not path.exists():
            return {"path": backup_path, "valid": False, "error": "File not found"}
        try:
            stored_checksum = ""
            checksum_file = path.with_suffix(path.suffix + ".sha256")
            if checksum_file.exists():
                stored_checksum = checksum_file.read_text().strip()
        except Exception:
            pass
        actual_checksum = self._checksum(path)
        valid = not stored_checksum or actual_checksum == stored_checksum
        return {
            "path": backup_path,
            "valid": valid,
            "size_bytes": path.stat().st_size,
            "checksum": actual_checksum,
            "stored_checksum": stored_checksum,
        }

    def _checksum(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def metadata(result: BackupResult) -> dict[str, Any]:
        return {
            "path": result.path,
            "timestamp": result.timestamp,
            "size_bytes": result.size_bytes,
            "checksum": result.checksum,
            "backend": result.backend,
            "success": result.success,
            "error": result.error,
        }
