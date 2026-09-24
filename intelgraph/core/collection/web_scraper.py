import re
import time
from html.parser import HTMLParser
from typing import Any

import ulid

from intelgraph.core.collection.base import CollectionDocument, CollectionResult, Collector
from intelgraph.core.collection.http_collector import HTTPCollector
from intelgraph.core.evidence import SourceLineage


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False
        if tag in ("p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "th", "td", "div"):
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._text.append(data)

    def get_text(self) -> str:
        raw = "".join(self._text)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


class WebScraperCollector(Collector):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("web_scraper", config)
        self._http = HTTPCollector(config)

    def validate_target(self, target: str) -> bool:
        return self._http.validate_target(target)

    def collect(self, target: str, **kwargs: Any) -> CollectionResult:
        start = time.time()
        result = CollectionResult(collector_name=self._name, target=target)
        collection_id = str(ulid.new())

        http_result = self._http.collect(target, **kwargs)
        if not http_result.success:
            return http_result

        html = http_result.raw_data
        parser = _TextExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass

        text = parser.get_text()
        doc = CollectionDocument(
            content=text,
            content_type="text",
            source_url=target,
            collected_at=http_result.documents[0].collected_at,
            metadata={"url": target, "method": "scrape"},
        )
        result.documents = [doc]
        result.raw_data = html

        lineage = SourceLineage(
            source_id=target,
            source_url=target,
        )
        result.provenance = self.make_provenance(collection_id, target, lineage)
        result.evidence.append(
            self.make_evidence(
                source_url=target,
                content=text[:500],
                source_tier=kwargs.get("source_tier", 2),
                trust_score=kwargs.get("trust_score", 70),
                reliability_score=kwargs.get("reliability_score", 60),
            )
        )
        result.source_metadata = {"url": target, "method": "scrape"}
        result.collection_time_ms = (time.time() - start) * 1000
        result.success = True
        return result
