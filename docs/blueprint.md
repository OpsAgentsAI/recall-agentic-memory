# Recall — Agentic Memory on CockroachDB + AWS Bedrock

**Hackathon:** CockroachDB × AWS — Build with Agentic Memory (QeBN9XY9) · Deadline Aug 18 2026 5pm EDT · Prize $8,750
**Decision:** GO (opsagent-pm + opsagents-cto, 2026-07-06)
**Repo (to cut, PUBLIC):** `OpsAgentsAI/recall-agentic-memory` — IP-boundary README (pattern only, no product source)
**AWS acct:** 952933884163 (Bedrock Path-2, Activate-credit-covered) · Region: **us-east-1** (AgentCore + Bedrock Claude + Titan v2)

## One-liner
Portable, SQL-native long-term memory for AI agents. CockroachDB is the memory substrate (episodic rows + native distributed vector index); AWS Bedrock is the reasoning/extraction/embedding layer; the whole thing is serverless on AWS and exposed to any agent via an MCP server. The differentiator: **own-your-data, SQL-queryable, portable agentic memory** vs. vendor-locked memory stores.

## CockroachDB tools used (need ≥2 — using 3)
1. **CockroachDB MCP Server** — agent-facing tools: `store_memory`, `recall`, `consolidate`, `forget`. Tool #1.
2. **Distributed vector indexing** — CockroachDB native `VECTOR` type + vector index for semantic recall over Titan embeddings. Tool #2.
3. **ccloud CLI** — provisions the Serverless free-tier cluster + schema in CI. Tool #3.

## AWS services used (need ≥1 — using several)
- **Bedrock** — Claude (inference profile) for memory extraction/consolidation + the demo agent's reasoning; **Titan Embeddings v2** for vectors.
- **Lambda** — MCP server handlers (store/recall/forget) + the consolidation worker.
- **AgentCore Runtime + Gateway + Observability** — hosts the demo agent; Gateway exposes the CockroachDB MCP server as MCP tools; Observability → CloudWatch/X-Ray.
- **EventBridge** — schedules the "consolidation" job (raw episodes → structured semantic memories — the generalized "dream/consolidate" pattern).
- **S3** — raw transcript store + Bedrock batch I/O for bulk consolidation.
- **API Gateway** — the public functional demo URL.
- **Secrets Manager** — CockroachDB connection string; **Bedrock Guardrails** + **AgentCore Policy (Cedar)** on the agent/tool surface.

## Data flow
Agent (AgentCore Runtime) → AgentCore Gateway (MCP) → CockroachDB MCP Server (Lambda) → CockroachDB Serverless (episodes table + vector index). Writes embed via Titan v2 and INSERT an episode row. Recalls vector-search the index + SQL-filter by metadata, return top-k. EventBridge → consolidation Lambda → Bedrock Claude extracts durable semantic memories from recent episodes and writes them back (long-term memory). AgentCore Observability traces every hop.

## Well-Architected (Production Readiness judging axis)
- **Security:** IAM least-priv per Lambda; CockroachDB creds in Secrets Manager (never in code); Bedrock Guardrails on agent I/O; Cedar Policy on Gateway (e.g. forbid `forget` on memories older than N days without confirmation); TLS to CockroachDB.
- **Reliability:** CockroachDB Serverless multi-region survivability; Lambda retries + SQS DLQ on consolidation; idempotent memory writes (content hash dedupe).
- **Cost:** serverless min=0; CockroachDB Serverless free tier (10 GiB); Titan v2 embeddings ~cents; Claude Haiku for consolidation; prompt caching on the agent system prompt. Whole build+demo < $20, Activate-credit-covered.
- **Performance:** native vector index (no external vector DB); prompt caching; hybrid recall (vector + SQL metadata filter).
- **Operational Excellence:** all IaC (SAM/CDK); GH Actions CI/CD (build → deploy → smoke `agentcore invoke`); memory-specific metrics.
- **Sustainability:** scale-to-zero serverless, batch consolidation.

## Judging-criteria map
| Axis | How we win it |
|---|---|
| Agentic Memory Design | Two-tier memory (episodic rows → consolidated semantic memories), vector + SQL hybrid recall, an explicit consolidation loop — a real cognitive-memory model, not just a vector dump. |
| Technical Implementation | 3 CockroachDB tools + 6 AWS services, MCP-native, all IaC, CI/CD, tests. |
| Real-World Impact | "Own-your-data portable agent memory" — any framework, any model, no vendor lock-in; SQL-auditable memory for compliance. |
| Production Readiness | Full Well-Architected pass, Guardrails + Cedar Policy, observability from day one, DLQ, IaC. |
| Creativity | CockroachDB-as-memory-substrate contrasted against vendor memory; the "consolidation/dream" job; SQL-queryable agent memory. |

## Build plan (~5.5 build-days ≤ 1 week; AWS/Bedrock arm = XPRIZE-orthogonal)
- **P0 (0.5d)** — cut PUBLIC repo + IP-boundary README; ccloud Serverless free-tier cluster; schema (episodes + vector index); Secrets Manager. 
- **P1 (1d)** — CockroachDB MCP Server (store/recall/forget) on Lambda + API GW; Titan v2 embeddings; unit tests.
- **P2 (1d)** — EventBridge → consolidation Lambda → Bedrock Claude extraction → semantic memories; hybrid recall path.
- **P3 (1d)** — demo agent on AgentCore Runtime; Gateway wires the MCP server; a concrete use-case (ops/support agent that remembers across sessions).
- **P4 (1d)** — public demo URL (API GW + minimal S3/CloudFront UI); AgentCore Observability dashboard; Well-Architected + security-review gate.
- **P5 (0.5d)** — demo video <3 min via /product-launch-video; README polish; Devpost submit.

## Risks / notes
- **XPRIZE collision (Aug 17 vs Aug 18):** honest flag. Mitigated by stack-orthogonality (this = AWS/Bedrock; XPRIZE = Gemini/Vertex) and the ≤1-week envelope, so it can run as a parallel secondary track or a post-XPRIZE sprint. Re-confirm capacity at the Jul 18 checkpoint.
- **Public-repo IP boundary:** pattern/artifact only — generalized memory-consolidation + knowledge-agent pattern; zero product source, prompts, or SOSA library. README codifies the boundary (XPRIZE precedent).
- **No hard-stop spend:** all Activate-credit-covered, serverless min=0.
