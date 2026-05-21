"""Shared HTTP client for Suno API operations.

Provides request/response helpers used by both the MCP server and the
plugin adapter layer. Built on urllib for zero-dependency stdio transport.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

SUNO_API_KEY = os.environ.get("SUNO_API_KEY", "").strip()
SUNO_BASE_URL = os.environ.get("SUNO_BASE_URL", "https://api.sunoapi.org").rstrip("/")
SUNO_CALLBACK_URL = os.environ.get("SUNO_CALLBACK_URL", "").strip()


def _auth_header() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }


def _require_api_key() -> str | None:
    """Return None if API key is set, else an error message."""
    if not SUNO_API_KEY:
        return (
            "SUNO_API_KEY environment variable is not set. "
            "Get a key at https://sunoapi.org/api-key and set it before using this tool."
        )
    return None


def api_post(path: str, body: dict, timeout: int = 30) -> dict:
    """POST to a Suno API endpoint, return parsed JSON. Adds auth header."""
    url = f"{SUNO_BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            **_auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return err_body
        except Exception:
            return {"code": e.code, "msg": f"HTTP {e.code}: {e.reason}", "_error": True}
    except urllib.error.URLError as e:
        return {"code": 0, "msg": f"Connection error: {e.reason}", "_error": True}


def api_get(path: str, params: dict | None = None, timeout: int = 30) -> dict:
    """GET a Suno API endpoint."""
    url = f"{SUNO_BASE_URL}{path}"
    if params:
        from urllib.parse import quote
        qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            **_auth_header(),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": e.code, "msg": f"HTTP {e.code}: {e.reason}", "_error": True}
    except urllib.error.URLError as e:
        return {"code": 0, "msg": f"Connection error: {e.reason}", "_error": True}


def extract_task_id(response: dict) -> str | None:
    """Best-effort task_id extraction from a Suno API response."""
    if response.get("code") == 200 and isinstance(response.get("data"), dict):
        return response["data"].get("taskId")
    return None
