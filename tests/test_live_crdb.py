"""Live integration test against the real CockroachDB cluster.

Gated behind RUN_LIVE_CRDB=1 so normal CI (no cluster access) skips it.
Run locally after provisioning:

    RUN_LIVE_CRDB=1 CRDB_DSN_FILE=~/.recall-crdb-dsn .venv/bin/python -m pytest tests/test_live_crdb.py -q

Exercises the exact db.py code paths the Lambdas use — proving the VECTOR
binding, hybrid recall ordering, and consolidation bookkeeping work against a
real cluster (unit tests mock the DB, so only this catches wire-format bugs).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

if os.environ.get("RUN_LIVE_CRDB") != "1":
    pytest.skip("live CRDB test — set RUN_LIVE_CRDB=1", allow_module_level=True)

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

_spec = importlib.util.spec_from_file_location("recall_db", SRC / "common" / "db.py")
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)

# Point db._dsn at the locally-staged DSN file instead of AWS Secrets Manager.
# macOS's bundled OpenSSL has no "system" CA store, so locally we swap
# sslrootcert=system for the explicit CockroachDB CA the console hands out
# (~/.postgresql/root.crt). The DSN kept in Secret Manager stays `system` —
# correct for the Amazon Linux Lambda runtime.
_DSN = Path(os.path.expanduser(os.environ.get("CRDB_DSN_FILE", "~/.recall-crdb-dsn"))).read_text().strip()
_ROOT_CRT = Path(os.path.expanduser("~/.postgresql/root.crt"))
if "sslrootcert=system" in _DSN and _ROOT_CRT.exists():
    _DSN = _DSN.replace("sslrootcert=system", f"sslrootcert={_ROOT_CRT}")
db._dsn = lambda: _DSN  # type: ignore[assignment]

AGENT = "pytest-live"


def _emb(seed: float) -> list[float]:
    return [seed] * 1024


def _axis(i: int, *, tilt: int | None = None) -> list[float]:
    """Unit-ish vector pointing along dimension `i` (optionally tilted toward
    `tilt`). CRDB `<=>` is COSINE distance, so nearest-neighbour tests need
    vectors that differ in DIRECTION — constant vectors are all collinear."""
    v = [0.0] * 1024
    v[i] = 1.0
    if tilt is not None:
        v[tilt] = 0.1
    return v


@pytest.fixture(autouse=True)
def _cleanup():
    with db._conn() as c:
        c.execute("DELETE FROM episodes WHERE agent_id = %s", (AGENT,))
        c.execute("DELETE FROM semantic_memories WHERE agent_id = %s", (AGENT,))
        c.execute("DELETE FROM consolidation_runs WHERE agent_id = %s", (AGENT,))
    yield
    with db._conn() as c:
        c.execute("DELETE FROM episodes WHERE agent_id = %s", (AGENT,))
        c.execute("DELETE FROM semantic_memories WHERE agent_id = %s", (AGENT,))
        c.execute("DELETE FROM consolidation_runs WHERE agent_id = %s", (AGENT,))


def test_insert_episode_and_vector_recall():
    import hashlib

    near = "we deploy Recall to us-east-1"
    far = "the cafeteria serves lunch at noon"
    for content, vec in ((near, _axis(0)), (far, _axis(5))):
        db.insert_episode(
            agent_id=AGENT, session_id="s1", role="user", content=content,
            content_hash=hashlib.sha256(content.encode()).digest(),
            embedding=vec, metadata={"topic": "ops"},
        )

    # Query points mostly along axis 0 → `near` must rank first by cosine distance.
    out = db.hybrid_recall(AGENT, _axis(0, tilt=5), k=2, tier="episodes")
    assert out, "no memories recalled"
    assert out[0]["text"] == near
    assert out[0]["distance"] <= out[-1]["distance"]


def test_metadata_filter_scopes_recall():
    import hashlib

    for content, meta in (("ops note", {"topic": "ops"}), ("hr note", {"topic": "hr"})):
        db.insert_episode(
            agent_id=AGENT, session_id="s1", role="user", content=content,
            content_hash=hashlib.sha256(content.encode()).digest(),
            embedding=_emb(0.2), metadata=meta,
        )
    out = db.hybrid_recall(AGENT, _emb(0.2), k=5, tier="episodes", filters={"topic": "hr"})
    assert [m["text"] for m in out] == ["hr note"]


def test_semantic_insert_and_consolidation_bookkeeping():
    run_id = db.start_consolidation_run(AGENT)
    sm_id = db.insert_semantic_memory(
        agent_id=AGENT, kind="fact", statement="Recall deploys to us-east-1.",
        confidence=0.95, embedding=_emb(0.3), source_episode_ids=[],
    )
    db.finish_consolidation_run(run_id, episodes_seen=2, memories_written=1)

    out = db.hybrid_recall(AGENT, _emb(0.3), k=1, tier="semantic")
    assert out and out[0]["tier"] == "semantic"
    assert db.delete_memory(AGENT, sm_id) is True


def test_dedupe_on_content_hash():
    import hashlib

    c = "duplicate content"
    h = hashlib.sha256(c.encode()).digest()
    for _ in range(2):
        db.insert_episode(agent_id=AGENT, session_id="s1", role="user", content=c,
                          content_hash=h, embedding=_emb(0.4), metadata={})
    with db._conn() as conn:
        n = conn.execute(
            "SELECT count(*) FROM episodes WHERE agent_id = %s", (AGENT,)
        ).fetchone()[0]
    assert n == 1, f"expected dedupe to 1 row, got {n}"
