# Recall — Portable, SQL-Native Long-Term Memory for AI Agents

**CockroachDB × AWS "Build with Agentic Memory" hackathon entry** ([rules](https://cockroachdb-ai.devpost.com/))

Recall gives any AI agent durable, own-your-data memory:

- **CockroachDB Serverless** is the memory substrate — episodic rows plus a native
  **distributed vector index** for semantic recall. Your agent's memory is plain SQL:
  queryable, auditable, exportable, portable.
- **AWS Bedrock** is the cognition layer — Titan Embeddings v2 for vectors, Claude for
  the *consolidation* loop that distills raw episodes into durable semantic memories.
- An **MCP server** exposes the whole thing (`store_memory` / `recall` / `consolidate` /
  `forget`) so any framework — Strands, LangGraph, Claude Code, custom — can use it.

```
USER → API Gateway → AgentCore Runtime (demo agent)
                          |  \reason → Bedrock Claude
                      MCP |
                          v
          AgentCore Gateway → CockroachDB MCP Server (Lambda)
                          | embed → Bedrock Titan v2
                          v
          CockroachDB Serverless [(episodes + VECTOR index)]
                          ^
 EventBridge → Consolidation Lambda → Bedrock Claude (extract)
 (all hops traced: AgentCore Observability → CloudWatch/X-Ray)
```

## Why this design

Most agent memory today is a vendor-locked vector dump. Recall models memory the way
cognitive systems do:

1. **Episodic tier** — every interaction lands as a row (`episodes`), embedded with
   Titan v2 and indexed by CockroachDB's distributed vector index.
2. **Semantic tier** — a scheduled **consolidation** job ("dreaming") has Bedrock Claude
   read recent episodes and distill durable facts, preferences, and skills into
   `semantic_memories`, with provenance links back to source episodes.
3. **Hybrid recall** — recall = vector similarity **AND** SQL metadata filters
   (agent, subject, time range, memory tier) in one query. Because it's just SQL.

## Hackathon requirements coverage

| Requirement | How |
|---|---|
| ≥2 CockroachDB tools | **MCP Server** + **distributed vector indexing** + **ccloud CLI** (3) |
| ≥1 AWS service | Bedrock, Lambda, AgentCore (Runtime/Gateway/Observability), EventBridge, S3, API Gateway (6+) |
| Public open-source repo | this repo (MIT) |
| Functional demo URL | API Gateway endpoint — see `docs/demo.md` (P4) |
| Demo video <3 min | linked from Devpost submission (P5) |

## Repository layout

```
src/mcp_server/      Lambda: MCP tools (store_memory / recall / forget / consolidate)
src/consolidation/   Lambda: EventBridge-scheduled episodic→semantic consolidation
src/common/          shared: db pool, bedrock clients, config
schema/              CockroachDB DDL (episodes, semantic_memories, vector indexes)
infra/               AWS SAM template (all resources as IaC)
scripts/             ccloud provisioning + smoke tests
tests/               unit tests (moto/pytest)
docs/                architecture, demo walkthrough, Well-Architected notes
```

## Quickstart (once deployed)

```bash
# provision the CockroachDB Serverless cluster + schema
./scripts/provision-ccloud.sh

# deploy the AWS stack
sam build && sam deploy --guided

# smoke: store a memory, then recall it
./scripts/smoke.sh
```

## IP boundary

This repository is a **standalone, generalized pattern** built for this hackathon:
architecture, schema, Lambda handlers, IaC, and evidence. It does **not** contain —
and will never contain — OpsAgents product source code, the SOSA agent skill library,
agent prompts/playbooks, credentials, or client data. Production OpsAgents codebases
are private; this artifact demonstrates the *pattern* end-to-end on its own.

## License

MIT — see [LICENSE](LICENSE).
