from __future__ import annotations

import json
import os
import pathlib
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any

import yaml
from flask import Flask, jsonify, request


BASE = pathlib.Path(__file__).resolve().parent
RUNS_DIR = BASE / "runs"
PROMPT_FILE = BASE / "prompts" / "openresty_5xx.md"
CONFIG_FILE = BASE / "config" / "harness.yaml"


def load_config() -> dict[str, Any]:
    config_file = pathlib.Path(os.environ.get("OPS_HARNESS_CONFIG", str(CONFIG_FILE)))
    if not config_file.is_absolute():
        config_file = BASE / config_file
    if not config_file.exists():
        return {}
    with config_file.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/alert")
    def alert():
        try:
            alert_body = request.get_json(force=True)
        except Exception as exc:  # pragma: no cover - Flask owns parse details.
            return jsonify({"error": "invalid json", "detail": str(exc)}), 400
        if not isinstance(alert_body, dict):
            return jsonify({"error": "alert body must be a JSON object"}), 400

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid.uuid4())
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        alert_json = json.dumps(alert_body, ensure_ascii=False, indent=2)
        (run_dir / "alert.json").write_text(alert_json, encoding="utf-8")

        prompt_template = PROMPT_FILE.read_text(encoding="utf-8")
        prompt = prompt_template.replace("{{ALERT_JSON}}", alert_json)
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        config = load_config()
        codex_config = config.get("codex", {}) if isinstance(config.get("codex", {}), dict) else {}
        timeout = int(codex_config.get("timeout_seconds", 900))
        command = str(codex_config.get("command", "codex"))
        sandbox = str(codex_config.get("sandbox", "workspace-write"))
        extra_args = codex_config.get("extra_args", [])
        if not isinstance(extra_args, list):
            extra_args = []

        report_file = run_dir / "report.md"
        cmd = [
            command,
            "exec",
            "--cd",
            str(BASE),
            "--sandbox",
            sandbox,
            "--output-last-message",
            str(report_file),
            *[str(arg) for arg in extra_args],
            "-",
        ]
        (run_dir / "command.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env["OPS_HARNESS_RUN_ID"] = run_id
        env["OPS_HARNESS_RUN_DIR"] = str(run_dir)
        env["OPS_HARNESS_ALERT_FILE"] = str(run_dir / "alert.json")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                cwd=BASE,
                env=env,
                input=prompt,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            (run_dir / "timeout.log").write_text(str(exc), encoding="utf-8")
            return jsonify({"run_id": run_id, "error": "codex exec timeout"}), 504
        except FileNotFoundError as exc:
            (run_dir / "startup_error.log").write_text(str(exc), encoding="utf-8")
            return jsonify({"run_id": run_id, "error": "codex command not found", "detail": str(exc)}), 500

        (run_dir / "stdout.md").write_text(result.stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
        (run_dir / "exit_code").write_text(str(result.returncode), encoding="utf-8")
        report = report_file.read_text(encoding="utf-8") if report_file.exists() else result.stdout

        return jsonify(
            {
                "run_id": run_id,
                "exit_code": result.returncode,
                "report": report,
                "stderr": result.stderr,
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=8080)
