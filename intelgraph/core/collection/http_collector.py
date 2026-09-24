import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import ulid

from intelgraph.core.collection.base import CollectionDocument, CollectionResult, Collector
from intelgraph.core.collection.retry import ExponentialBackoff, RetryPolicy
from intelgraph.core.evidence import SourceLineage


class HTTPCollector(Collector):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        timeout: int = 30,
        user_agent: str | None = None,
    ) -> None:
        super().__init__("http", config)
        self._timeout = timeout
        self._user_agent = user_agent or "IntelGraph/1.0 (+https://intelgraph.dev)"
        retry_policy = RetryPolicy(
            max_retries=config.get("retries", 3) if config else 3,
            base_delay=1.0,
            max_delay=30.0,
            retryable_exceptions=(
                urllib.error.URLError,
                ConnectionError,
                TimeoutError,
                OSError,
            ),
        )
        self._backoff = ExponentialBackoff(retry_policy)

    def validate_target(self, target: str) -> bool:
        try:
            parsed = urlparse(target)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except Exception:
            return False

    def collect(self, target: str, **kwargs: Any) -> CollectionResult:
        start = time.time()
        result = CollectionResult(collector_name=self._name, target=target)
        collection_id = str(ulid.new())

        if not self.validate_target(target):
            result.success = False
            result.error = f"Invalid URL: {target}"
            return result

        try:
            response_data = self._backoff.execute(
                lambda: self._fetch(target),
                context=f"HTTP GET {target}",
            )
        except Exception as e:
            result.success = False
            result.error = str(e)
            return result

        doc = CollectionDocument(
            content=response_data,
            content_type="html",
            source_url=target,
            collected_at=datetime.now(UTC),
            metadata={"method": "GET", "url": target},
        )
        result.documents.append(doc)
        result.raw_data = response_data

        lineage = SourceLineage(
            source_id=target,
            source_url=target,
        )
        result.provenance = self.make_provenance(collection_id, target, lineage)
        result.evidence.append(
            self.make_evidence(
                source_url=target,
                content=response_data[:500],
                source_tier=kwargs.get("source_tier", 2),
                trust_score=kwargs.get("trust_score", 70),
                reliability_score=kwargs.get("reliability_score", 60),
            )
        )
        result.source_metadata = {"url": target, "method": "GET"}
        result.collection_time_ms = (time.time() - start) * 1000
        return result

    def _fetch(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            data=None,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
