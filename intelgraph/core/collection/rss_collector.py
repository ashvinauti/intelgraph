import time
from typing import Any

import ulid

from intelgraph.core.collection.base import CollectionDocument, CollectionResult, Collector
from intelgraph.core.collection.http_collector import HTTPCollector
from intelgraph.core.evidence import SourceLineage


class RSSCollector(Collector):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("rss", config)
        self._http = HTTPCollector(config)

    def validate_target(self, target: str) -> bool:
        return self._http.validate_target(target)

    def collect(self, target: str, **kwargs: Any) -> CollectionResult:
        start = time.time()
        result = CollectionResult(collector_name=self._name, target=target)
        collection_id = str(ulid.new())

        http_result = self._http.collect(
            target,
            source_tier=kwargs.get("source_tier", 2),
            trust_score=kwargs.get("trust_score", 70),
            reliability_score=kwargs.get("reliability_score", 60),
        )
        if not http_result.success:
            return http_result

        raw = http_result.raw_data
        entries = self._parse_feed(raw)

        documents = []
        for entry in entries:
            doc = CollectionDocument(
                content=entry.get("summary", entry.get("title", "")),
                content_type="rss",
                source_url=entry.get("link", target),
                metadata=entry,
            )
            documents.append(doc)
            result.raw_data += (
                f"\n---\nTitle: {entry.get('title', '')}\nLink: {entry.get('link', '')}\n"
            )

        if not documents:
            doc = CollectionDocument(
                content=raw[:2000],
                content_type="xml",
                source_url=target,
                metadata={"raw_feed": True},
            )
            documents.append(doc)

        result.documents = documents
        lineage = SourceLineage(
            source_id=target,
            source_url=target,
        )
        result.provenance = self.make_provenance(collection_id, target, lineage)
        result.evidence.append(
            self.make_evidence(
                source_url=target,
                content=raw[:500],
                source_tier=kwargs.get("source_tier", 2),
                trust_score=kwargs.get("trust_score", 70),
                reliability_score=kwargs.get("reliability_score", 60),
            )
        )
        result.source_metadata = {"url": target, "feed_type": "rss", "entries": len(documents)}
        result.collection_time_ms = (time.time() - start) * 1000
        return result

    @staticmethod
    def _parse_feed(raw: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        from defusedxml import ElementTree as ET

        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return entries

        for item in root.iter("item"):
            entry: dict[str, str] = {}
            for child in item:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                entry[tag] = (child.text or "").strip()
            if entry.get("title") or entry.get("link"):
                entries.append(entry)

        for entry_elem in root.iter("{http://www.w3.org/2005/Atom}entry"):
            entry = {}
            for child in entry_elem:
                tag = child.tag.split("}")[-1]
                entry[tag] = (child.text or "").strip()
            if entry.get("title") or entry.get("id"):
                entries.append(entry)

        return entries
