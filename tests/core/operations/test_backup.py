import os
import tempfile

from intelgraph.core.operations.backup import BackupManager


class TestBackupManager:
    def test_sqlite_backup_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, "w") as f:
                f.write("sqlite db content")
            backup_dir = os.path.join(tmp, "backups")
            bm = BackupManager(
                {
                    "storage": {"backend": "sqlite", "path": db_path},
                    "backup": {"output_dir": backup_dir},
                }
            )
            result = bm.create_backup(label="test_backup")
            assert result.success is True
            assert result.backend == "sqlite"
            assert result.size_bytes > 0
            assert os.path.exists(result.path)
            assert result.path.endswith(".backup")

    def test_sqlite_backup_missing_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            bm = BackupManager(
                {
                    "storage": {"backend": "sqlite", "path": "/nonexistent/db.sqlite"},
                    "backup": {"output_dir": tmp},
                }
            )
            result = bm.create_backup()
            assert result.success is False
            assert "not found" in result.error

    def test_verify_backup_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            with open(db_path, "w") as f:
                f.write("data")
            bm = BackupManager(
                {
                    "storage": {"backend": "sqlite", "path": db_path},
                    "backup": {"output_dir": tmp},
                }
            )
            result = bm.create_backup()
            assert result.success is True
            verification = bm.verify_backup(result.path)
            assert verification["valid"] is True
            assert verification["size_bytes"] == result.size_bytes
            assert verification["checksum"] == result.checksum

    def test_metadata_structure(self):
        from intelgraph.core.operations.backup import BackupResult

        result = BackupResult(
            path="/tmp/backup.db",
            timestamp="2025-01-01T00:00:00",
            size_bytes=1024,
            checksum="abc123",
            backend="sqlite",
            success=True,
        )
        meta = BackupManager.metadata(result)
        assert meta["path"] == "/tmp/backup.db"
        assert meta["size_bytes"] == 1024
        assert meta["checksum"] == "abc123"
        assert meta["success"] is True

    def test_verify_backup_not_found(self):
        bm = BackupManager(
            {
                "storage": {"backend": "sqlite", "path": "test.db"},
                "backup": {"output_dir": "/tmp"},
            }
        )
        verification = bm.verify_backup("/nonexistent/backup.db")
        assert verification["valid"] is False
        assert "not found" in verification["error"]
