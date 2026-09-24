import json
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import ulid

from intelgraph.core.collection.base import CollectionDocument, CollectionResult, Collector
from intelgraph.core.collection.http_collector import HTTPCollector
from intelgraph.core.evidence import SourceLineage


class APICollector(Collector):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("api", config)
        self._http = HTTPCollector(config)
        self._base_url = (config or {}).get("base_url", "")

    def validate_target(self, target: str) -> bool:
        try:
            parsed = urlparse(target)
            return bool(parsed.netloc) or bool(self._base_url)
        except Exception:
            return False

    def collect(self, target: str, **kwargs: Any) -> CollectionResult:
        start = time.time()
        result = CollectionResult(collector_name=self._name, target=target)
        collection_id = str(ulid.new())

        if self._base_url and not target.startswith("http"):
            target = self._base_url.rstrip("/") + "/" + target.lstrip("/")

        params = kwargs.get("params", {})
        if params:
            target += "?" + urlencode(params)

        kwargs.get("headers", {})
        http_result = self._http.collect(
            target,
            source_tier=kwargs.get("source_tier", 2),
            trust_score=kwargs.get("trust_score", 70),
            reliability_score=kwargs.get("reliability_score", 60),
        )
        if not http_result.success:
            return http_result

        try:
            parsed = json.loads(http_result.raw_data)
            content = json.dumps(parsed, indent=2)
        except (json.JSONDecodeError, ValueError):
            content = http_result.raw_data
            parsed = {}

        doc = CollectionDocument(
            content=content,
            content_type="json",
            source_url=target,
            collected_at=http_result.documents[0].collected_at,
            metadata={"url": target, "api": True, "parsed": bool(parsed)},
        )
        result.documents = [doc]
        result.raw_data = http_result.raw_data

        lineage = SourceLineage(
            source_id=target,
            source_url=target,
        )
        result.provenance = self.make_provenance(collection_id, target, lineage)
        result.evidence.append(
            self.make_evidence(
                source_url=target,
                content=content[:500],
                source_tier=kwargs.get("source_tier", 2),
                trust_score=kwargs.get("trust_score", 70),
                reliability_score=kwargs.get("reliability_score", 60),
            )
        )
        result.source_metadata = {"url": target, "method": "API"}
        result.collection_time_ms = (time.time() - start) * 1000
        return result
