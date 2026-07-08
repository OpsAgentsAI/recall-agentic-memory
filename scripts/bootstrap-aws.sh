#!/usr/bin/env bash
# One-time AWS bootstrap — run ONCE with admin credentials (operator step).
# Creates the GitHub OIDC provider + recall-gha-deployer role; after that every
# deploy is keyless via GitHub Actions (.github/workflows/deploy.yml).
set -euo pipefail

aws cloudformation deploy \
  --stack-name recall-gha-oidc \
  --template-file "$(dirname "$0")/../infra/gha-oidc.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

aws cloudformation describe-stacks --stack-name recall-gha-oidc \
  --query "Stacks[0].Outputs" --output table --region us-east-1

echo "OK — push to main (or re-run the Deploy workflow) and GitHub Actions deploys keylessly."
