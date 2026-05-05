#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


NOW = int(time.time())


def prom_vector(metric: dict[str, str], value: float) -> dict[str, Any]:
    return {"metric": metric, "value": [NOW, str(value)]}


def prom_matrix(metric: dict[str, str], values: list[float]) -> dict[str, Any]:
    start = NOW - (len(values) - 1) * 60
    return {"metric": metric, "values": [[start + index * 60, str(value)] for index, value in enumerate(values)]}


def vm_response(query: str, range_query: bool) -> dict[str, Any]:
    query_lc = query.lower()
    if "5xx" in query_lc or "status" in query_lc or "500" in query_lc:
        data = [
            prom_matrix({"host": "openresty-lab-1", "status": "502", "upstream": "hbg-fiat-web"}, [2, 8, 23, 41, 38, 44])
            if range_query
            else prom_vector({"host": "openresty-lab-1", "status": "502", "upstream": "hbg-fiat-web"}, 44),
            prom_matrix({"host": "openresty-lab-2", "status": "502", "upstream": "hbg-fiat-web"}, [0, 1, 1, 2, 1, 2])
            if range_query
            else prom_vector({"host": "openresty-lab-2", "status": "502", "upstream": "hbg-fiat-web"}, 2),
        ]
    elif "upstream" in query_lc and ("time" in query_lc or "latency" in query_lc or "duration" in query_lc):
        data = [
            prom_matrix({"upstream": "hbg-fiat-web", "quantile": "0.99"}, [0.18, 0.25, 1.8, 4.2, 4.8, 5.1])
            if range_query
            else prom_vector({"upstream": "hbg-fiat-web", "quantile": "0.99"}, 5.1)
        ]
    elif "retrans" in query_lc or "allowance" in query_lc or "packet" in query_lc or "network" in query_lc:
        data = [
            prom_matrix({"host": "openresty-lab-1"}, [0, 0, 0, 1, 0, 0])
            if range_query
            else prom_vector({"host": "openresty-lab-1"}, 0)
        ]
    elif "cpu" in query_lc or "load" in query_lc or "memory" in query_lc:
        data = [
            prom_matrix({"host": "openresty-lab-1"}, [0.18, 0.19, 0.21, 0.23, 0.20, 0.22])
            if range_query
            else prom_vector({"host": "openresty-lab-1"}, 0.22)
        ]
    else:
        data = [prom_vector({"scenario": "openresty_5xx_lab"}, 1)]
    return {"status": "success", "data": {"resultType": "matrix" if range_query else "vector", "result": data}}


def es_hits() -> list[dict[str, Any]]:
    messages = [
        "upstream timed out (110: Connection timed out) while reading response header from upstream",
        "connect() failed (111: Connection refused) while connecting to upstream",
        "upstream prematurely closed connection while reading response header from upstream",
        "no live upstreams while connecting to upstream",
    ]
    hits = []
    for index, message in enumerate(messages):
        hits.append(
            {
                "_index": "openresty-2026.05.05",
                "_id": f"lab-{index}",
                "_score": None,
                "_source": {
                    "@timestamp": "2026-05-05T04:20:00Z",
                    "host": "openresty-lab-1",
                    "status": 502 if index != 3 else 504,
                    "request": "GET /api/payment",
                    "upstream": "hbg-fiat-web",
                    "upstream_addr": "10.42.8.17:8080",
                    "upstream_status": "502",
                    "upstream_response_time": 5.004,
                    "request_time": 5.011,
                    "message": message,
                },
            }
        )
    return hits


class Handler(BaseHTTPRequestHandler):
    server_version = "OpsCodexLab/1.0"

    def _write_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        query = params.get("query", [""])[0]
        if parsed.path == "/api/v1/query":
            self._write_json(vm_response(query, range_query=False))
            return
        if parsed.path == "/api/v1/query_range":
            self._write_json(vm_response(query, range_query=True))
            return
        if parsed.path == "/healthz":
            self._write_json({"ok": True})
            return
        self._write_json({"error": "not found", "path": parsed.path}, status=404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.endswith("/_search"):
            self._write_json(
                {
                    "took": 3,
                    "timed_out": False,
                    "hits": {"total": {"value": len(es_hits()), "relation": "eq"}, "hits": es_hits()},
                }
            )
            return
        self._write_json({"error": "not found", "path": parsed.path}, status=404)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vm-port", type=int, default=19090)
    parser.add_argument("--es-port", type=int, default=19200)
    args = parser.parse_args()
    threads = [
        threading.Thread(target=serve, args=(args.vm_port,), daemon=True),
        threading.Thread(target=serve, args=(args.es_port,), daemon=True),
    ]
    for thread in threads:
        thread.start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
