"""Tests for the concurrent aggregator."""

import re

import httpx

from rugcheck.config import Config
from rugcheck.fetchers.aggregator import Aggregator


MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
CONFIG = Config()

# --- Mock responses ---

RUGCHECK_RESP = {
    "token": {"mintAuthority": None, "freezeAuthority": None, "supply": 1000000, "decimals": 5},
    "tokenMeta": {"name": "Bonk", "symbol": "BONK", "mutable": False},
    "score": 250,
    "score_normalised": 25,
    "totalMarketLiquidity": 80000.0,
    "totalHolders": 5000,
    "risks": [],
    "topHolders": [{"owner": "a1", "pct": 5.0}],  # pct is already percentage
    "markets": [{"lp": {"lpCurrentSupply": 100, "lpTotalSupply": 200, "lpLockedPct": 0.99, "quoteUSD": 80000}}],
}

DEXSCREENER_RESP = [
    {
        "chainId": "solana",
        "baseToken": {"address": MINT, "name": "Bonk", "symbol": "BONK"},
        "quoteToken": {"address": "SOL", "name": "SOL", "symbol": "SOL"},
        "priceUsd": "0.000025",
        "liquidity": {"usd": 5000000},
        "volume": {"h24": 12000000},
        "txns": {"h24": {"buys": 15000, "sells": 12000}},
        "pairCreatedAt": 1700000000000,
    }
]

GOPLUS_RESP = {
    "code": 1,
    "message": "ok",
    "result": {
        MINT: {
            "metadata": {"name": "Bonk", "symbol": "BONK"},
            "holder_count": "5000",
            "mintable": {"status": "0"},
            "freezable": {"status": "0"},
            "closable": {"status": "0"},
            "metadata_mutable": {"status": "0"},
            "holders": [{"account": "a1", "percent": "0.08"}],
            "dex": [{"tvl": 60000, "burn_percent": 99}],
        }
    },
}


async def test_all_sources_succeed(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*rugcheck.*"), json=RUGCHECK_RESP)
    httpx_mock.add_response(url=re.compile(r".*dexscreener.*"), json=DEXSCREENER_RESP)
    httpx_mock.add_response(url=re.compile(r".*gopluslabs.*"), json=GOPLUS_RESP)

    async with httpx.AsyncClient() as client:
        agg = Aggregator(CONFIG, client=client)
        result = await agg.aggregate(MINT)

    assert len(result.sources_succeeded) == 3
    assert len(result.sources_failed) == 0
    assert result.token_name == "Bonk"
    assert result.price_usd == 0.000025
    assert result.rugcheck_score == 25


async def test_one_source_fails(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*rugcheck.*"), json=RUGCHECK_RESP)
    httpx_mock.add_response(url=re.compile(r".*dexscreener.*"), json=DEXSCREENER_RESP)
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"), url=re.compile(r".*gopluslabs.*"))

    async with httpx.AsyncClient() as client:
        agg = Aggregator(CONFIG, client=client)
        result = await agg.aggregate(MINT)

    assert len(result.sources_succeeded) == 2
    assert "GoPlus" in result.sources_failed
    assert result.token_name == "Bonk"


async def test_all_sources_fail(httpx_mock):
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"), url=re.compile(r".*rugcheck.*"))
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"), url=re.compile(r".*dexscreener.*"))
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"), url=re.compile(r".*gopluslabs.*"))

    async with httpx.AsyncClient() as client:
        agg = Aggregator(CONFIG, client=client)
        result = await agg.aggregate(MINT)

    assert len(result.sources_succeeded) == 0
    assert len(result.sources_failed) == 3
    assert result.token_name is None


async def test_priority_rugcheck_over_goplus(httpx_mock):
    """RugCheck data should take priority over GoPlus when both succeed."""
    rugcheck_data = dict(RUGCHECK_RESP)
    rugcheck_data["tokenMeta"] = {"name": "RugCheckName", "symbol": "RC"}

    goplus_data = dict(GOPLUS_RESP)
    goplus_data["result"] = {MINT: {**GOPLUS_RESP["result"][MINT], "metadata": {"name": "GoPlusName", "symbol": "GP"}}}

    httpx_mock.add_response(url=re.compile(r".*rugcheck.*"), json=rugcheck_data)
    httpx_mock.add_response(url=re.compile(r".*dexscreener.*"), json=DEXSCREENER_RESP)
    httpx_mock.add_response(url=re.compile(r".*gopluslabs.*"), json=goplus_data)

    async with httpx.AsyncClient() as client:
        agg = Aggregator(CONFIG, client=client)
        result = await agg.aggregate(MINT)

    assert result.token_name == "RugCheckName"
