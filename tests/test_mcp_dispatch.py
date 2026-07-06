"""Unit tests — MCP lifecycle + plain dispatch surface (no live DB/Bedrock)."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

_spec = importlib.util.spec_from_file_location(
    "mcp_server_handler", SRC / "mcp_server" / "handler.py"
)
handler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(handler)


def _http(body) -> tuple[int, dict | list]:
    resp = handler.lambda_handler({"body": json.dumps(body)}, None)
    return resp["statusCode"], json.loads(resp["body"])


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


# ---- plain (P0) shape -----------------------------------------------------------

def test_plain_unknown_tool_rejected():
    status, body = _http({"tool": "nope"})
    assert status == 400
    assert "store_memory" in body["tools"]


def test_plain_missing_arguments_rejected():
    status, body = _http({"tool": "recall", "arguments": {"agent_id": "a1"}})
    assert status == 400
    assert "query" in body["error"]


def test_plain_store_memory_routes_to_db_and_embedding():
    with mock.patch.object(handler.bedrock, "embed", return_value=[0.0] * 1024), \
         mock.patch.object(handler.db, "insert_episode", return_value="ep-1"):
        status, body = _http({
            "tool": "store_memory",
            "arguments": {
                "agent_id": "a1", "session_id": "s1",
                "role": "user", "content": "remember the deploy region is us-east-1",
            },
        })
    assert status == 200
    assert body["episode_id"] == "ep-1"


# ---- MCP JSON-RPC lifecycle -----------------------------------------------------

def test_mcp_initialize_handshake():
    status, body = _http(_rpc("initialize", {"protocolVersion": "2025-06-18"}))
    assert status == 200
    assert body["result"]["serverInfo"]["name"] == "recall-memory"
    assert body["result"]["capabilities"] == {"tools": {}}


def test_mcp_notification_gets_202_no_body():
    resp = handler.lambda_handler(
        {"body": json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})},
        None,
    )
    assert resp["statusCode"] == 202


def test_mcp_tools_list_exposes_all_four_tools():
    status, body = _http(_rpc("tools/list"))
    assert status == 200
    names = {t["name"] for t in body["result"]["tools"]}
    assert names == {"store_memory", "recall", "forget", "consolidate"}
    for t in body["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_mcp_tools_call_recall_happy_path():
    memories = [{"id": "m1", "tier": "semantic", "text": "region is us-east-1",
                 "metadata": {}, "created_at": "2026-07-07", "distance": 0.1}]
    with mock.patch.object(handler.bedrock, "embed", return_value=[0.0] * 1024), \
         mock.patch.object(handler.db, "hybrid_recall", return_value=memories):
        status, body = _http(_rpc("tools/call", {
            "name": "recall",
            "arguments": {"agent_id": "a1", "query": "what region do we deploy to?"},
        }))
    assert status == 200
    assert body["result"]["isError"] is False
    payload = json.loads(body["result"]["content"][0]["text"])
    assert payload["memories"][0]["id"] == "m1"


def test_mcp_tools_call_missing_args_is_tool_error_not_rpc_error():
    status, body = _http(_rpc("tools/call", {"name": "recall", "arguments": {}}))
    assert status == 200
    assert body["result"]["isError"] is True


def test_mcp_unknown_method_is_rpc_error():
    status, body = _http(_rpc("prompts/list"))
    assert status == 200
    assert body["error"]["code"] == -32601


def test_mcp_batch_messages():
    status, body = _http([_rpc("tools/list", req_id=1), _rpc("initialize", {}, req_id=2)])
    assert status == 200
    assert {m["id"] for m in body} == {1, 2}
