from typing import Any

from intelgraph.core.collection.api_collector import APICollector
from intelgraph.core.collection.base import CollectionResult, Collector
from intelgraph.core.collection.file_collector import FileCollector
from intelgraph.core.collection.http_collector import HTTPCollector
from intelgraph.core.collection.incremental import IncrementalTracker
from intelgraph.core.collection.rss_collector import RSSCollector
from intelgraph.core.collection.web_scraper import WebScraperCollector
from intelgraph.core.source_registry import SourceRegistryService


class CollectionManager:
    def __init__(
        self,
        storage_backend: Any,
        source_registry: SourceRegistryService | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._storage = storage_backend
        self._config = config or {}
        self._source_registry = source_registry
        self._incremental = IncrementalTracker(storage_backend)
        self._collectors: dict[str, Collector] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(HTTPCollector(self._config.get("http")))
        self.register(WebScraperCollector(self._config.get("web_scraper")))
        self.register(APICollector(self._config.get("api")))
        self.register(FileCollector(self._config.get("file")))
        self.register(RSSCollector(self._config.get("rss")))

    def register(self, collector: Collector) -> None:
        self._collectors[collector.name] = collector

    def get_collector(self, name: str) -> Collector | None:
        return self._collectors.get(name)

    def list_collectors(self) -> list[dict[str, Any]]:
        return [{"name": c.name, "runnable": True} for c in self._collectors.values()]

    def collect(
        self,
        collector_name: str,
        target: str,
        source_tier: int = 2,
        trust_score: int = 70,
        reliability_score: int = 60,
        dry_run: bool = False,
        force: bool = False,
        incremental_ttl_days: int | None = None,
        **kwargs: Any,
    ) -> CollectionResult:
        collector = self._collectors.get(collector_name)
        if collector is None:
            return CollectionResult(
                collector_name=collector_name,
                target=target,
                success=False,
                error=f"Unknown collector: {collector_name}",
            )

        if not collector.validate_target(target):
            return CollectionResult(
                collector_name=collector_name,
                target=target,
                success=False,
                error=f"Invalid target for {collector_name}: {target}",
            )

        if dry_run:
            result = CollectionResult(
                collector_name=collector_name,
                target=target,
                success=True,
            )
            result.source_metadata = collector.dry_run(target)
            return result

        if not force:
            should = self._incremental.should_collect(
                collector_name, target, ttl_days=incremental_ttl_days
            )
            if not should:
                return CollectionResult(
                    collector_name=collector_name,
                    target=target,
                    success=True,
                    error="Skipped (incremental TTL not expired)",
                    source_metadata={"skipped": True, "reason": "incremental_ttl"},
                )

        result = collector.collect(
            target,
            source_tier=source_tier,
            trust_score=trust_score,
            reliability_score=reliability_score,
            **kwargs,
        )

        if result.success and result.provenance:
            self._persist_result(result, collector_name, target)

        return result

    def _persist_result(self, result: CollectionResult, collector_name: str, target: str) -> None:
        if result.provenance:
            target_id = f"col:{collector_name}:{target}"
            self._storage.store_provenance(target_id, result.provenance)

        for ev in result.evidence:
            target_id = f"col:{collector_name}:{target}:{ev.id}"
            self._storage.store_collection_evidence(ev, entity_id=target_id)

        if self._source_registry:
            try:
                url = result.source_metadata.get("url", target)
                existing = None
                for src in self._source_registry.list_sources():
                    if src.get("source_url") == url:
                        existing = src
                        break
                if existing:
                    self._source_registry.record_usage(existing["id"])
                else:
                    self._source_registry.add_source(
                        source_url=url,
                        source_name=collector_name,
                        source_tier=result.evidence[0].source_tier if result.evidence else 3,
                    )
            except Exception:
                pass

        content_hash = ""
        if result.documents:
            content_hash = result.documents[0].content_hash
        self._incremental.mark_collected(collector_name, target, content_hash=content_hash)
