"""Unit tests — consolidation extraction parsing + worker loop (mocked Bedrock/DB)."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

from common import bedrock  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "consolidation_handler", SRC / "consolidation" / "handler.py"
)
consolidation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(consolidation)

EPISODES = [
    {"id": "e0", "role": "user", "content": "We deploy Recall to us-east-1.",
     "created_at": "2026-07-07T10:00:00Z"},
    {"id": "e1", "role": "user", "content": "Please always answer me in Hebrew.",
     "created_at": "2026-07-07T10:01:00Z"},
    {"id": "e2", "role": "assistant", "content": "בסדר גמור!",
     "created_at": "2026-07-07T10:01:30Z"},
]

MODEL_JSON = """```json
{"memories": [
  {"kind": "fact", "statement": "Recall deploys to us-east-1.",
   "confidence": 0.95, "source_indices": [0]},
  {"kind": "preference", "statement": "The user prefers responses in Hebrew.",
   "confidence": 0.9, "source_indices": [1, 2], "supersedes_existing": 0},
  {"kind": "gibberish", "statement": "dropped — bad kind", "confidence": 1.0,
   "source_indices": [0]},
  {"kind": "fact", "statement": "", "confidence": 1.0, "source_indices": [99]}
]}
```"""

EXISTING = [{"id": "sm-old", "kind": "preference",
             "statement": "The user prefers responses in English."}]


def test_extract_parses_fenced_json_validates_and_maps_provenance():
    with mock.patch.object(bedrock, "generate", return_value=MODEL_JSON):
        out = bedrock.extract_semantic_memories(EPISODES, EXISTING)

    assert len(out) == 2  # bad kind + empty statement dropped
    fact, pref = out
    assert fact["source_episode_ids"] == ["e0"]
    assert pref["supersedes_id"] == "sm-old"
    assert 0 <= pref["confidence"] <= 1


def test_extract_handles_non_json_output():
    with mock.patch.object(bedrock, "generate", return_value="I have no memories to report."):
        assert bedrock.extract_semantic_memories(EPISODES) == []


def test_worker_skips_below_min_episodes():
    with mock.patch.object(consolidation.db, "episodes_since_last_run", return_value=EPISODES[:1]):
        out = consolidation.consolidate_agent("a1")
    assert out["skipped"] is True


def test_worker_full_run_writes_memories_and_run_row():
    mem = {"kind": "fact", "statement": "Recall deploys to us-east-1.",
           "confidence": 0.95, "source_episode_ids": ["e0"]}
    with mock.patch.object(consolidation.db, "episodes_since_last_run", return_value=EPISODES), \
         mock.patch.object(consolidation.db, "list_semantic_memories", return_value=[]), \
         mock.patch.object(consolidation.db, "start_consolidation_run", return_value="run-1"), \
         mock.patch.object(consolidation.db, "insert_semantic_memory", return_value="sm-1") as ins, \
         mock.patch.object(consolidation.db, "finish_consolidation_run") as fin, \
         mock.patch.object(consolidation.bedrock, "extract_semantic_memories", return_value=[mem]), \
         mock.patch.object(consolidation.bedrock, "embed", return_value=[0.0] * 1024):
        out = consolidation.consolidate_agent("a1")

    assert out == {"agent_id": "a1", "run_id": "run-1",
                   "episodes_seen": 3, "memories_written": 1}
    ins.assert_called_once()
    fin.assert_called_once_with("run-1", 3, 1, "ok")


def test_worker_marks_run_error_and_reraises():
    with mock.patch.object(consolidation.db, "episodes_since_last_run", return_value=EPISODES), \
         mock.patch.object(consolidation.db, "list_semantic_memories", return_value=[]), \
         mock.patch.object(consolidation.db, "start_consolidation_run", return_value="run-1"), \
         mock.patch.object(consolidation.db, "finish_consolidation_run") as fin, \
         mock.patch.object(consolidation.bedrock, "extract_semantic_memories",
                           side_effect=RuntimeError("bedrock down")):
        try:
            consolidation.consolidate_agent("a1")
            raised = False
        except RuntimeError:
            raised = True

    assert raised
    fin.assert_called_once_with("run-1", 3, 0, "error")
