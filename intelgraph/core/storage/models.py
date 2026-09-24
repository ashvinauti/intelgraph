SCHEMA_VERSION = 1

SCHEMA_SQL = """

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

INSERT INTO schema_version (version) SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    data TEXT NOT NULL,
    confidence_score INTEGER NOT NULL DEFAULT 0,
    trust_score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_latest INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS entity_versions (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    data TEXT NOT NULL,
    confidence_score INTEGER NOT NULL DEFAULT 0,
    trust_score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    operation TEXT NOT NULL,
    PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    data TEXT NOT NULL,
    confidence_score INTEGER NOT NULL DEFAULT 0,
    trust_weight INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    is_latest INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (source_id) REFERENCES entities(id),
    FOREIGN KEY (target_id) REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS relationship_versions (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    data TEXT NOT NULL,
    confidence_score INTEGER NOT NULL DEFAULT 0,
    trust_weight INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    operation TEXT NOT NULL,
    PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    entity_id TEXT,
    entity_type TEXT,
    operation TEXT NOT NULL,
    old_data TEXT,
    new_data TEXT,
    actor TEXT,
    correlation_id TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    collector_name TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    source_lineage TEXT,
    raw_data_hash TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS source_registry (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_tier INTEGER NOT NULL,
    trust_score INTEGER NOT NULL,
    reliability_score INTEGER NOT NULL,
    last_validated TEXT,
    classification TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS canonical_map (
    canonical_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    linked_entity_ids TEXT NOT NULL,
    aliases TEXT,
    highest_confidence INTEGER NOT NULL DEFAULT 0,
    highest_trust INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    label TEXT,
    entity_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_latest ON entities(is_latest);
CREATE INDEX IF NOT EXISTS idx_entity_versions_id ON entity_versions(id);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_relationships_latest ON relationships(is_latest);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE TABLE IF NOT EXISTS collection_evidence (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    source_tier INTEGER NOT NULL,
    trust_score INTEGER NOT NULL DEFAULT 50,
    reliability_score INTEGER NOT NULL DEFAULT 50
);

CREATE INDEX IF NOT EXISTS idx_provenance_entity ON provenance(entity_id);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_collection_evidence_entity ON collection_evidence(entity_id);
"""

# PostgreSQL-compatible variant (uses TEXT for all, no INTEGER BOOLEAN tricks)
SCHEMA_SQL_PG = SCHEMA_SQL.replace("INTEGER NOT NULL DEFAULT", "INTEGER DEFAULT")
# Make is_latest use SMALLINT for PG
SCHEMA_SQL_PG = SCHEMA_SQL_PG.replace(
    "is_latest INTEGER NOT NULL DEFAULT 1",
    "is_latest SMALLINT NOT NULL DEFAULT 1",
)
