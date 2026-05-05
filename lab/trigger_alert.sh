#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

curl -sS http://127.0.0.1:8080/alert \
  -H 'Content-Type: application/json' \
  --data-binary @lab/sample_openresty_5xx_alert.json
