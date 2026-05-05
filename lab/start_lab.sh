#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p /opt/opscodex-lab/logs/openresty run

cat >/opt/opscodex-lab/logs/openresty/error.log <<'LOG'
2026/05/05 12:15:12 [error] 1212#1212: *881 upstream timed out (110: Connection timed out) while reading response header from upstream, upstream: "http://10.42.8.17:8080/api/payment", host: "api.lab"
2026/05/05 12:16:03 [error] 1212#1212: *904 connect() failed (111: Connection refused) while connecting to upstream, upstream: "http://10.42.8.17:8080/api/payment", host: "api.lab"
2026/05/05 12:17:31 [error] 1212#1212: *932 upstream prematurely closed connection while reading response header from upstream, upstream: "http://10.42.8.17:8080/api/payment", host: "api.lab"
LOG

export OPS_HARNESS_CONFIG="$ROOT/config/harness.lab.yaml"
export OPSCODEX_LAB_KUBECTL="$ROOT/lab/mock_kubectl"
export OPSCODEX_LAB_AWS="$ROOT/lab/mock_aws"

if [ "$(id -u)" -eq 0 ]; then
  mkdir -p /root/.ssh
  chmod 700 /root/.ssh
  if [ ! -f /root/.ssh/id_ed25519_opscodex_lab ]; then
    ssh-keygen -t ed25519 -C "opscodex-lab-localhost" -f /root/.ssh/id_ed25519_opscodex_lab -N "" >/dev/null
  fi
  touch /root/.ssh/authorized_keys /root/.ssh/config
  chmod 600 /root/.ssh/authorized_keys /root/.ssh/config
  pub_key="$(cat /root/.ssh/id_ed25519_opscodex_lab.pub)"
  if ! grep -Fq "$pub_key" /root/.ssh/authorized_keys; then
    printf '%s\n' "$pub_key" >>/root/.ssh/authorized_keys
  fi
  if ! grep -Fq "Host opscodex-lab-localhost" /root/.ssh/config; then
    cat >>/root/.ssh/config <<'SSHCONFIG'

Host opscodex-lab-localhost localhost 127.0.0.1 kobe openresty-lab-1 i-lab-openresty-1
    HostName localhost
    User root
    IdentityFile ~/.ssh/id_ed25519_opscodex_lab
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
SSHCONFIG
  fi
  if ! grep -Fq "Host openresty-lab-1 i-lab-openresty-1" /root/.ssh/config; then
    cat >>/root/.ssh/config <<'SSHCONFIG'

Host openresty-lab-1 i-lab-openresty-1
    HostName localhost
    User root
    IdentityFile ~/.ssh/id_ed25519_opscodex_lab
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
SSHCONFIG
  fi
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt

if [ -f run/mock_observability.pid ] && kill -0 "$(cat run/mock_observability.pid)" 2>/dev/null; then
  echo "mock_observability already running"
else
  nohup python lab/mock_observability.py >run/mock_observability.log 2>&1 &
  echo "$!" >run/mock_observability.pid
fi

if [ -f run/ops_harness.pid ] && kill -0 "$(cat run/ops_harness.pid)" 2>/dev/null; then
  echo "ops_harness already running"
else
  nohup python app.py >run/ops_harness.log 2>&1 &
  echo "$!" >run/ops_harness.pid
fi

for url in http://127.0.0.1:19090/healthz http://127.0.0.1:8080/healthz; do
  for _ in {1..30}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
done

echo "lab started"
echo "OPS_HARNESS_CONFIG=$OPS_HARNESS_CONFIG"
echo "mock_observability_pid=$(cat run/mock_observability.pid)"
echo "ops_harness_pid=$(cat run/ops_harness.pid)"
