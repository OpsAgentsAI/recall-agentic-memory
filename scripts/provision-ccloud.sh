#!/usr/bin/env bash
# Provision the CockroachDB Serverless cluster + SQL user + schema — CRDB tool #3 (ccloud CLI).
# Requires `ccloud auth login` (operator step, real TTY).
# Idempotent: skips cluster/user creation if they already exist.
#
# State as provisioned 2026-07-08: cluster `crabby-phantom` (Basic, AWS us-east-1,
# v25.4), user `recall_app`, schema applied, DSN staged at ~/.recall-crdb-dsn and
# stored durably in GCP Secret Manager (opsagent-prod / recall-crdb-connection).
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-crabby-phantom}"
SQL_USER="${SQL_USER:-recall_app}"
CLOUD_PROVIDER="${CLOUD_PROVIDER:-AWS}"
REGION="${REGION:-us-east-1}"
DSN_FILE="${DSN_FILE:-$HOME/.recall-crdb-dsn}"

command -v ccloud >/dev/null || {
  echo "ccloud CLI not installed — brew install cockroachdb/tap/ccloud" >&2
  exit 1
}

if ! ccloud cluster info "${CLUSTER_NAME}" --quiet >/dev/null 2>&1; then
  echo "==> Creating serverless cluster ${CLUSTER_NAME} (${CLOUD_PROVIDER}/${REGION})"
  ccloud cluster create serverless "${CLUSTER_NAME}" --cloud "${CLOUD_PROVIDER}" --region "${REGION}"
fi

if ! ccloud cluster user list "${CLUSTER_NAME}" --quiet --hide-header 2>/dev/null | grep -qx "${SQL_USER}"; then
  echo "==> Creating SQL user ${SQL_USER} (password minted locally, never printed)"
  PW=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-28)
  ccloud cluster user create "${CLUSTER_NAME}" "${SQL_USER}" -p "${PW}" --quiet
  BASE=$(ccloud cluster connection-string "${CLUSTER_NAME}" --sql-user "${SQL_USER}" --database defaultdb --quiet \
         | grep -o 'postgresql://[^ ]*' | head -1)
  DSN=$(printf '%s' "${BASE}" | sed "s#${SQL_USER}\(:<ENTER-SQL-USER-PASSWORD>\)\{0,1\}@#${SQL_USER}:${PW}@#")"&sslrootcert=system"
  umask 177 && printf '%s' "${DSN}" > "${DSN_FILE}"
  echo "==> DSN staged at ${DSN_FILE}"
fi

[ -s "${DSN_FILE}" ] || { echo "No DSN at ${DSN_FILE} — user existed but DSN was never staged. Reset the user: ccloud cluster user delete ${CLUSTER_NAME} ${SQL_USER}, then re-run." >&2; exit 1; }
DSN="$(cat "${DSN_FILE}")"

echo "==> Live test"
psql -v ON_ERROR_STOP=1 "${DSN}" -tAc "SELECT current_user" >/dev/null

echo "==> Applying schema"
psql -v ON_ERROR_STOP=1 "${DSN}" -f "$(dirname "$0")/../schema/001_init.sql"

echo "==> Storing durably in GCP Secret Manager (house convention)"
gcloud secrets describe recall-crdb-connection --project=opsagent-prod >/dev/null 2>&1 \
  || gcloud secrets create recall-crdb-connection --project=opsagent-prod --replication-policy=automatic
gcloud secrets versions add recall-crdb-connection --project=opsagent-prod --data-file="${DSN_FILE}"

echo "OK — cluster + user + schema ready; DSN in ${DSN_FILE} and GCP SM."
echo "AWS Secrets Manager (runtime consumer) is filled by scripts/bootstrap-aws.sh after the first deploy."
