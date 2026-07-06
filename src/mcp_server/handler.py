"""Recall MCP server — Lambda handler.

Exposes agentic-memory tools over MCP (streamable HTTP via API Gateway):

  store_memory(agent_id, session_id, role, content, metadata) -> episode_id
  recall(agent_id, query, k=5, tier="both", filters={}) -> [memories]
  forget(agent_id, memory_id, reason) -> bool           (Cedar-policied at Gateway)
  consolidate(agent_id) -> run_id                       (manual trigger; normally EventBridge)

P1 scope: tool routing + store/recall against CockroachDB with Titan v2 embeddings.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from common import bedrock, db  # src/common — shared clients

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TOOLS: dict[str, dict[str, Any]] = {
    "store_memory": {
        "description": "Persist an episodic memory for an agent.",
        "required": ["agent_id", "session_id", "role", "content"],
    },
    "recall": {
        "description": "Hybrid recall: vector similarity + SQL metadata filters.",
        "required": ["agent_id", "query"],
    },
    "forget": {
        "description": "Delete a memory by id (subject to Gateway Cedar policy).",
        "required": ["agent_id", "memory_id"],
    },
    "consolidate": {
        "description": "Trigger an episodic->semantic consolidation run.",
        "required": ["agent_id"],
    },
}


def store_memory(args: dict[str, Any]) -> dict[str, Any]:
    content = args["content"]
    content_hash = hashlib.sha256(content.encode()).digest()
    embedding = bedrock.embed(content)  # Titan v2, 1024 dims
    episode_id = db.insert_episode(
        agent_id=args["agent_id"],
        session_id=args["session_id"],
        role=args["role"],
        content=content,
        content_hash=content_hash,
        embedding=embedding,
        metadata=args.get("metadata", {}),
    )
    return {"episode_id": episode_id}


def recall(args: dict[str, Any]) -> dict[str, Any]:
    embedding = bedrock.embed(args["query"])
    rows = db.hybrid_recall(
        agent_id=args["agent_id"],
        embedding=embedding,
        k=int(args.get("k", 5)),
        tier=args.get("tier", "both"),  # episodes | semantic | both
        filters=args.get("filters", {}),
    )
    return {"memories": rows}


def forget(args: dict[str, Any]) -> dict[str, Any]:
    deleted = db.delete_memory(args["agent_id"], args["memory_id"])
    return {"deleted": deleted, "reason": args.get("reason")}


def consolidate(args: dict[str, Any]) -> dict[str, Any]:
    # P2: enqueue/trigger the consolidation Lambda for this agent.
    raise NotImplementedError("P2 — consolidation trigger")


DISPATCH = {
    "store_memory": store_memory,
    "recall": recall,
    "forget": forget,
    "consolidate": consolidate,
}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Minimal MCP-over-HTTP dispatch. P1: harden into full MCP lifecycle
    (initialize / tools-list / tools-call) using the reference MCP Lambda adapter."""
    body = json.loads(event.get("body") or "{}")
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool not in DISPATCH:
        return _resp(400, {"error": f"unknown tool: {tool}", "tools": list(TOOLS)})

    missing = [p for p in TOOLS[tool]["required"] if p not in args]
    if missing:
        return _resp(400, {"error": f"missing arguments: {missing}"})

    try:
        return _resp(200, DISPATCH[tool](args))
    except NotImplementedError as exc:
        return _resp(501, {"error": str(exc)})
    except Exception:
        logger.exception("tool %s failed", tool)
        return _resp(500, {"error": "internal error"})


def _resp(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "body": json.dumps(payload, default=str)}
