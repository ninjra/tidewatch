#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Example: Tidewatch as a REST scoring API.

Minimal HTTP server using stdlib only. Production deployments should
use FastAPI, Flask, or similar.

Usage:
    python examples/api_server.py
    curl -X POST http://localhost:8090/score -H "Content-Type: application/json" -d @examples/sample_payload.json

Endpoints:
    POST /score    — score a batch of obligations, return ranked results
    GET  /health   — health check
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from tidewatch import Obligation, recalculate_batch

PORT = 8090


class TidewatchHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "version": "0.4.4"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/score":
            self._respond(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return

        now = datetime.now(UTC)
        obligations = []
        for item in payload.get("obligations", []):
            due_str = item.get("due_date")
            due = datetime.fromisoformat(due_str) if due_str else now + timedelta(days=7)

            obligations.append(Obligation(
                id=item.get("id", 0),
                title=item.get("title", ""),
                due_date=due,
                materiality=item.get("materiality", "routine"),
                dependency_count=item.get("dependency_count", 0),
                completion_pct=item.get("completion_pct", 0.0),
                domain=item.get("domain"),
            ))

        results = recalculate_batch(obligations, now=now)

        response = {
            "scored_at": now.isoformat(),
            "count": len(results),
            "results": [
                {
                    "obligation_id": r.obligation_id,
                    "pressure": round(r.pressure, 6),
                    "zone": r.zone,
                    "factors": {
                        "time_pressure": round(r.time_pressure, 6),
                        "materiality": round(r.materiality_mult, 2),
                        "dependency_amp": round(r.dependency_amp, 6),
                        "completion_damp": round(r.completion_damp, 6),
                    },
                }
                for r in results
            ],
        }
        self._respond(200, response)

    def _respond(self, code: int, data: dict):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quiet logging
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), TidewatchHandler)
    print(f"Tidewatch scoring API running on http://localhost:{PORT}")
    print("  POST /score  — score obligations")
    print("  GET  /health — health check")
    print()
    print("Example:")
    print(f'  curl -X POST http://localhost:{PORT}/score \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"obligations": [{"id": 1, "title": "Test", "due_date": "2026-06-15T12:00:00+00:00", "materiality": "material", "dependency_count": 5}]}\'')
    server.serve_forever()
