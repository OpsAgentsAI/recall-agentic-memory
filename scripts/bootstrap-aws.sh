#!/usr/bin/env bash
# One-time AWS bootstrap — run ONCE with local admin credentials (operator step).
# End state: keyless GitHub-Actions deploys + live stack + runtime DB secret filled.
#
#   1. Deploy the OIDC bootstrap stack (GitHub OIDC provider + recall-gha-deployer role)
#   2. Trigger the Deploy workflow (sam build/deploy via OIDC) and wait for it
#   3. Fill the SAM-created AWS Secrets Manager secret with the CockroachDB DSN
#      (from ~/.recall-crdb-dsn, staged by provision-ccloud.sh — never printed)
#   4. Smoke the live MCP endpoint end-to-end (store + recall against CockroachDB)
set -euo pipefail

REGION=us-east-1
DSN_FILE="${DSN_FILE:-$HOME/.recall-crdb-dsn}"

echo "==> [1/4] OIDC bootstrap stack"
aws cloudformation deploy \
  --stack-name recall-gha-oidc \
  --template-file "$(dirname "$0")/../infra/gha-oidc.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${REGION}"

echo "==> [2/4] First deploy via GitHub Actions (keyless)"
gh workflow run deploy.yml --repo OpsAgentsAI/recall-agentic-memory
sleep 10
RUN_ID=$(gh run list --repo OpsAgentsAI/recall-agentic-memory --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "${RUN_ID}" --repo OpsAgentsAI/recall-agentic-memory --exit-status || {
  echo "Deploy run failed — inspect: gh run view ${RUN_ID} --log-failed" >&2; exit 1; }

echo "==> [3/4] Fill runtime DB secret (recall/crdb-connection)"
[ -s "${DSN_FILE}" ] || { echo "Missing ${DSN_FILE} — run scripts/provision-ccloud.sh first." >&2; exit 1; }
aws secretsmanager put-secret-value \
  --secret-id recall/crdb-connection \
  --secret-string "file://${DSN_FILE}" \
  --region "${REGION}" >/dev/null
echo "secret filled (value from ${DSN_FILE}, not echoed)"

echo "==> [4/4] End-to-end smoke against the live MCP endpoint"
URL=$(aws cloudformation describe-stacks --stack-name recall --region "${REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='DemoUrl'].OutputValue" --output text)
curl -sf -X POST "${URL}" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"tools/call",
  "params":{"name":"store_memory","arguments":{
    "agent_id":"bootstrap-smoke","session_id":"s0","role":"user",
    "content":"bootstrap smoke: Recall is live on AWS us-east-1"}}}' >/dev/null
curl -sf -X POST "${URL}" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":2,"method":"tools/call",
  "params":{"name":"recall","arguments":{
    "agent_id":"bootstrap-smoke","query":"where is Recall live?","k":1}}}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); p=json.loads(r['result']['content'][0]['text']); assert p['memories'], 'no memories recalled'; print('E2E SMOKE OK:', p['memories'][0]['text'])"

echo "DemoUrl: ${URL}"
echo "OK — keyless deploys armed, stack live, memory loop verified end-to-end."
echo "Next: flip deploy.yml back to on-push (agent task)."
