# Recall — CockroachDB × AWS Hackathon

Portable, SQL-native long-term memory for AI agents. CockroachDB Serverless = memory
substrate (episodic rows + native distributed vector index). AWS Bedrock = cognition
(Titan v2 embeddings + Claude consolidation "dreaming" loop). An MCP server exposes
`store_memory` / `recall` / `consolidate` / `forget` so any framework can plug in.

- **Hackathon:** CockroachDB × AWS "Build with Agentic Memory" — https://cockroachdb-ai.devpost.com/
- **Deadline:** 2026-08-18, 5pm EDT
- **License:** MIT (public OSS repo is a hackathon requirement)

## IP boundary (load-bearing)

This repo is a **standalone, generalized pattern** built for this hackathon only:
architecture, schema, Lambda handlers, IaC, and evidence. It does **not** — and will never
— contain OpsAgents product source, the SOSA agent-skill library, agent prompts/playbooks,
credentials, or client data. Production OpsAgents codebases stay private.

## Trello build board

Work is tracked on **🗄️ Recall — CockroachDB × AWS Hackathon** —
https://trello.com/b/DLl9OC0T (board id `6a50e3c3a9d813cf0d41c0fa`, shortLink `DLl9OC0T`).
Cross-linked from the Hackathons tracker card https://trello.com/c/QeBN9XY9.

Cloned from the canonical OpsAgents 7-stage template, so `/board-pipeline`,
`/backend-pipeline`, and `/board-refinement` run against it unmodified. Pipelines key on
**listId**, never list name.

### List IDs

| List | ID |
|---|---|
| ℹ️ Info | `6a50e3cd46f1c1afe6d31393` |
| To Do | `6a50e3c3a9d813cf0d41c0f3` |
| Doing | `6a50e3c3a9d813cf0d41c0f4` |
| Code Review (Pass if not Technical) | `6a50e3c3a9d813cf0d41c0f5` |
| Deploy Staging (Pass if nothing to deploy) | `6a50e3c3a9d813cf0d41c0f6` |
| QA (or verify done) | `6a50e3c3a9d813cf0d41c0f7` |
| Deploy Prod (pass if nothing to deploy) | `6a50e3c3a9d813cf0d41c0f8` |
| Done | `6a50e3c3a9d813cf0d41c0f9` |

**Repo (Info column):** https://github.com/OpsAgentsAI/recall-agentic-memory

## Path to submission (dependency order)

GO/NO-GO (vs XPRIZE crunch — PM/Michal decision, gates the rest) → provision CockroachDB
Serverless + schema (ccloud login) → deploy AWS SAM stack → smoke test (store→recall +
consolidation) → functional demo URL + `docs/demo.md` → demo video <3 min → Devpost submit.

## Requirements coverage

- **≥2 CockroachDB tools:** MCP Server + distributed vector indexing + ccloud CLI (3)
- **≥1 AWS service:** Bedrock, Lambda, AgentCore, EventBridge, S3, API Gateway (6+)
- **Public OSS repo:** this repo (MIT)
- **Functional demo URL:** API Gateway endpoint — see `docs/demo.md`
- **Demo video <3 min:** linked from the Devpost submission

## Repository layout

```
src/mcp_server/     Lambda: MCP tools (store_memory / recall / forget / consolidate)
src/consolidation/  Lambda: EventBridge-scheduled episodic→semantic consolidation
src/common/         shared: db pool, bedrock clients, config
schema/             CockroachDB DDL (episodes, semantic_memories, vector indexes)
infra/              AWS SAM template (all resources as IaC)
scripts/            ccloud provisioning + smoke tests
tests/              unit tests (moto/pytest)
docs/               architecture, demo walkthrough, Well-Architected notes
```
