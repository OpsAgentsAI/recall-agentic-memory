"""P0 smoke tests — MCP dispatch surface (no DB/Bedrock needed)."""

import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "mcp_server"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import handler  # noqa: E402


def _call(body: dict) -> tuple[int, dict]:
    resp = handler.lambda_handler({"body": json.dumps(body)}, None)
    return resp["statusCode"], json.loads(resp["body"])


def test_unknown_tool_rejected():
    status, body = _call({"tool": "nope"})
    assert status == 400
    assert "store_memory" in body["tools"]


def test_missing_arguments_rejected():
    status, body = _call({"tool": "recall", "arguments": {"agent_id": "a1"}})
    assert status == 400
    assert "query" in body["error"]


def test_consolidate_not_implemented_yet():
    status, _ = _call({"tool": "consolidate", "arguments": {"agent_id": "a1"}})
    assert status == 501


def test_store_memory_routes_to_db_and_embedding():
    with mock.patch.object(handler.bedrock, "embed", return_value=[0.0] * 1024), \
         mock.patch.object(handler.db, "insert_episode", return_value="ep-1"):
        status, body = _call({
            "tool": "store_memory",
            "arguments": {
                "agent_id": "a1", "session_id": "s1",
                "role": "user", "content": "remember the deploy region is us-east-1",
            },
        })
    assert status == 200
    assert body["episode_id"] == "ep-1"
