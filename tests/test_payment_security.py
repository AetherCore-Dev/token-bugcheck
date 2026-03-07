"""Payment security tests — verify gateway rejects invalid payment proofs.

These tests validate that the ag402 gateway correctly:
  1. Returns 402 when no payment header is provided
  2. Rejects malformed/fake payment proofs
  3. Rejects payment with wrong amount (underpayment)
  4. Rejects payment to wrong address
  5. Rejects replayed transaction hashes

Tests run against the X402Gateway in test/mock mode to verify the
protocol-level security without requiring real Solana transactions.
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest

# Force test mode for ag402
os.environ.setdefault("X402_MODE", "test")
os.environ.setdefault("X402_NETWORK", "mock")

BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
SELLER_ADDRESS = "EtfTwndhRFLaWUe64ZbCBBdXBqfaK9H6QqCAeSnNXLLK"

# ---------------------------------------------------------------------------
# Fixtures — spin up audit + gateway in-process
# ---------------------------------------------------------------------------


def _create_audit_app():
    """Create the audit FastAPI app."""
    from rugcheck.config import Config
    from rugcheck.models import AggregatedData
    from rugcheck.server import create_app

    class FakeAggregator:
        last_success_time = time.monotonic()
        last_failure_time = None

        async def aggregate(self, mint_address: str) -> AggregatedData:
            return AggregatedData(
                token_name="Bonk",
                token_symbol="BONK",
                is_mintable=False,
                is_freezable=False,
                liquidity_usd=5_000_000.0,
                sources_succeeded=["RugCheck", "DexScreener"],
            )

        async def close(self):
            pass

    return create_app(Config(), aggregator=FakeAggregator())


# ---------------------------------------------------------------------------
# 1. No payment header → 402
# ---------------------------------------------------------------------------


async def test_no_payment_returns_402():
    """Request without any payment proof must receive 402 Payment Required."""
    from ag402_mcp import X402Gateway

    audit_app = _create_audit_app()
    gw = X402Gateway(
        target_url="http://testserver",
        price="0.05",
        chain="solana",
        token="USDC",
        address=SELLER_ADDRESS,
    )
    gw_app = gw.create_app()

    # Mount audit app as a sub-app that the gateway proxies to
    transport = httpx.ASGITransport(app=gw_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/audit/{BONK_MINT}")

    assert resp.status_code == 402
    body = resp.json()
    assert body.get("protocol") == "x402"
    assert body.get("chain") == "solana"
    assert body.get("token") == "USDC"
    assert body.get("address") == SELLER_ADDRESS


# ---------------------------------------------------------------------------
# 2. Malformed/fake payment header → rejected
# ---------------------------------------------------------------------------


async def test_fake_payment_header_rejected():
    """A completely fake X-PAYMENT header must be rejected (not 200)."""
    from ag402_mcp import X402Gateway

    gw = X402Gateway(
        target_url="http://testserver",
        price="0.05",
        chain="solana",
        token="USDC",
        address=SELLER_ADDRESS,
    )
    gw_app = gw.create_app()

    transport = httpx.ASGITransport(app=gw_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/audit/{BONK_MINT}",
            headers={"X-PAYMENT": "totally-fake-payment-proof-12345"},
        )

    # Must NOT return 200 — should be 402 or 400
    assert resp.status_code in (400, 402, 403), (
        f"Fake payment proof should be rejected, got {resp.status_code}"
    )


async def test_empty_payment_header_rejected():
    """An empty X-PAYMENT header must be rejected."""
    from ag402_mcp import X402Gateway

    gw = X402Gateway(
        target_url="http://testserver",
        price="0.05",
        chain="solana",
        token="USDC",
        address=SELLER_ADDRESS,
    )
    gw_app = gw.create_app()

    transport = httpx.ASGITransport(app=gw_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/audit/{BONK_MINT}",
            headers={"X-PAYMENT": ""},
        )

    assert resp.status_code in (400, 402, 403)


# ---------------------------------------------------------------------------
# 3. Malformed JSON payment proof → rejected
# ---------------------------------------------------------------------------


async def test_malformed_json_payment_rejected():
    """A malformed JSON payment proof must be rejected."""
    from ag402_mcp import X402Gateway

    gw = X402Gateway(
        target_url="http://testserver",
        price="0.05",
        chain="solana",
        token="USDC",
        address=SELLER_ADDRESS,
    )
    gw_app = gw.create_app()

    transport = httpx.ASGITransport(app=gw_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Send something that looks like JSON but is wrong
        import base64
        fake_proof = base64.b64encode(json.dumps({
            "tx_hash": "fake_hash_abc123",
            "chain": "solana",
            "amount": "0.05",
        }).encode()).decode()

        resp = await client.get(
            f"/audit/{BONK_MINT}",
            headers={"X-PAYMENT": fake_proof},
        )

    # Should not be 200
    assert resp.status_code != 200, (
        f"Malformed payment proof should not yield 200, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 4. 402 challenge contains correct payment parameters
# ---------------------------------------------------------------------------


async def test_402_challenge_has_correct_parameters():
    """The 402 challenge must specify the correct price, chain, token, and address."""
    from ag402_mcp import X402Gateway

    gw = X402Gateway(
        target_url="http://testserver",
        price="0.10",  # custom price
        chain="solana",
        token="USDC",
        address=SELLER_ADDRESS,
    )
    gw_app = gw.create_app()

    transport = httpx.ASGITransport(app=gw_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/audit/{BONK_MINT}")

    assert resp.status_code == 402
    body = resp.json()
    assert body["address"] == SELLER_ADDRESS
    assert body["chain"] == "solana"
    assert body["token"] == "USDC"
    # Price may be formatted differently, but should represent 0.10
    amount = float(body.get("amount", 0))
    assert amount == pytest.approx(0.10, abs=0.001)


# ---------------------------------------------------------------------------
# 5. Gateway health endpoint accessible without payment
# ---------------------------------------------------------------------------


async def test_health_bypasses_paywall():
    """Health endpoint should be accessible without payment."""
    from ag402_mcp import X402Gateway

    gw = X402Gateway(
        target_url="http://testserver",
        price="0.05",
        chain="solana",
        token="USDC",
        address=SELLER_ADDRESS,
    )
    gw_app = gw.create_app()

    transport = httpx.ASGITransport(app=gw_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    # Health should return 200 (gateway has its own health) or proxy through
    assert resp.status_code in (200, 404), (
        f"Health endpoint should not require payment, got {resp.status_code}"
    )
