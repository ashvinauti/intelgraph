import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ulid

from intelgraph.core.collection.base import CollectionDocument, CollectionResult, Collector
from intelgraph.core.evidence import SourceLineage


class FileCollector(Collector):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("file", config)
        self._base_path = Path(config.get("base_path", ".")) if config else Path(".")

    def validate_target(self, target: str) -> bool:
        path = self._resolve(target)
        return path.exists() and path.is_file()

    def collect(self, target: str, **kwargs: Any) -> CollectionResult:
        start = time.time()
        result = CollectionResult(collector_name=self._name, target=target)
        collection_id = str(ulid.new())

        path = self._resolve(target)
        if not path.exists():
            result.success = False
            result.error = f"File not found: {path}"
            return result
        if not path.is_file():
            result.success = False
            result.error = f"Not a file: {path}"
            return result

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result.success = False
            result.error = f"Read error: {e}"
            return result

        ext = path.suffix.lower()
        content_type = {
            ".json": "json",
            ".html": "html",
            ".htm": "html",
            ".xml": "xml",
            ".csv": "csv",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".txt": "text",
        }.get(ext, "binary")

        doc = CollectionDocument(
            content=raw,
            content_type=content_type,
            source_url=str(path),
            collected_at=datetime.now(UTC),
            metadata={"path": str(path), "size": len(raw), "ext": ext},
        )
        result.documents = [doc]
        result.raw_data = raw

        lineage = SourceLineage(
            source_id=str(path),
            source_url=str(path),
        )
        result.provenance = self.make_provenance(collection_id, target, lineage)
        result.evidence.append(
            self.make_evidence(
                source_url=str(path),
                content=raw[:500],
                source_tier=kwargs.get("source_tier", 2),
                trust_score=kwargs.get("trust_score", 70),
                reliability_score=kwargs.get("reliability_score", 60),
            )
        )
        result.source_metadata = {"path": str(path), "size": len(raw)}
        result.collection_time_ms = (time.time() - start) * 1000
        return result

    def _resolve(self, target: str) -> Path:
        p = Path(target)
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self._base_path / p).resolve()
        # Prevent path traversal outside the base directory
        base_resolved = self._base_path.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            resolved = base_resolved / p.name
        return resolved
