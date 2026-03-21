"""Tests for trending tokens fetcher — sanitization, caching, and enrichment."""

import asyncio

import httpx
import pytest

from rugcheck.fetchers.trending import (
    TrendingCache,
    TrendingResponse,
    TrendingToken,
    _build_icon_url,
    _sanitize_text,
    _sanitize_url,
    fetch_trending_solana,
)


# ---------------------------------------------------------------------------
# _sanitize_text
# ---------------------------------------------------------------------------


class TestSanitizeText:
    def test_none_returns_none(self):
        assert _sanitize_text(None) is None

    def test_non_string_returns_none(self):
        assert _sanitize_text(123) is None

    def test_empty_string_returns_none(self):
        assert _sanitize_text("") is None

    def test_normal_text_passes_through(self):
        assert _sanitize_text("Bonk") == "Bonk"

    def test_control_chars_stripped(self):
        assert _sanitize_text("Bo\x00nk\x01\x1b") == "Bonk"

    def test_tabs_and_newlines_preserved(self):
        assert _sanitize_text("Line1\nLine2\tTab") == "Line1\nLine2\tTab"

    def test_max_len_truncation(self):
        long_str = "A" * 500
        result = _sanitize_text(long_str, max_len=80)
        assert len(result) == 80

    def test_only_control_chars_returns_none(self):
        assert _sanitize_text("\x00\x01\x02") is None

    def test_default_max_len_is_280(self):
        long_str = "B" * 300
        result = _sanitize_text(long_str)
        assert len(result) == 280


# ---------------------------------------------------------------------------
# _sanitize_url
# ---------------------------------------------------------------------------


class TestSanitizeUrl:
    def test_none_returns_none(self):
        assert _sanitize_url(None) is None

    def test_empty_returns_none(self):
        assert _sanitize_url("") is None

    def test_non_string_returns_none(self):
        assert _sanitize_url(42) is None

    def test_https_url_passes(self):
        url = "https://dexscreener.com/solana/abc123"
        assert _sanitize_url(url) == url

    def test_http_rejected(self):
        assert _sanitize_url("http://example.com") is None

    def test_javascript_rejected(self):
        assert _sanitize_url("javascript:alert(1)") is None

    def test_data_uri_rejected(self):
        assert _sanitize_url("data:text/html,<h1>XSS</h1>") is None

    def test_url_length_capped_at_2048(self):
        url = "https://example.com/" + "a" * 3000
        result = _sanitize_url(url)
        assert len(result) == 2048

    def test_whitespace_stripped(self):
        assert _sanitize_url("  https://example.com  ") == "https://example.com"


# ---------------------------------------------------------------------------
# _build_icon_url
# ---------------------------------------------------------------------------


class TestBuildIconUrl:
    def test_empty_returns_empty(self):
        assert _build_icon_url("") == ""

    def test_short_id_builds_cdn_url(self):
        result = _build_icon_url("_oTISsfbbH79Kpmp")
        assert result.startswith("https://cdn.dexscreener.com/cms/images/_oTISsfbbH79Kpmp")
        assert "width=64" in result

    def test_dexscreener_cdn_url_passes(self):
        url = "https://cdn.dexscreener.com/cms/images/abc?w=64"
        assert _build_icon_url(url) == url

    def test_arbitrary_http_url_rejected(self):
        """SSRF prevention: non-CDN http(s) URLs must be rejected."""
        assert _build_icon_url("http://169.254.169.254/latest/meta-data") == ""
        assert _build_icon_url("https://evil.com/icon.png") == ""

    def test_http_localhost_rejected(self):
        assert _build_icon_url("http://127.0.0.1:8080/icon") == ""


# ---------------------------------------------------------------------------
# TrendingCache
# ---------------------------------------------------------------------------


class TestTrendingCache:
    @pytest.mark.asyncio
    async def test_empty_cache_returns_none(self):
        cache = TrendingCache(ttl_seconds=60)
        data, age = await cache.get()
        assert data is None
        assert age == 0

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        cache = TrendingCache(ttl_seconds=60)
        resp = TrendingResponse(tokens=[])
        await cache.set(resp)
        data, age = await cache.get()
        assert data is not None
        assert age >= 0

    @pytest.mark.asyncio
    async def test_expired_returns_none(self):
        cache = TrendingCache(ttl_seconds=1)
        resp = TrendingResponse(tokens=[])
        await cache.set(resp)
        # Force timestamp back so age > ttl (avoids real sleep)
        cache._timestamp -= 2
        data, _ = await cache.get()
        assert data is None


# ---------------------------------------------------------------------------
# fetch_trending_solana
# ---------------------------------------------------------------------------


_BOOSTED_RESPONSE = [
    {
        "chainId": "solana",
        "tokenAddress": "So11111111111111111111111111111111111111112",
        "icon": "_testIcon123",
        "description": "Wrapped SOL",
        "url": "https://dexscreener.com/solana/sol",
        "totalAmount": 500,
    },
    {
        "chainId": "ethereum",
        "tokenAddress": "0xabc",
        "totalAmount": 100,
    },
    {
        "chainId": "solana",
        "tokenAddress": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "name": "Jupiter",
        "symbol": "JUP",
        "totalAmount": 300,
    },
]


class TestFetchTrendingSolana:
    @pytest.mark.asyncio
    async def test_filters_solana_only(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=_BOOSTED_RESPONSE)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            tokens = await fetch_trending_solana(client, max_tokens=10)

        # Should exclude the ethereum token
        mints = [t.mint_address for t in tokens]
        assert "0xabc" not in mints
        assert len(tokens) == 2

    @pytest.mark.asyncio
    async def test_deduplicates_mints(self):
        duped = _BOOSTED_RESPONSE + [_BOOSTED_RESPONSE[0]]  # duplicate SOL
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=duped)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            tokens = await fetch_trending_solana(client, max_tokens=10)

        sol_count = sum(
            1 for t in tokens
            if t.mint_address == "So11111111111111111111111111111111111111112"
        )
        assert sol_count == 1

    @pytest.mark.asyncio
    async def test_max_tokens_respected(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=_BOOSTED_RESPONSE)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            tokens = await fetch_trending_solana(client, max_tokens=1)

        assert len(tokens) == 1

    @pytest.mark.asyncio
    async def test_non_list_response_returns_empty(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"error": "unexpected"})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            tokens = await fetch_trending_solana(client)

        assert tokens == []

    @pytest.mark.asyncio
    async def test_sanitizes_description_and_url(self):
        malicious = [
            {
                "chainId": "solana",
                "tokenAddress": "So11111111111111111111111111111111111111112",
                "description": "Safe\x00Token\x01\x1b",
                "url": "javascript:alert(1)",
                "totalAmount": 100,
            },
        ]
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=malicious)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            tokens = await fetch_trending_solana(client)

        assert tokens[0].description == "SafeToken"  # control chars stripped
        assert tokens[0].url is None  # javascript: rejected

    @pytest.mark.asyncio
    async def test_icon_ssrf_blocked(self):
        malicious = [
            {
                "chainId": "solana",
                "tokenAddress": "So11111111111111111111111111111111111111112",
                "icon": "http://169.254.169.254/meta",
                "totalAmount": 100,
            },
        ]
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=malicious)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            tokens = await fetch_trending_solana(client)

        assert tokens[0].icon_url is None or tokens[0].icon_url == ""
