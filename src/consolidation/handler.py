"""Recall consolidation worker — the "dream" job (P2).

EventBridge-scheduled. For each active agent:
  1. SELECT unconsolidated episodes since the last consolidation_runs row
  2. Bedrock Claude distills them into durable semantic memories
     (facts / preferences / skills / entities, with confidence + provenance)
  3. Embed each statement (Titan v2) and UPSERT into semantic_memories,
     linking source_episode_ids and superseding stale memories
  4. Record the consolidation_runs row (episodes_seen, memories_written)

Failure path: Lambda retries → SQS DLQ (see infra/template.yaml).
"""

from __future__ import annotations

from typing import Any


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    raise NotImplementedError("P2 — consolidation loop")
