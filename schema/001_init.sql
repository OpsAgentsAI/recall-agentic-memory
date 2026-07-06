-- Recall — CockroachDB schema (episodic + semantic memory tiers)
-- Requires CockroachDB 25.2+ (VECTOR type + vector indexes).
-- Titan Embeddings v2 default dimensionality: 1024.

CREATE TABLE IF NOT EXISTS episodes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id     STRING NOT NULL,                -- which agent owns this memory
    session_id   STRING NOT NULL,                -- conversation/session scope
    role         STRING NOT NULL,                -- user | assistant | tool | system
    content      STRING NOT NULL,                -- raw episode text
    content_hash BYTES NOT NULL,                 -- sha256(content) — idempotent writes
    embedding    VECTOR(1024),                   -- Titan v2 embedding
    metadata     JSONB NOT NULL DEFAULT '{}',    -- arbitrary SQL-filterable tags
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE INDEX episodes_dedupe (agent_id, content_hash)
);

-- Distributed vector index — CockroachDB tool #2 (native vector indexing)
CREATE VECTOR INDEX IF NOT EXISTS episodes_embedding_idx
    ON episodes (embedding);

CREATE INDEX IF NOT EXISTS episodes_agent_time_idx
    ON episodes (agent_id, created_at DESC);

CREATE TABLE IF NOT EXISTS semantic_memories (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id     STRING NOT NULL,
    kind         STRING NOT NULL,                -- fact | preference | skill | entity
    statement    STRING NOT NULL,                -- distilled durable memory
    confidence   FLOAT NOT NULL DEFAULT 0.5,     -- consolidation confidence 0..1
    embedding    VECTOR(1024),
    source_episode_ids UUID[] NOT NULL DEFAULT '{}',  -- provenance
    supersedes   UUID,                           -- prior memory this one replaces
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE VECTOR INDEX IF NOT EXISTS semantic_embedding_idx
    ON semantic_memories (embedding);

CREATE INDEX IF NOT EXISTS semantic_agent_kind_idx
    ON semantic_memories (agent_id, kind);

-- Consolidation bookkeeping: which episodes each run processed
CREATE TABLE IF NOT EXISTS consolidation_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id      STRING NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    episodes_seen INT NOT NULL DEFAULT 0,
    memories_written INT NOT NULL DEFAULT 0,
    status        STRING NOT NULL DEFAULT 'running'  -- running | ok | error
);
