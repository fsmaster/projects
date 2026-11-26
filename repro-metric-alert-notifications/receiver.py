#!/usr/bin/env python3
"""Webhook receiver for the metric-alert notification repro.

Appends {received_at, headers, body} to ./local/webhooks.jsonl and always
answers 204. If SENTRY_APP_CLIENT_SECRET is set in ./local/.env, the
Sentry-Hook-Signature header (hex HMAC-SHA256 of the raw body) is checked and
the result recorded as signature_ok; the answer is 204 either way.
"""
import hashlib
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "local"
ENV_FILE = LOCAL / ".env"
OUT = LOCAL / "webhooks.jsonl"
HOST = os.environ.get("RECEIVER_HOST", "127.0.0.1")
PORT = int(os.environ.get("RECEIVER_PORT", "8787"))

_lock = threading.Lock()
_env_cache = {"mtime": None, "values": {}}


def read_env():
    """Parse ./local/.env, re-reading only when the file changes."""
    try:
        mtime = ENV_FILE.stat().st_mtime
    except OSError:
        return {}
    if _env_cache["mtime"] != mtime:
        values = {}
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
        _env_cache["mtime"] = mtime
        _env_cache["values"] = values
    return _env_cache["values"]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _answer(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.wfile.flush()

    def do_POST(self):
        received_at = time.time()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        # Answer first, record second: the answer never waits on the disk.
        self._answer()

        secret = read_env().get("SENTRY_APP_CLIENT_SECRET") or ""
        signature_ok = None
        if secret:
            expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            got = self.headers.get("Sentry-Hook-Signature") or ""
            signature_ok = hmac.compare_digest(expected, got)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = raw.decode("utf-8", "replace")
        record = {
            "received_at": received_at,
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "signature_ok": signature_ok,
            "body": body,
        }
        with _lock:
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    def do_GET(self):
        self._answer()

    def log_message(self, fmt, *args):
        pass


def main():
    LOCAL.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"receiver listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
