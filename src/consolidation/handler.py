"""Recall consolidation worker — the "dream" job.

EventBridge-scheduled (or async-invoked via the MCP `consolidate` tool). For the
target agent(s):

  1. SELECT episodes newer than the last successful consolidation_runs row
  2. Bedrock Claude distills them into durable semantic memories
     (facts / preferences / skills / entities, with confidence + provenance)
  3. Embed each statement (Titan v2) and INSERT into semantic_memories,
     retiring any superseded memory
  4. Record the consolidation_runs row (episodes_seen, memories_written)

Failure path: Lambda retries -> SQS DLQ (see infra/template.yaml).
"""

from __future__ import annotations

import logging
from typing import Any

from common import bedrock, db

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MIN_EPISODES = 3  # don't wake Claude for less


def consolidate_agent(agent_id: str) -> dict[str, Any]:
    episodes = db.episodes_since_last_run(agent_id)
    if len(episodes) < MIN_EPISODES:
        logger.info("agent %s: only %d new episodes — skipping", agent_id, len(episodes))
        return {"agent_id": agent_id, "skipped": True, "episodes_seen": len(episodes)}

    run_id = db.start_consolidation_run(agent_id)
    written = 0
    try:
        existing = db.list_semantic_memories(agent_id)
        for mem in bedrock.extract_semantic_memories(episodes, existing):
            db.insert_semantic_memory(
                agent_id=agent_id,
                kind=mem["kind"],
                statement=mem["statement"],
                confidence=mem["confidence"],
                embedding=bedrock.embed(mem["statement"]),
                source_episode_ids=mem["source_episode_ids"],
                supersedes_id=mem.get("supersedes_id"),
            )
            written += 1
        db.finish_consolidation_run(run_id, len(episodes), written, "ok")
    except Exception:
        db.finish_consolidation_run(run_id, len(episodes), written, "error")
        raise

    logger.info("agent %s: %d episodes -> %d semantic memories",
                agent_id, len(episodes), written)
    return {"agent_id": agent_id, "run_id": run_id,
            "episodes_seen": len(episodes), "memories_written": written}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    agent_id = (event or {}).get("agent_id")
    if agent_id:
        return consolidate_agent(agent_id)

    # Scheduled run: consolidate every agent with recent episodes.
    results = [consolidate_agent(a) for a in _active_agents()]
    return {"runs": results}


def _active_agents() -> list[str]:
    from common.db import _conn  # noqa: PLC0415

    with _conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT agent_id FROM episodes
               WHERE created_at > now() - INTERVAL '24 hours'"""
        ).fetchall()
    return [r[0] for r in rows]
