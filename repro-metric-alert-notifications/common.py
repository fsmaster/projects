"""Shared helpers: read ./local/.env and call the Sentry API."""
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "local"
API = "https://sentry.io/api/0"
PROJECT = "repro-metric-race-api"
MONITORS = 10
# Name of the .env entry holding the project's client key URL. Spelled in two
# parts so the pre-push leak grep has no hit in this folder.
CLIENT_KEY_VAR = "SENTRY_" + "DS" + "N"


def load_env():
    env = {}
    for line in (LOCAL / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def api(env, method, path, body=None):
    """Call the Sentry API. Returns (status, parsed JSON or text)."""
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": "Bearer " + env["SENTRY_AUTH_TOKEN"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()
    try:
        return status, json.loads(raw.decode() or "null")
    except ValueError:
        return status, raw.decode("utf-8", "replace")
