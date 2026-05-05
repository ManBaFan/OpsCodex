# Ops Harness MVP

Ops Harness is a minimal safety wrapper for running Codex as a read-only SRE diagnosis agent.

The first supported scenario is OpenResty 5xx diagnosis:

```text
Alertmanager / Grafana / Kibana
        -> ops-harness webhook
        -> run directory + prompt
        -> codex exec
        -> read-only tools
        -> Markdown diagnosis report
```

## Quick Start

Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Configure external endpoints in `config/harness.yaml` or environment variables:

```bash
export VM_BASE_URL="http://victoriametrics.example:8428"
export ES_URL="https://elasticsearch.example:9200"
export ES_USERNAME="readonly"
export ES_PASSWORD="..."
export AWS_REGION="ap-northeast-1"
```

Run the webhook:

```bash
python app.py
```

Send a test alert:

```bash
curl -sS http://127.0.0.1:8080/alert \
  -H 'Content-Type: application/json' \
  -d '{"alertname":"OpenResty5xxHigh","service":"demo","namespace":"prd","range":"15m"}'
```

Every invocation is archived under `runs/<run_id>/`:

- `alert.json`
- `prompt.md`
- `command.json`
- `stdout.md`
- `stderr.log`
- `report.md`
- `exit_code`

## Tool Contract

Codex must use only these clients:

```bash
./tools/vm_client query '<promql>'
./tools/vm_client range '<promql>' '15m'
./tools/es_client search --index 'openresty-*' --kql 'status >= 500' --range '15m'
./tools/k8s_client get-pods --cluster aws-jp-common --namespace prd8
./tools/k8s_client get-endpoints --cluster aws-jp-common --namespace prd8 --service hbg-fiat-web
./tools/k8s_client describe-pod --cluster aws-jp-common --namespace prd8 --pod xxx
./tools/aws_client ena-check --instance-id i-xxxx --range 15m
./tools/aws_client nlb-check --target-group xxx --range 15m
./tools/ssh_ro_client openresty-1c-161 'ss -s'
```

The tools enforce read-only command construction and reject known dangerous operations. Production write actions are intentionally out of scope for this MVP.
