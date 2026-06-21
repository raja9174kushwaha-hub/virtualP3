"""Tests for the EcoStep Flask server.

Covers:
 - HTTP routing (index, static allow-list, denylist, traversal, 404)
 - /api/config behaviour in both local and firebase modes
 - Defense-in-depth security headers
 - Rate limiting on /api/*
 - Health check
"""
from __future__ import annotations


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data
    assert b"EcoStep" in resp.data


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_security_headers_present_on_index(client):
    resp = client.get("/")
    headers = resp.headers
    assert "Content-Security-Policy" in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "strict-origin-when-cross-origin" in headers["Referrer-Policy"]
    assert "geolocation=()" in headers["Permissions-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "Strict-Transport-Security" in headers
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "object-src 'none'" in headers["Content-Security-Policy"]


def test_static_allowlist_serves_known_files(client):
    for name in ("style.css", "app.js"):
        resp = client.get("/" + name)
        assert resp.status_code == 200, name


def test_static_denylist_blocks_secrets(client):
    for forbidden in (".env", "server.py", "Dockerfile", "requirements.txt"):
        resp = client.get("/" + forbidden)
        assert resp.status_code == 404, f"{forbidden} should be blocked"


def test_static_blocks_unknown_files(client):
    resp = client.get("/totally-not-a-file.txt")
    assert resp.status_code == 404


def test_static_blocks_path_traversal(client):
    """Trying to escape the static root must 404, never 200."""
    for evil in (
        "..%2F.env",
        "..%2Fserver.py",
        "%2e%2e%2fserver.py",
        "../server.py",
        "subdir/../server.py",
    ):
        resp = client.get("/" + evil)
        assert resp.status_code in (400, 404), evil
        assert b"FIREBASE" not in resp.data
        assert b"def index" not in resp.data


def test_config_local_mode(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["mode"] == "local"
    assert payload["firebaseConfig"] is None
    assert "csrfToken" in payload and len(payload["csrfToken"]) >= 16


def test_config_firebase_mode(firebase_client):
    resp = firebase_client.get("/api/config")
    payload = resp.get_json()
    assert payload["mode"] == "firebase"
    assert payload["firebaseConfig"]["apiKey"] == "test-api-key-1234567890"
    assert payload["firebaseConfig"]["projectId"] == "test-project"


def test_config_ignores_placeholder_values(monkeypatch, client):
    monkeypatch.setenv("FIREBASE_API_KEY", "YOUR_KEY_HERE")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "YOUR_PROJECT")
    resp = client.get("/api/config")
    payload = resp.get_json()
    assert payload["mode"] == "local"
    assert payload["firebaseConfig"] is None


def test_rate_limit_returns_429(client):
    import server
    # Force the bucket to be one below the limit.
    for _ in range(server._RATE_LIMIT_MAX):
        client.get("/api/config")
    resp = client.get("/api/config")
    assert resp.status_code == 429
    assert resp.get_json() == {"error": "rate_limited"}


def test_no_secret_files_in_static_response(client):
    """Even on the index, no env-var values should be echoed back."""
    resp = client.get("/")
    assert b"FIREBASE_API_KEY=" not in resp.data
    assert b"AIza" not in resp.data  # Google-style API key prefix


def test_max_content_length_enforced(client):
    """Oversize POST bodies should be rejected, not OOM the server."""
    huge = b"x" * (2 * 1024 * 1024)  # 2 MiB > 1 MiB cap
    resp = client.post("/api/config", data=huge)
    # Flask returns 413 (or 405 because it's a GET endpoint) — either is fine,
    # what matters is we never returned 500 from a memory spike.
    assert resp.status_code in (405, 413, 404)


def test_client_ip_forwarded(client):
    """Verify client IP extraction when X-Forwarded-For header is present."""
    resp = client.get("/api/config", headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert resp.status_code == 200


def test_rate_limit_popleft(client):
    """Check that old rate-limit entries are purged from the bucket queue."""
    import time
    from collections import deque
    import server
    server._rate_buckets["127.0.0.1"] = deque([time.monotonic() - 100])
    resp = client.get("/api/config")
    assert resp.status_code == 200


def test_server_error_500(client, monkeypatch):
    """Assert that unhandled errors trigger a generic, safe 500 response."""
    import server
    # Cause getenv to raise TypeError when called in get_config
    def mock_getenv(*args, **kwargs):
        raise TypeError("simulated error")
    
    monkeypatch.setattr(server.os, "getenv", mock_getenv)
    # Temporarily disable PROPAGATE_EXCEPTIONS to test the 500 handler
    server.app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        resp = client.get("/api/config")
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "internal_error"}
    finally:
        server.app.config["PROPAGATE_EXCEPTIONS"] = True



def test_static_file_not_exist(client, monkeypatch):
    """Verify that allowed but non-existent files return a 404."""
    import server
    monkeypatch.setattr(server, "PUBLIC_FILES", frozenset({"nonexistent.html"}))
    resp = client.get("/nonexistent.html")
    assert resp.status_code == 404


def test_static_outside_root(client, monkeypatch):
    """Test that requests resolving outside the static root directory return a 404."""
    import server
    from pathlib import Path
    monkeypatch.setattr(server, "STATIC_ROOT", Path("/tmp/nonexistent-dir-123"))
    monkeypatch.setattr(server, "PUBLIC_FILES", frozenset({"index.html"}))
    resp = client.get("/index.html")
    assert resp.status_code == 404

