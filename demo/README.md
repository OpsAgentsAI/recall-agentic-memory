# Recall demo — an ops assistant that survives session death

The demo scenario judges see (< 3 min):

1. **Session 1:** tell the agent things — "we deploy to us-east-1", "always answer
   me in Hebrew", "our on-call rotation flips Mondays".
2. **Consolidation runs** (EventBridge, or trigger via the `consolidate` MCP tool) —
   Bedrock Claude distills those episodes into semantic memories in CockroachDB.
   Show the rows: `SELECT kind, statement, confidence FROM semantic_memories;` —
   the agent's brain is **plain SQL**.
3. **Session 2 (fresh session, next day):** ask "what region do we deploy to?" —
   the agent answers from consolidated memory it was never told in this session,
   in Hebrew, because it *remembers you prefer that*.

## Deploy the demo agent (AgentCore Runtime)

```bash
cd demo/agent
pip install agentcore-cli
agentcore init --framework custom      # wraps app.py
export RECALL_MCP_URL=<DemoUrl output of the SAM stack>
agentcore deploy --region us-east-1
agentcore invoke --agent-name recall-demo \
  --input '{"prompt": "We deploy Recall to us-east-1. Remember that.", "agent_id": "demo", "session_id": "s1"}'
```

Dev/test uses the AgentCore CLI; the runtime resources get pinned as IaC before
submission (production-readiness judging axis).

## Wire the MCP server into AgentCore Gateway (optional richer setup)

Gateway can front the Recall MCP Lambda directly, adding Cedar policy enforcement
(e.g. `forget` requires elevated principal) between agent and memory:

agent → AgentCore Gateway (Cedar Policy) → Recall MCP Lambda → CockroachDB

The demo agent talks to the API Gateway endpoint by default so the demo works
without Gateway provisioning; both paths speak the same MCP JSON-RPC.
