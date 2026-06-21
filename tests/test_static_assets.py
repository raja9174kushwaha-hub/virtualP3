"""Static asset checks — accessibility & security regressions caught at CI time."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "style.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "app.js").read_text(encoding="utf-8")


def test_html_has_lang_attribute():
    assert '<html lang="en">' in INDEX


def test_html_has_viewport_meta():
    assert 'name="viewport"' in INDEX


def test_html_has_description_meta():
    assert 'name="description"' in INDEX


def test_html_has_theme_color():
    assert 'name="theme-color"' in INDEX


def test_html_has_favicon():
    assert 'rel="icon"' in INDEX


def test_html_has_skip_link():
    assert 'class="skip-link"' in INDEX
    assert 'href="#main-content"' in INDEX


def test_html_main_landmark_has_id():
    assert 'id="main-content"' in INDEX
    assert '<main' in INDEX


def test_html_app_script_is_deferred():
    import re

    script_tags = re.findall(r"<script[^>]*src=\"app\.js\"[^>]*>", INDEX)
    assert script_tags, "Expected app.js script tag"
    assert any('defer' in tag for tag in script_tags)


def test_html_firebase_scripts_have_crossorigin():
    """Cross-origin script tags pointing at gstatic should declare crossorigin.

    Tags may wrap across lines, so we scan whole <script> blocks, not lines.
    """
    import re

    blocks = re.findall(r"<script[^>]*gstatic\.com/firebasejs[^>]*>", INDEX, re.S)
    assert blocks, "Expected at least one Firebase compat script tag"
    for block in blocks:
        assert 'crossorigin="anonymous"' in block, block
        assert "defer" in block, block


def test_css_defines_skip_link_styles():
    assert ".skip-link" in CSS
    assert "prefers-reduced-motion" in CSS
    assert ".sr-only" in CSS


def test_app_js_strict_mode():
    # Strict mode must appear in the first 60 lines (before any code runs).
    head = "\n".join(APP_JS.splitlines()[:60])
    assert "'use strict'" in head or '"use strict"' in head


def test_app_js_no_obvious_secret_patterns():
    """Guardrail: no hard-coded API keys/tokens checked in."""
    needles = [
        "AIzaSy",       # Google API key prefix
        "sk-proj-",     # OpenAI project key prefix
        "ghp_",         # GitHub personal access token prefix
        "AKIA",         # AWS access key id prefix
    ]
    for needle in needles:
        assert needle not in APP_JS, f"Possible leaked secret prefix: {needle}"


def test_html_buttons_have_accessibility_labels():
    """Verify that all icon/close buttons have proper aria-labels or screen reader descriptions."""
    assert 'aria-label="Toggle Dark/Light Mode"' in INDEX
    assert 'aria-label="Edit Avatar"' in INDEX
    assert 'aria-label="Close rewards marketplace"' in INDEX
    assert 'aria-label="Close modal"' in INDEX


def test_css_defines_focus_visible_styles():
    """Ensure style.css has focus indicators defined for accessibility compliance."""
    assert ".btn:focus-visible" in CSS
    assert ".archetype-selector-small select:focus-visible" in CSS

