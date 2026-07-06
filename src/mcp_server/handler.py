"""Recall MCP server — Lambda handler.

Implements the MCP lifecycle over streamable HTTP (JSON-RPC 2.0 via API Gateway):

  initialize            -> protocol/capability handshake
  notifications/*       -> accepted (202-style no-op)
  tools/list            -> the four memory tools with JSON Schemas
  tools/call            -> dispatch to store_memory / recall / forget / consolidate

Also accepts the P0 plain shape {"tool": ..., "arguments": ...} so early smoke
clients and the provisioning scripts keep working.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from common import bedrock, db  # src/common — shared clients

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "recall-memory", "version": "0.2.0"}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "store_memory",
        "description": "Persist an episodic memory for an agent. Embeds the content "
        "(Titan v2) and inserts a row into CockroachDB; idempotent on content hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "session_id": {"type": "string"},
                "role": {"type": "string", "enum": ["user", "assistant", "tool", "system"]},
                "content": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["agent_id", "session_id", "role", "content"],
        },
    },
    {
        "name": "recall",
        "description": "Hybrid recall: CockroachDB vector similarity + SQL metadata "
        "filters over both memory tiers (episodes and consolidated semantic memories).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
                "tier": {"type": "string", "enum": ["episodes", "semantic", "both"], "default": "both"},
                "filters": {"type": "object"},
            },
            "required": ["agent_id", "query"],
        },
    },
    {
        "name": "forget",
        "description": "Delete a memory by id. Subject to AgentCore Gateway Cedar "
        "policy (e.g. old memories require confirmation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "memory_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["agent_id", "memory_id"],
        },
    },
    {
        "name": "consolidate",
        "description": "Trigger an episodic->semantic consolidation run for an agent "
        "(normally fired on schedule by EventBridge).",
        "inputSchema": {
            "type": "object",
            "properties": {"agent_id": {"type": "string"}},
            "required": ["agent_id"],
        },
    },
]

TOOLS: dict[str, dict[str, Any]] = {
    t["name"]: {"required": t["inputSchema"]["required"]} for t in TOOL_SCHEMAS
}


# ---- tool implementations ----------------------------------------------------

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
        tier=args.get("tier", "both"),
        filters=args.get("filters", {}),
    )
    return {"memories": rows}


def forget(args: dict[str, Any]) -> dict[str, Any]:
    deleted = db.delete_memory(args["agent_id"], args["memory_id"])
    return {"deleted": deleted, "reason": args.get("reason")}


def consolidate(args: dict[str, Any]) -> dict[str, Any]:
    """Fire-and-forget async invoke of the consolidation worker."""
    import boto3

    fn = os.environ.get("CONSOLIDATION_FUNCTION_NAME", "recall-consolidation")
    boto3.client("lambda").invoke(
        FunctionName=fn,
        InvocationType="Event",
        Payload=json.dumps({"agent_id": args["agent_id"]}).encode(),
    )
    return {"triggered": True, "agent_id": args["agent_id"]}


DISPATCH = {
    "store_memory": store_memory,
    "recall": recall,
    "forget": forget,
    "consolidate": consolidate,
}


# ---- MCP JSON-RPC layer --------------------------------------------------------

def _rpc_result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _call_tool(name: str, args: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Returns (is_error, payload). Shared by MCP and plain dispatch."""
    if name not in DISPATCH:
        return True, {"error": f"unknown tool: {name}", "tools": list(TOOLS)}
    missing = [p for p in TOOLS[name]["required"] if p not in args]
    if missing:
        return True, {"error": f"missing arguments: {missing}"}
    return False, DISPATCH[name](args)


def handle_mcp(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; None for notifications (no response body)."""
    method = msg.get("method", "")
    req_id = msg.get("id")

    if method.startswith("notifications/"):
        return None

    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method == "tools/list":
        return _rpc_result(req_id, {"tools": TOOL_SCHEMAS})

    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            is_error, payload = _call_tool(name, args)
        except Exception:
            logger.exception("tool %s failed", name)
            is_error, payload = True, {"error": "internal error"}
        return _rpc_result(req_id, {
            "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
            "isError": is_error,
        })

    return _rpc_error(req_id, -32601, f"method not found: {method}")


# ---- Lambda entrypoint -----------------------------------------------------------

def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON body"})

    # MCP JSON-RPC (single message or batch)
    if isinstance(body, dict) and body.get("jsonrpc") == "2.0":
        out = handle_mcp(body)
        return _resp(202, {}) if out is None else _resp(200, out)
    if isinstance(body, list) and body and all(
        isinstance(m, dict) and m.get("jsonrpc") == "2.0" for m in body
    ):
        outs = [r for r in (handle_mcp(m) for m in body) if r is not None]
        return _resp(202, {}) if not outs else _resp(200, outs)

    # P0 plain shape (smoke clients, provisioning scripts)
    tool = body.get("tool") if isinstance(body, dict) else None
    args = body.get("arguments", {}) if isinstance(body, dict) else {}
    if tool is None:
        return _resp(400, {"error": "expected MCP JSON-RPC or {tool, arguments}"})
    try:
        is_error, payload = _call_tool(tool, args)
    except NotImplementedError as exc:
        return _resp(501, {"error": str(exc)})
    except Exception:
        logger.exception("tool %s failed", tool)
        return _resp(500, {"error": "internal error"})
    return _resp(400 if is_error else 200, payload)


def _resp(status: int, payload: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload, default=str),
    }
