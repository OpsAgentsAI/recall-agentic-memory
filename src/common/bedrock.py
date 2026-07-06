"""Bedrock clients — Titan v2 embeddings + Claude (inference profile) generation."""

from __future__ import annotations

import functools
import json
import os
from typing import Any

import boto3


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


def extract_semantic_memories(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """P2 — consolidation prompt: distill episodes into durable semantic memories.

    Returns [{kind, statement, confidence, source_episode_ids}].
    """
    raise NotImplementedError("P2 — consolidation extraction")
