from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

TOOL_NAME = "validate_json_against_schema"
SUPPORTED_TYPES: dict[str, type[Any] | tuple[type[Any], ...]] = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@example.com")


def is_type_match(value: Any, expected_type: str) -> bool:
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, SUPPORTED_TYPES[expected_type])


def validate_payload(input_json: dict[str, Any], schema_obj: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field, expected_type in schema_obj.items():
        if field not in input_json:
            errors.append(f"{field} is required")
            continue
        if not isinstance(expected_type, str) or expected_type not in SUPPORTED_TYPES:
            errors.append(f"{field} has unsupported schema type")
            continue
        if not is_type_match(input_json[field], expected_type):
            errors.append(f"{field} must be {expected_type}")
    return errors


class TaskAppHandler(BaseHTTPRequestHandler):
    server_version = "TaskAppHTTP/1.1"

    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none';",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_json(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._set_headers(status_code=status_code, content_type="application/json")
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _send_text(self, text: str, status_code: int = 200) -> None:
        self._set_headers(status_code=status_code, content_type="text/plain; charset=utf-8")
        self.wfile.write(text.encode("utf-8"))

    def _error_contract(self, request_id: Any, code: str, message: str, status_code: int = 200) -> None:
        payload: dict[str, Any] = {"error": {"code": code, "message": message}}
        if request_id is not None:
            payload = {"jsonrpc": "2.0", "id": request_id, "error": payload["error"]}
        self._send_json(payload, status_code=status_code)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_headers(status_code=204, content_type="application/json")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json({"status": "ok"})
            return

        if path == "/privacy":
            self._send_text(
                "no storage\nno tracking\nno retention\ncontact: " + SUPPORT_EMAIL
            )
            return

        if path == "/terms":
            self._send_text("Use only for deterministic JSON type and required-field validation.")
            return

        if path == "/support":
            self._send_text("contact: " + SUPPORT_EMAIL)
            return

        if path == "/.well-known/openai-apps-challenge":
            self._send_text(os.getenv("OPENAI_APPS_CHALLENGE", ""))
            return

        self._error_contract(None, "NOT_FOUND", "Route not found", status_code=404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/mcp":
            self._error_contract(None, "NOT_FOUND", "Route not found", status_code=404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)

        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._error_contract(None, "INVALID_JSON", "Body must be valid JSON", status_code=400)
            return

        if not isinstance(body, dict):
            self._error_contract(None, "INVALID_REQUEST", "Request must be an object")
            return

        request_id = body.get("id")

        if body.get("jsonrpc") != "2.0":
            self._error_contract(request_id, "INVALID_REQUEST", "jsonrpc must be '2.0'")
            return

        method = body.get("method")
        if method == "tools/list":
            self._send_json(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": TOOL_NAME,
                                "description": "Validate JSON against schema fields and primitive types.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "json": {"type": "object"},
                                        "schema": {"type": "object"},
                                    },
                                    "required": ["json", "schema"],
                                    "additionalProperties": False,
                                },
                            }
                        ]
                    },
                }
            )
            return

        if method != "tools/call":
            self._error_contract(request_id, "METHOD_NOT_FOUND", "Unsupported method")
            return

        params = body.get("params")
        if not isinstance(params, dict):
            self._error_contract(request_id, "INVALID_PARAMS", "params must be an object")
            return

        if params.get("name") != TOOL_NAME:
            self._error_contract(request_id, "INVALID_PARAMS", "Unknown tool name")
            return

        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            self._error_contract(request_id, "INVALID_PARAMS", "arguments must be an object")
            return

        if set(arguments.keys()) != {"json", "schema"}:
            self._error_contract(request_id, "INVALID_PARAMS", "arguments must contain only json and schema")
            return

        input_json = arguments.get("json")
        schema_obj = arguments.get("schema")

        if not isinstance(input_json, dict):
            self._error_contract(request_id, "INVALID_PARAMS", "json must be an object")
            return

        if not isinstance(schema_obj, dict):
            self._error_contract(request_id, "INVALID_PARAMS", "schema must be an object")
            return

        errors = validate_payload(input_json, schema_obj)
        if errors:
            self._error_contract(request_id, "VALIDATION_ERROR", "; ".join(errors))
            return

        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "structuredContent": {
                        "valid": True,
                        "errors": [],
                    }
                },
            }
        )


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = HTTPServer((host, port), TaskAppHandler)
    print(f"Serving on http://{host}:{port}")
    server.serve_forever()


def run_self_tests() -> None:
    import threading
    import time
    from http.client import HTTPConnection

    server = HTTPServer(("127.0.0.1", 8765), TaskAppHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)

    conn = HTTPConnection("127.0.0.1", 8765)

    def post(payload: dict[str, Any]) -> dict[str, Any]:
        conn.request("POST", "/mcp", body=json.dumps(payload), headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        return body

    # Group 1: Direct valid inputs
    direct = post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": TOOL_NAME,
                "arguments": {"json": {"a": 1}, "schema": {"a": "number"}},
            },
        }
    )
    assert direct["result"]["structuredContent"] == {"valid": True, "errors": []}

    # Group 2: Indirect valid inputs
    indirect = post(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": TOOL_NAME,
                "arguments": {"json": {"a": 1, "b": "x"}, "schema": {"a": "number"}},
            },
        }
    )
    assert indirect["result"]["structuredContent"] == {"valid": True, "errors": []}

    # Group 3: Invalid / out-of-scope inputs -> error contract
    invalid = post(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": TOOL_NAME,
                "arguments": {"json": {"a": "x"}, "schema": {"a": "number"}},
            },
        }
    )
    assert "error" in invalid
    assert set(invalid["error"].keys()) == {"code", "message"}

    tools = post({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
    assert len(tools["result"]["tools"]) == 1

    conn.request("GET", "/health")
    health_resp = conn.getresponse()
    health_body = json.loads(health_resp.read().decode("utf-8"))
    assert health_body == {"status": "ok"}
    assert health_resp.getheader("Content-Security-Policy") is not None
    assert health_resp.getheader("X-Content-Type-Options") == "nosniff"
    assert health_resp.getheader("X-Frame-Options") == "DENY"
    assert health_resp.getheader("Referrer-Policy") == "no-referrer"
    assert health_resp.getheader("Access-Control-Allow-Origin") == "*"
    assert health_resp.getheader("Access-Control-Allow-Methods") == "GET,POST,OPTIONS"
    assert health_resp.getheader("Access-Control-Allow-Headers") == "Content-Type"

    for route in ["/privacy", "/terms", "/support", "/.well-known/openai-apps-challenge"]:
        conn.request("GET", route)
        r = conn.getresponse()
        _ = r.read()
        assert r.status in (200,)

    conn.close()
    server.shutdown()
    print("self-tests passed")


if __name__ == "__main__":
    if os.getenv("RUN_SELF_TESTS") == "1":
        run_self_tests()
    else:
        run(port=int(os.getenv("PORT", "8000")))
