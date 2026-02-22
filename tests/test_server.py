"""Tests for the FastAPI audit server."""

import httpx
import pytest

from rugcheck.config import Config
from rugcheck.models import AggregatedData
from rugcheck.server import create_app

MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
CONFIG = Config()


def _safe_data() -> AggregatedData:
    return AggregatedData(
        token_name="Bonk",
        token_symbol="BONK",
        is_mintable=False,
        is_freezable=False,
        is_closable=False,
        liquidity_usd=5_000_000.0,
        volume_24h_usd=12_000_000.0,
        lp_burned_pct=99.0,
        price_usd=0.000025,
        sources_succeeded=["RugCheck", "DexScreener", "GoPlus"],
    )


def _empty_data() -> AggregatedData:
    return AggregatedData(
        sources_succeeded=[],
        sources_failed=["RugCheck", "DexScreener", "GoPlus"],
    )


class FakeAggregator:
    """Test double that returns pre-set data."""

    def __init__(self, data: AggregatedData):
        self._data = data

    async def aggregate(self, mint_address: str) -> AggregatedData:
        return self._data

    async def close(self) -> None:
        pass


@pytest.fixture
def safe_app():
    return create_app(CONFIG, aggregator=FakeAggregator(_safe_data()))


@pytest.fixture
def failing_app():
    return create_app(CONFIG, aggregator=FakeAggregator(_empty_data()))


async def test_audit_success(safe_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=safe_app), base_url="http://test") as client:
        resp = await client.get(f"/audit/{MINT}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["contract_address"] == MINT
    assert data["chain"] == "solana"
    assert "action" in data
    assert "analysis" in data
    assert "evidence" in data
    assert "metadata" in data
    assert data["action"]["risk_level"] in ["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert data["action"]["is_safe"] is True
    assert data["metadata"]["cache_hit"] is False
    assert data["evidence"]["token_name"] == "Bonk"


async def test_audit_cache_hit(safe_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=safe_app), base_url="http://test") as client:
        resp1 = await client.get(f"/audit/{MINT}")
        assert resp1.status_code == 200
        assert resp1.json()["metadata"]["cache_hit"] is False

        resp2 = await client.get(f"/audit/{MINT}")
        assert resp2.status_code == 200
        assert resp2.json()["metadata"]["cache_hit"] is True


async def test_audit_invalid_address(safe_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=safe_app), base_url="http://test") as client:
        resp = await client.get("/audit/not-a-valid-address!!!")
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


async def test_audit_all_sources_down(failing_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=failing_app), base_url="http://test") as client:
        resp = await client.get(f"/audit/{MINT}")
    assert resp.status_code == 503


async def test_health(safe_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=safe_app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_stats(safe_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=safe_app), base_url="http://test") as client:
        # Make one request first
        await client.get(f"/audit/{MINT}")
        resp = await client.get("/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_requests"] == 1
    assert "cache" in stats
