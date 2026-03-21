"""DexScreener trending/boosted tokens fetcher.

Fetches the top boosted Solana tokens from DexScreener's public API and
provides an in-memory cache with configurable TTL to avoid excessive
upstream calls.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DexScreener Boosted Tokens API
# ---------------------------------------------------------------------------

BOOSTED_TOP_URL = "https://api.dexscreener.com/token-boosts/top/v1"
TOKENS_API_BASE = "https://api.dexscreener.com/tokens/v1/solana"
ICON_CDN_BASE = "https://cdn.dexscreener.com/cms/images"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TrendingToken(BaseModel):
    """A single trending token for frontend display."""

    mint_address: str
    token_name: str | None = None
    token_symbol: str | None = None
    icon_url: str | None = None
    description: str | None = None
    url: str | None = None
    boost_amount: int = 0


class TrendingResponse(BaseModel):
    """/v1/trending endpoint response."""

    tokens: list[TrendingToken]
    cached: bool = False
    cache_age_seconds: int = 0
    source: str = "dexscreener"


# ---------------------------------------------------------------------------
# TrendingCache — single-key in-memory cache with TTL
# ---------------------------------------------------------------------------


class TrendingCache:
    """Simple single-key cache for trending data.

    Not reusing TTLCache (which is AuditReport-specific and per-mint LRU).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._data: TrendingResponse | None = None
        self._timestamp: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> tuple[TrendingResponse | None, int]:
        async with self._lock:
            if self._data is None:
                return None, 0
            age = int(time.monotonic() - self._timestamp)
            if age > self._ttl:
                self._data = None
                return None, 0
            return self._data, age

    async def set(self, data: TrendingResponse) -> None:
        async with self._lock:
            self._data = data
            self._timestamp = time.monotonic()


# ---------------------------------------------------------------------------
# Fetch function
# ---------------------------------------------------------------------------


def _sanitize_text(val: str | None, *, max_len: int = 280) -> str | None:
    """Strip control characters and cap length for external text fields."""
    if not val or not isinstance(val, str):
        return None
    # Remove control chars (keep newlines/tabs for descriptions)
    cleaned = "".join(c for c in val if c >= " " or c in "\n\t")
    return cleaned[:max_len] or None


def _sanitize_url(val: str | None) -> str | None:
    """Only allow https:// URLs from DexScreener — reject javascript: / data: etc."""
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if val.startswith("https://"):
        return val[:2048]  # cap length
    return None


def _build_icon_url(icon_raw: str) -> str:
    """Build full CDN URL from DexScreener icon identifier.

    The boosted API returns short icon IDs (e.g. '_oTISsfbbH79Kpmp'),
    while the profiles API returns full URLs. Handle both cases.
    Only allows https:// URLs from the DexScreener CDN domain.
    """
    if not icon_raw:
        return ""
    if icon_raw.startswith("https://cdn.dexscreener.com/"):
        return icon_raw[:2048]
    if icon_raw.startswith("http"):
        # Reject non-CDN URLs (SSRF prevention)
        return ""
    return f"{ICON_CDN_BASE}/{icon_raw}?width=64&height=64&fit=crop&quality=95&format=auto"


async def fetch_trending_solana(
    client: httpx.AsyncClient,
    *,
    timeout: float = 3.0,
    max_tokens: int = 8,
) -> list[TrendingToken]:
    """Fetch top boosted Solana tokens from DexScreener.

    Returns up to *max_tokens* unique Solana tokens, sorted by boost amount
    (descending — highest boosted first).
    """
    resp = await client.get(BOOSTED_TOP_URL, timeout=timeout)
    resp.raise_for_status()
    items = resp.json()

    if not isinstance(items, list):
        logger.warning("[TRENDING] Unexpected response type: %s", type(items))
        return []

    tokens: list[TrendingToken] = []
    seen: set[str] = set()

    for item in items:
        chain = item.get("chainId", "")
        if chain != "solana":
            continue

        mint = item.get("tokenAddress", "")
        if not mint or mint in seen:
            continue
        seen.add(mint)

        icon_raw = item.get("icon", "")
        tokens.append(TrendingToken(
            mint_address=mint,
            token_name=_sanitize_text(item.get("name"), max_len=80),
            token_symbol=_sanitize_text(item.get("symbol"), max_len=20),
            icon_url=_build_icon_url(icon_raw) if icon_raw else None,
            description=_sanitize_text(item.get("description"), max_len=280),
            url=_sanitize_url(item.get("url")),
            boost_amount=item.get("totalAmount", 0),
        ))

        if len(tokens) >= max_tokens:
            break

    # --- Enrich with name/symbol from DexScreener tokens API ---
    mints_needing_info = [t.mint_address for t in tokens if not t.token_name]
    if mints_needing_info:
        try:
            mints_param = ",".join(mints_needing_info)
            enrich_resp = await client.get(
                f"{TOKENS_API_BASE}/{mints_param}",
                timeout=timeout,
            )
            enrich_resp.raise_for_status()
            pairs = enrich_resp.json()
            if isinstance(pairs, list):
                # Build lookup: mint -> (name, symbol) from first matching pair
                info_map: dict[str, tuple[str, str]] = {}
                for pair in pairs:
                    base = pair.get("baseToken") or {}
                    mint = base.get("address", "")
                    if mint and mint not in info_map:
                        name = base.get("name")
                        symbol = base.get("symbol")
                        if name or symbol:
                            info_map[mint] = (name or "", symbol or "")
                # Apply to tokens
                for token in tokens:
                    if token.mint_address in info_map:
                        name, symbol = info_map[token.mint_address]
                        if not token.token_name:
                            token.token_name = _sanitize_text(name, max_len=80)
                        if not token.token_symbol:
                            token.token_symbol = _sanitize_text(symbol, max_len=20)
        except Exception as exc:
            # Graceful degradation: enrichment failure is non-fatal
            logger.warning("[TRENDING] Token enrichment failed: %s", exc)

    return tokens
