from intelgraph.core.storage import SQLiteBackend
from intelgraph.core.verification.manager import VerificationManager


def _make_manager() -> VerificationManager:
    backend = SQLiteBackend(":memory:")
    backend.connect()
    backend.initialize_schema()
    mgr = VerificationManager(backend)
    mgr.initialize()
    return mgr


def test_manager_initialize():
    mgr = _make_manager()
    assert mgr._storage is not None


def test_get_verification_not_found():
    mgr = _make_manager()
    record = mgr.get_verification("entity-123")
    assert record is None


def test_list_verifications_empty():
    mgr = _make_manager()
    records = mgr.list_verifications()
    assert records == []


def test_stats_empty():
    mgr = _make_manager()
    stats = mgr.stats()
    assert stats["total"] == 0


def test_get_high_impact_unverified_empty():
    mgr = _make_manager()
    assert mgr.get_high_impact_unverified() == []


def test_get_history_not_found():
    mgr = _make_manager()
    history = mgr.get_history("entity-123")
    assert history == []


def test_get_history_for_existing():
    mgr = _make_manager()

    # Create a chain with evidence first
    from intelgraph.core.evidence_chain.manager import ChainManager

    chain_mgr = ChainManager(mgr._chain_mgr._storage._backend)
    chain_mgr.initialize()

    chain_mgr.add_evidence(
        "person-123",
        source_id="https://example.com/article1",
        document_id="doc-001",
        claim="Person is CEO of Acme",
        support_type="supports",
        confidence=85.0,
    )

    # Now recompute
    record = mgr.recompute("person-123")
    assert record is not None

    history = mgr.get_history("person-123")
    assert len(history) == 1
    assert history[0]["operation"] == "RECOMPUTE"


def test_recompute_all():
    mgr = _make_manager()
    count = mgr.recompute_all()
    assert count == 0


def test_initialization_creates_tables():
    backend = SQLiteBackend(":memory:")
    backend.connect()
    backend.initialize_schema()
    mgr = VerificationManager(backend)
    mgr.initialize()

    conn = mgr._storage._get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t["name"] for t in tables]
    assert "verifications" in table_names
    assert "verification_history" in table_names
    assert "evidence_chains" in table_names
    assert "review_records" in table_names
