#!/usr/bin/env bash
# Provision the CockroachDB Serverless free-tier cluster + schema — CRDB tool #3 (ccloud CLI).
# GATE: requires a CockroachDB Cloud account + `ccloud auth login` (operator step).
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-recall-memory}"
CLOUD_PROVIDER="${CLOUD_PROVIDER:-AWS}"
REGION="${REGION:-us-east-1}"

command -v ccloud >/dev/null || {
  echo "ccloud CLI not installed — https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started" >&2
  exit 1
}

echo "==> Creating serverless cluster ${CLUSTER_NAME} (${CLOUD_PROVIDER}/${REGION})"
ccloud cluster create serverless "${CLUSTER_NAME}" --cloud "${CLOUD_PROVIDER}" --region "${REGION}" || true

echo "==> Fetching connection string"
CONN=$(ccloud cluster sql-url "${CLUSTER_NAME}")

echo "==> Applying schema"
psql "${CONN}" -f "$(dirname "$0")/../schema/001_init.sql"

echo "==> Pushing connection string to AWS Secrets Manager (recall/crdb-connection)"
aws secretsmanager put-secret-value \
  --secret-id recall/crdb-connection \
  --secret-string "${CONN}"

echo "OK — cluster provisioned, schema applied, secret set."
