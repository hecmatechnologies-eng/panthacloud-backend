"""Unit tests for origin guardrails and alias derivation."""


from app.core.origins import (
    get_origin_aliases,
    is_preview_origin,
    is_private_or_loopback_origin,
    normalize_origin,
)


def test_normalize_origin_standard():
    assert normalize_origin("https://sweets.com") == "https://sweets.com"
    assert normalize_origin("https://www.sweets.com/") == "https://www.sweets.com"
    assert normalize_origin("http://localhost:3000") == "http://localhost:3000"


def test_get_origin_aliases_apex_and_www():
    aliases = get_origin_aliases("https://sweets.com")
    assert aliases == ["https://sweets.com", "https://www.sweets.com"]

    aliases_www = get_origin_aliases("https://www.sweets.com")
    assert aliases_www == ["https://www.sweets.com", "https://sweets.com"]


def test_get_origin_aliases_localhost_no_alias():
    aliases = get_origin_aliases("http://localhost:3000")
    assert aliases == ["http://localhost:3000"]


def test_get_origin_aliases_preview_no_alias():
    aliases = get_origin_aliases("https://my-app.vercel.app")
    assert aliases == ["https://my-app.vercel.app"]


def test_is_private_or_loopback_origin():
    assert is_private_or_loopback_origin("http://localhost:3000") is True
    assert is_private_or_loopback_origin("http://127.0.0.1:8000") is True
    assert is_private_or_loopback_origin("https://10.0.1.5:443") is True
    assert is_private_or_loopback_origin("https://192.168.1.100") is True
    assert is_private_or_loopback_origin("https://my-tunnel.ngrok.io") is True
    assert is_private_or_loopback_origin("https://free-tunnel.loca.lt") is True

    # Real public domain
    assert is_private_or_loopback_origin("https://sweets.com") is False
    assert is_private_or_loopback_origin("https://app.sweets.com") is False
    assert is_private_or_loopback_origin("https://my-app.vercel.app") is False


def test_is_preview_origin():
    assert is_preview_origin("https://my-site-preview-123.vercel.app") is True
    assert is_preview_origin("https://sweetstore.netlify.app") is True
    assert is_preview_origin("https://feature-branch.pages.dev") is True
    assert is_preview_origin("https://main.amplifyapp.com") is True

    assert is_preview_origin("https://sweets.com") is False
    assert is_preview_origin("https://google.com") is False
