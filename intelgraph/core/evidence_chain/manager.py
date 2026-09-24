from datetime import UTC, datetime
from typing import Any

from intelgraph.core.evidence_chain.base import (
    EvidenceChain,
    EvidenceItem,
    EvidenceStatus,
    SupportType,
    _chain_id,
)
from intelgraph.core.evidence_chain.confidence import ConfidenceComputer
from intelgraph.core.evidence_chain.contradiction import ContradictionDetector
from intelgraph.core.evidence_chain.query import ChainQueryEngine
from intelgraph.core.evidence_chain.storage import EvidenceChainStorage
from intelgraph.core.evidence_chain.validator import ChainValidator


class ChainManager:
    def __init__(self, storage_backend: Any) -> None:
        self._storage = EvidenceChainStorage(storage_backend)
        self._confidence = ConfidenceComputer()
        self._contradiction = ContradictionDetector()
        self._validator = ChainValidator()
        self._query = ChainQueryEngine()

    def initialize(self) -> None:
        self._storage.initialize_tables()

    def get_chain(self, chain_id: str) -> EvidenceChain | None:
        return self._storage.load_chain(chain_id)

    def get_chain_by_entity(self, entity_id: str) -> EvidenceChain | None:
        return self._storage.load_chain_by_entity(entity_id)

    def list_chains(
        self,
        status: str | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        only_contradictions: bool = False,
    ) -> list[EvidenceChain]:
        chains = self._storage.load_all_chains()
        self._query._chains = {c.chain_id: c for c in chains}
        status_enum = EvidenceStatus[status.upper()] if status else None
        return self._query.list_chains(
            status=status_enum,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            has_contradictions=True if only_contradictions else None,
            min_contradiction=1.0 if only_contradictions else None,
        )

    def get_contradictions(self) -> list[EvidenceChain]:
        chains = self._storage.load_all_chains()
        self._query._chains = {c.chain_id: c for c in chains}
        return self._query.get_contradictions()

    def stats(self) -> dict[str, Any]:
        chains = self._storage.load_all_chains()
        self._query._chains = {c.chain_id: c for c in chains}
        return self._query.stats()

    def add_evidence_batch(
        self,
        entity_id: str,
        items: list[tuple[str, str, str, str, float, dict[str, Any]]],
    ) -> tuple[EvidenceChain, list[Any]]:
        existing = self._storage.load_chain_by_entity(entity_id)
        if existing:
            chain = existing
            existing_count = len(chain.evidence)
        else:
            chain = EvidenceChain(entity_id=entity_id)
            chain.chain_id = _chain_id(entity_id)
            chain.created_at = datetime.now(UTC)
            existing_count = 0

        existing_ids = {e.document_id for e in chain.evidence if e.document_id}
        for source_id, document_id, claim, support_type_str, confidence, metadata in items:
            if document_id in existing_ids:
                continue
            item = EvidenceItem(
                source_id=source_id,
                document_id=document_id,
                claim=claim,
                support_type=SupportType[support_type_str.upper()],
                confidence=confidence,
                metadata=metadata or {},
            )
            chain.add_item(item)
            existing_ids.add(document_id)

        chain.recompute_id()
        # Incremental detection: only compare new items with existing items
        contradictions = self._contradiction.detect(chain, existing_count=existing_count)
        self._confidence.compute(chain)
        chain.updated_at = datetime.now(UTC)

        self._storage.save_chain(chain)
        self._storage.save_chain_version(chain, "ADD_EVIDENCE_BATCH")
        if contradictions:
            self._storage.save_contradictions(contradictions)

        return chain, contradictions

    def add_evidence(
        self,
        entity_id: str,
        source_id: str,
        document_id: str,
        claim: str,
        support_type: str = "supports",
        confidence: float = 50.0,
        source_trust: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceChain:
        existing = self._storage.load_chain_by_entity(entity_id)
        if existing:
            chain = existing
            existing_count = len(chain.evidence)
        else:
            chain = EvidenceChain(entity_id=entity_id)
            chain.chain_id = _chain_id(entity_id)
            chain.created_at = datetime.now(UTC)
            existing_count = 0

        item = EvidenceItem(
            source_id=source_id,
            document_id=document_id,
            claim=claim,
            support_type=SupportType[support_type.upper()],
            confidence=confidence,
            metadata=metadata or {},
        )
        chain.add_item(item)
        chain.recompute_id()

        source_trust_map = {source_id: source_trust} if source_trust else {}
        self._confidence.compute(chain, source_trust_map)
        contradictions = self._contradiction.detect(chain, existing_count=existing_count)

        chain.updated_at = datetime.now(UTC)

        self._storage.save_chain(chain)
        self._storage.save_chain_version(chain, "ADD_EVIDENCE")
        if contradictions:
            self._storage.save_contradictions(contradictions)

        return chain

    def recompute_confidence(
        self,
        entity_id: str,
        source_trust_map: dict[str, int] | None = None,
    ) -> EvidenceChain | None:
        chain = self._storage.load_chain_by_entity(entity_id)
        if chain is None:
            return None

        self._confidence.compute(chain, source_trust_map)
        self._contradiction.detect(chain)
        chain.updated_at = datetime.now(UTC)
        chain.version += 1

        self._storage.save_chain(chain)
        self._storage.save_chain_version(chain, "RECOMPUTE")
        return chain

    def update_chain(
        self,
        chain_id: str,
        updates: dict[str, Any],
    ) -> EvidenceChain | None:
        chain = self._storage.load_chain(chain_id)
        if chain is None:
            return None

        if "status" in updates:
            chain.status = EvidenceStatus[updates["status"].upper()]
        if "contradiction_score" in updates:
            chain.contradiction_score = updates["contradiction_score"]

        chain.updated_at = datetime.now(UTC)
        chain.version += 1

        self._storage.save_chain(chain)
        self._storage.save_chain_version(chain, "UPDATE")
        return chain

    def remove_evidence(self, entity_id: str, evidence_id: str) -> EvidenceChain | None:
        chain = self._storage.load_chain_by_entity(entity_id)
        if chain is None:
            return None

        removed = chain.remove_item(evidence_id)
        if not removed:
            return chain

        chain.recompute_id()
        self._confidence.compute(chain)
        self._contradiction.detect(chain)
        chain.updated_at = datetime.now(UTC)

        self._storage.save_chain(chain)
        self._storage.save_chain_version(chain, "REMOVE_EVIDENCE")
        return chain

    def rollback(self, entity_id: str, target_version: int) -> EvidenceChain | None:
        chain = self._storage.load_chain_by_entity(entity_id)
        if chain is None:
            return None

        conn = self._storage._get_conn()
        row = conn.execute(
            "SELECT MAX(version) as max_ver FROM chain_versions WHERE chain_id = ?",
            (chain.chain_id,),
        ).fetchone()
        max_ver = row["max_ver"] if row and row["max_ver"] else 0

        row2 = conn.execute(
            "SELECT data FROM chain_versions WHERE chain_id = ? AND version = ?",
            (chain.chain_id, target_version),
        ).fetchone()
        if row2 is None:
            return None

        import json

        data = json.loads(row2["data"])
        rolled = EvidenceChain(
            chain_id=data["chain_id"],
            entity_id=data["entity_id"],
            confidence=data["confidence"],
            contradiction_score=data["contradiction_score"],
            status=EvidenceStatus[data["status"].upper()],
            version=max_ver + 1,
            source_count=data["source_count"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.now(UTC),
        )
        for ed in data["evidence"]:
            rolled.evidence.append(
                EvidenceItem(
                    evidence_id=ed["evidence_id"],
                    source_id=ed["source_id"],
                    document_id=ed["document_id"],
                    claim=ed["claim"],
                    support_type=SupportType[ed["support_type"].upper()],
                    confidence=ed["confidence"],
                    extracted_at=datetime.fromisoformat(ed["extracted_at"]),
                    metadata=ed.get("metadata", {}),
                )
            )

        self._storage.save_chain(rolled)
        self._storage.save_chain_version(rolled, "ROLLBACK")
        return rolled

    def validate(self, entity_id: str) -> Any:
        chain = self._storage.load_chain_by_entity(entity_id)
        if chain is None:
            return {
                "is_valid": False,
                "errors": ["chain not found"],
                "warnings": [],
                "quality_flags": [],
            }
        report = self._validator.validate(chain)
        return {
            "is_valid": report.is_valid,
            "errors": report.errors,
            "warnings": report.warnings,
            "quality_flags": report.quality_flags,
        }
