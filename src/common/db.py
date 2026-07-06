"""CockroachDB access layer — connection via Secrets Manager, psycopg pool.

CockroachDB is Postgres-wire-compatible; vector search uses the native VECTOR
type + distributed vector index (see schema/001_init.sql).
"""

from __future__ import annotations

import functools
import json
import os
from typing import Any

import boto3
import psycopg


@functools.cache
def _dsn() -> str:
    secret_arn = os.environ["CRDB_SECRET_ARN"]
    sm = boto3.client("secretsmanager")
    return sm.get_secret_value(SecretId=secret_arn)["SecretString"]


def _conn() -> psycopg.Connection:
    return psycopg.connect(_dsn(), autocommit=True)


def insert_episode(**f: Any) -> str:
    sql = """
        INSERT INTO episodes (agent_id, session_id, role, content, content_hash,
                              embedding, metadata)
        VALUES (%(agent_id)s, %(session_id)s, %(role)s, %(content)s, %(content_hash)s,
                %(embedding)s, %(metadata)s)
        ON CONFLICT (agent_id, content_hash) DO UPDATE SET metadata = excluded.metadata
        RETURNING id
    """
    f["metadata"] = json.dumps(f.get("metadata") or {})
    with _conn() as conn:
        row = conn.execute(sql, f).fetchone()
    return str(row[0])


def hybrid_recall(
    agent_id: str,
    embedding: list[float],
    k: int = 5,
    tier: str = "both",
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Vector similarity + SQL metadata filter, in one query per tier.

    P1 note: filters are matched against the JSONB metadata column with @>;
    time-range and kind filters are added in P2.
    """
    results: list[dict[str, Any]] = []
    meta = json.dumps(filters or {})

    if tier in ("episodes", "both"):
        sql = """
            SELECT id, 'episode' AS tier, content AS text, metadata, created_at,
                   embedding <=> %(emb)s AS distance
            FROM episodes
            WHERE agent_id = %(agent_id)s AND metadata @> %(meta)s
            ORDER BY embedding <=> %(emb)s
            LIMIT %(k)s
        """
        with _conn() as conn:
            for r in conn.execute(
                sql, {"agent_id": agent_id, "emb": embedding, "meta": meta, "k": k}
            ):
                results.append(_row(r))

    if tier in ("semantic", "both"):
        sql = """
            SELECT id, 'semantic' AS tier, statement AS text, metadata, created_at,
                   embedding <=> %(emb)s AS distance
            FROM semantic_memories
            WHERE agent_id = %(agent_id)s AND metadata @> %(meta)s
            ORDER BY embedding <=> %(emb)s
            LIMIT %(k)s
        """
        with _conn() as conn:
            for r in conn.execute(
                sql, {"agent_id": agent_id, "emb": embedding, "meta": meta, "k": k}
            ):
                results.append(_row(r))

    results.sort(key=lambda m: m["distance"])
    return results[:k]


def delete_memory(agent_id: str, memory_id: str) -> bool:
    with _conn() as conn:
        n = conn.execute(
            "DELETE FROM episodes WHERE agent_id = %s AND id = %s", (agent_id, memory_id)
        ).rowcount
        n += conn.execute(
            "DELETE FROM semantic_memories WHERE agent_id = %s AND id = %s",
            (agent_id, memory_id),
        ).rowcount
    return n > 0


def _row(r: tuple) -> dict[str, Any]:
    return {
        "id": str(r[0]),
        "tier": r[1],
        "text": r[2],
        "metadata": r[3],
        "created_at": r[4],
        "distance": float(r[5]),
    }
