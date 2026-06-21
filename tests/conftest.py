"""Pytest fixtures for the EcoStep Flask server tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(monkeypatch):
    """A Flask test client with a clean rate-limit bucket per test."""
    # Disable Firebase config so /api/config returns the 'local' branch.
    for key in (
        "FIREBASE_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_PROJECT_ID",
        "FIREBASE_STORAGE_BUCKET", "FIREBASE_MESSAGING_SENDER_ID", "FIREBASE_APP_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    import server  # imported after env vars are cleared
    server._rate_buckets.clear()
    server.app.testing = True
    with server.app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def firebase_client(monkeypatch):
    """A test client with a populated Firebase config."""
    monkeypatch.setenv("FIREBASE_API_KEY", "test-api-key-1234567890")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "test-project")
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "test-project.firebaseapp.com")

    import importlib
    import server
    importlib.reload(server)  # rebuild app with the new env

    server._rate_buckets.clear()
    server.app.testing = True
    with server.app.test_client() as test_client:
        yield test_client
