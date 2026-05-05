from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - covered by deployment dependency check.
    yaml = None


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_FILE = BASE_DIR / "config" / "harness.yaml"
DURATION_RE = re.compile(r"^(?P<value>[1-9][0-9]*)(?P<unit>s|m|h|d)$")
ENV_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def emit(payload: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


def fail(message: str, exit_code: int = 2, **extra: Any) -> None:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    emit(payload, exit_code)


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        match = ENV_RE.match(value)
        if match:
            return os.environ.get(match.group(1), "")
        return value
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def load_config() -> dict[str, Any]:
    config_path = pathlib.Path(os.environ.get("OPS_HARNESS_CONFIG", str(DEFAULT_CONFIG_FILE)))
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path
    if not config_path.exists() or yaml is None:
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        fail("config/harness.yaml must contain a YAML mapping")
    return _expand_env(data)


def tool_config(name: str) -> dict[str, Any]:
    tools = load_config().get("tools", {})
    if not isinstance(tools, dict):
        return {}
    config = tools.get(name, {})
    return config if isinstance(config, dict) else {}


def default_timeout(config: dict[str, Any], fallback: int = 20) -> int:
    value = config.get("timeout_seconds", fallback)
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        fail("timeout_seconds must be an integer", value=value)
    if timeout <= 0 or timeout > 300:
        fail("timeout_seconds must be between 1 and 300", value=value)
    return timeout


def parse_duration_seconds(value: str) -> int:
    match = DURATION_RE.match(value)
    if not match:
        fail("duration must use a compact form like 15m, 1h, or 30s", value=value)
    amount = int(match.group("value"))
    unit = match.group("unit")
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    seconds = amount * multiplier
    if seconds <= 0 or seconds > 7 * 86400:
        fail("duration must be between 1 second and 7 days", value=value)
    return seconds


def utc_window(value: str) -> tuple[str, str, int]:
    seconds = parse_duration_seconds(value)
    end = int(time.time())
    start = end - seconds
    return (
        datetime.fromtimestamp(start, timezone.utc).isoformat().replace("+00:00", "Z"),
        datetime.fromtimestamp(end, timezone.utc).isoformat().replace("+00:00", "Z"),
        seconds,
    )


def command_result(command: list[str], timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": f"command not found: {command[0]}",
            "exception": str(exc),
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": "command timeout",
            "command": command,
            "timeout_seconds": timeout,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }

    return {
        "ok": proc.returncode == 0,
        "command": command,
        "exit_code": proc.returncode,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def require_name(value: str, label: str) -> str:
    if not re.match(r"^[A-Za-z0-9_.:/@=-]+$", value):
        fail(f"{label} contains unsupported characters", value=value)
    return value


def parse_json_output(result: dict[str, Any]) -> dict[str, Any]:
    stdout = result.get("stdout", "")
    if not stdout:
        return {"parse_ok": False, "data": None}
    try:
        return {"parse_ok": True, "data": json.loads(stdout)}
    except json.JSONDecodeError as exc:
        return {"parse_ok": False, "error": str(exc), "data": None}
