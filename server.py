"""EcoStep Flask server.

Serves the single-page client, exposes the Firebase web config at /api/config
(read from environment variables only — never from a checked-in file), and
applies strong defense-in-depth headers, rate limiting, and a strict path
allow-list so the static directory cannot leak secrets or escape its root.
"""

from __future__ import annotations

import gzip
import io
import logging
import mimetypes
import os
import secrets
import time
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Deque, Dict

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_ROOT = BASE_DIR

# Files that must NEVER be served, even if a user requests them by name.
DENYLIST = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "server.py",
        "Dockerfile",
        "requirements.txt",
        "requirements-dev.txt",
        ".gitignore",
        ".dockerignore",
        "server.err.log",
        "server.log",
        ".coverage",
        "TRDofvirtualEco.pdf",
    }
)

# Public assets the SPA is allowed to request. Anything outside this set is
# rejected before touching the filesystem, which neutralises path-traversal.
PUBLIC_FILES = frozenset(
    {
        "index.html",
        "style.css",
        "app.js",
        "favicon.ico",
        "robots.txt",
        "manifest.webmanifest",
    }
)

# Per-IP token bucket for /api/* endpoints.
_RATE_LIMIT_WINDOW_S = 60
_RATE_LIMIT_MAX = 60
_rate_buckets: Dict[str, Deque[float]] = {}
_rate_lock = Lock()


def _client_ip() -> str:
    """Return the request's best-known client IP, honouring a trusted proxy."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _rate_limited(key: str) -> bool:
    """Return True iff `key` has exceeded the rate window."""
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_S
    with _rate_lock:
        bucket = _rate_buckets.setdefault(key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_MAX:
            return True
        bucket.append(now)
        return False


def create_app() -> Flask:
    """Application factory — used by gunicorn and by the test suite."""
    flask_app = Flask(__name__, static_folder=None)
    flask_app.config.update(
        SEND_FILE_MAX_AGE_DEFAULT=3600,
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,  # 1 MiB request cap
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    @flask_app.after_request
    def _security_headers(resp: Response) -> Response:
        # A strict CSP that still allows the Firebase JS SDK on gstatic.com and
        # Google identity / Firestore endpoints used by the client.
        csp = (
            "default-src 'self'; "
            "script-src 'self' https://www.gstatic.com https://apis.google.com https://www.google.com; "
            "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' "
            "https://*.googleapis.com https://*.firebaseio.com "
            "https://identitytoolkit.googleapis.com "
            "https://securetoken.googleapis.com "
            "https://firestore.googleapis.com "
            "https://www.gstatic.com "
            "https://www.google.com; "
            "frame-src 'self' https://*.firebaseapp.com https://www.google.com https://recaptcha.google.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "object-src 'none'"
        )
        resp.headers.setdefault("Content-Security-Policy", csp)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        resp.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        resp.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return resp

    @flask_app.after_request
    def _cache_control(resp: Response) -> Response:
        path = request.path
        if (
            path.endswith(".css")
            or path.endswith(".js")
            or path.endswith(".ico")
            or path.endswith(".webmanifest")
        ):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path == "/" or path.endswith(".html"):
            resp.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        elif path.startswith("/api/") or path in ("/health", "/healthz"):
            resp.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    @flask_app.after_request
    def _compress_response(resp: Response) -> Response:
        accept_encoding = request.headers.get("Accept-Encoding", "")
        if "gzip" not in accept_encoding.lower():
            return resp

        content_type = resp.headers.get("Content-Type", "").lower()
        is_compressible = (
            "text/html" in content_type
            or "text/css" in content_type
            or "javascript" in content_type
            or "json" in content_type
            or "text/plain" in content_type
            or "xml" in content_type
            or "svg" in content_type
        )
        if not is_compressible:
            return resp

        if "Content-Encoding" in resp.headers:
            return resp

        if resp.direct_passthrough:
            resp.direct_passthrough = False

        data = resp.get_data()
        if len(data) < 500:
            return resp

        gzip_buffer = io.BytesIO()
        with gzip.GzipFile(
            mode="wb", compresslevel=6, fileobj=gzip_buffer
        ) as gzip_file:
            gzip_file.write(data)

        compressed_data = gzip_buffer.getvalue()
        resp.set_data(compressed_data)
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Content-Length"] = str(len(compressed_data))

        vary = resp.headers.get("Vary", "")
        if "Accept-Encoding" not in vary:
            resp.headers["Vary"] = f"{vary}, Accept-Encoding".strip(", ")

        return resp

    @flask_app.errorhandler(404)
    def _not_found(_err):
        return jsonify({"error": "not_found"}), 404

    @flask_app.errorhandler(429)
    def _too_many(_err):
        return jsonify({"error": "rate_limited"}), 429

    @flask_app.errorhandler(500)
    def _server_error(_err):
        # Never leak internal errors in the response body.
        flask_app.logger.exception("Unhandled error")
        return jsonify({"error": "internal_error"}), 500

    @flask_app.route("/healthz")
    @flask_app.route("/health")
    def healthz():
        return jsonify({"status": "ok"})

    @flask_app.route("/")
    def index():
        return send_from_directory(STATIC_ROOT, "index.html")

    @flask_app.route("/<path:requested>")
    def serve_static(requested: str):
        # Normalise and forbid traversal segments.
        if requested in DENYLIST or requested not in PUBLIC_FILES:
            abort(404)
        target = (STATIC_ROOT / requested).resolve()
        # Ensure the resolved path stays inside the static root.
        if STATIC_ROOT not in target.parents and target != STATIC_ROOT:
            abort(404)
        if not target.is_file():
            abort(404)
        mime, _ = mimetypes.guess_type(target.name)
        return send_from_directory(
            STATIC_ROOT,
            requested,
            mimetype=mime or "application/octet-stream",
        )

    @flask_app.route("/api/config")
    def get_config():
        if _rate_limited(_client_ip()):
            abort(429)

        api_key = os.getenv("FIREBASE_API_KEY", "")
        project_id = os.getenv("FIREBASE_PROJECT_ID", "")

        is_valid = (
            bool(api_key)
            and bool(project_id)
            and not (api_key.startswith("YOUR_") or project_id.startswith("YOUR_"))
        )
        config = {
            "apiKey": api_key,
            "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
            "projectId": project_id,
            "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
            "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
            "appId": os.getenv("FIREBASE_APP_ID", ""),
        }
        return jsonify(
            {
                "firebaseConfig": config if is_valid else None,
                "mode": "firebase" if is_valid else "local",
                "csrfToken": secrets.token_urlsafe(32),
            }
        )

    return flask_app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.logger.info("EcoStep server starting on http://0.0.0.0:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)  # nosec B104
