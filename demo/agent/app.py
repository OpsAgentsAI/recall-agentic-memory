"""Recall demo agent — an ops assistant that actually remembers you.

Runs on Amazon Bedrock AgentCore Runtime. Every turn:

  1. RECALL  — query Recall (MCP over HTTP) for memories relevant to the message
  2. REASON  — Bedrock Claude answers with those memories in context
  3. REMEMBER — both sides of the exchange are stored as new episodes

Across sessions, the EventBridge-scheduled consolidation job distills those
episodes into durable semantic memories — so the agent doesn't just have
history, it *learns*: preferences, facts, and procedures survive session death.

Deploy (dev):    agentcore init && agentcore deploy   (see demo/README.md)
Invoke payload:  {"prompt": "...", "agent_id": "demo", "session_id": "s-123"}
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

RECALL_URL = os.environ["RECALL_MCP_URL"]          # API GW /mcp endpoint
MODEL_ID = os.environ.get(
    "AGENT_MODEL_ID", "us.anthropic.claude-sonnet-4-6-v1:0"  # inference profile
)

SYSTEM = """\
You are an operations assistant with persistent memory. MEMORIES below were
recalled from your long-term store (CockroachDB) — semantic memories are
consolidated durable knowledge, episodes are raw history. Trust semantic
memories unless the user contradicts them now. Use memories naturally; don't
recite them. If the user states a durable fact or preference, acknowledge it —
it will be remembered.

MEMORIES:
{memories}
"""


def _recall_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a Recall memory tool over MCP JSON-RPC."""
    req = urllib.request.Request(
        RECALL_URL,
        data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        rpc = json.loads(resp.read())
    return json.loads(rpc["result"]["content"][0]["text"])


@app.entrypoint
def invoke(payload: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    prompt = payload["prompt"]
    agent_id = payload.get("agent_id", "demo")
    session_id = payload.get("session_id", "default")

    # 1. RECALL
    memories = _recall_tool(
        "recall", {"agent_id": agent_id, "query": prompt, "k": 8}
    ).get("memories", [])
    memory_lines = "\n".join(
        f"- [{m['tier']}] {m['text']}" for m in memories
    ) or "(none yet — first meeting)"

    # 2. REASON
    answer = boto3.client("bedrock-runtime").converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM.format(memories=memory_lines)}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1024, "temperature": 0.4},
    )["output"]["message"]["content"][0]["text"]

    # 3. REMEMBER (both turns)
    for role, content in (("user", prompt), ("assistant", answer)):
        _recall_tool("store_memory", {
            "agent_id": agent_id, "session_id": session_id,
            "role": role, "content": content,
        })

    return {
        "answer": answer,
        "memories_used": len(memories),
        "memory_preview": memory_lines[:500],
    }


if __name__ == "__main__":
    app.run()
