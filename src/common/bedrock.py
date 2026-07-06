"""Bedrock clients — Titan v2 embeddings + Claude (inference profile) generation."""

from __future__ import annotations

import functools
import json
import os
from typing import Any

import boto3

CONSOLIDATION_SYSTEM = """\
You are the memory-consolidation module of an AI agent — the part that turns raw \
experience into durable knowledge, the way sleep consolidates memory in humans.

You receive a batch of raw episodic memories (conversation turns, tool results, \
observations) belonging to one agent. Distill them into durable SEMANTIC memories \
worth keeping long-term.

Rules:
- Extract only durable knowledge: stable facts, user preferences, learned skills or \
procedures, and important entities. Skip chit-chat, one-off states, and anything \
already implied by an existing memory you are shown.
- Each memory must be a single, self-contained statement understandable without the \
source conversation.
- kind is one of: fact | preference | skill | entity.
- confidence in [0,1]: 0.9+ only for explicitly stated facts; hedge inferred ones.
- source_indices lists the episode numbers (from the input) that support the memory.
- If an extracted memory contradicts one of the EXISTING memories shown, emit it with \
"supersedes_existing": <existing index> so the old one can be retired.
- Return STRICT JSON: {"memories": [{"kind", "statement", "confidence", \
"source_indices", "supersedes_existing"?}]} and nothing else. No memories worth \
keeping -> {"memories": []}.
"""


@functools.cache
def _runtime():
    return boto3.client("bedrock-runtime")


def embed(text: str) -> list[float]:
    """Titan Embeddings v2 — 1024-dim vector (matches schema VECTOR(1024))."""
    resp = _runtime().invoke_model(
        modelId=os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"),
        body=json.dumps({"inputText": text[:8000], "dimensions": 1024}),
    )
    return json.loads(resp["body"].read())["embedding"]


def generate(system: str, user: str, max_tokens: int = 2048) -> str:
    """Claude via Bedrock inference profile (Converse API).

    INFERENCE_PROFILE-only in this account — model id must be the `us.` profile id,
    never the bare foundation-model id.
    """
    resp = _runtime().converse(
        modelId=os.environ["CONSOLIDATE_MODEL_ID"],
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"]


def extract_semantic_memories(
    episodes: list[dict[str, Any]],
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Consolidation: distill raw episodes into durable semantic memories.

    episodes: [{id, role, content, created_at}] — chronological.
    existing: [{id, kind, statement}] — current semantic memories for dedupe/supersede.
    Returns [{kind, statement, confidence, source_episode_ids, supersedes_id?}].
    """
    ep_lines = "\n".join(
        f"[{i}] ({e['role']}, {e.get('created_at', '?')}) {e['content']}"
        for i, e in enumerate(episodes)
    )
    ex_lines = "\n".join(
        f"[{i}] ({m['kind']}) {m['statement']}" for i, m in enumerate(existing or [])
    ) or "(none)"

    raw = generate(
        CONSOLIDATION_SYSTEM,
        f"EXISTING memories:\n{ex_lines}\n\nEPISODES to consolidate:\n{ep_lines}",
        max_tokens=4096,
    )
    parsed = _parse_json_block(raw)

    out: list[dict[str, Any]] = []
    for m in parsed.get("memories", []):
        if m.get("kind") not in ("fact", "preference", "skill", "entity"):
            continue
        statement = (m.get("statement") or "").strip()
        if not statement:
            continue
        src = [
            episodes[i]["id"]
            for i in m.get("source_indices", [])
            if isinstance(i, int) and 0 <= i < len(episodes)
        ]
        mem: dict[str, Any] = {
            "kind": m["kind"],
            "statement": statement,
            "confidence": max(0.0, min(1.0, float(m.get("confidence", 0.5)))),
            "source_episode_ids": src,
        }
        sup = m.get("supersedes_existing")
        if existing and isinstance(sup, int) and 0 <= sup < len(existing):
            mem["supersedes_id"] = existing[sup]["id"]
        out.append(mem)
    return out


def _parse_json_block(raw: str) -> dict[str, Any]:
    """Parse model output that may wrap JSON in a markdown fence."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {"memories": []}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"memories": []}
