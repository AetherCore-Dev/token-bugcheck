"""
E2E Demo: AI Agent queries token safety audit via the RugCheck MCP service.

Demonstrates:
  1. Start the audit server locally
  2. Query a well-known safe token (BONK)
  3. Query a suspicious/unknown token
  4. Show the three-layer audit report
  5. Demonstrate cache hit behavior

Usage:
    python examples/demo_agent.py

    Requires internet access to reach GoPlus, RugCheck, and DexScreener APIs.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx
import uvicorn

from rugcheck.config import Config
from rugcheck.server import create_app

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT = 18000
# BONK — well-known Solana memecoin (should be relatively safe)
BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def log(tag: str, msg: str) -> None:
    print(f"  [{tag}] {msg}")


# ---------------------------------------------------------------------------
# Background server
# ---------------------------------------------------------------------------

class BackgroundServer:
    def __init__(self, app, port: int):
        self.app = app
        self.port = port
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="error")
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None
        self._task = asyncio.create_task(self._server.serve())
        for _ in range(50):
            await asyncio.sleep(0.1)
            if self._server.started:
                break

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def main() -> None:
    print()
    print("=" * 64)
    print("  Token RugCheck MCP — End-to-End Demo")
    print("=" * 64)
    print()

    # 1. Start server
    log("BOOT", f"Starting audit server on port {PORT}...")
    cfg = Config(port=PORT)
    app = create_app(config=cfg)
    server = BackgroundServer(app, PORT)
    await server.start()
    log("BOOT", "Audit server ready.")
    print()

    base_url = f"http://127.0.0.1:{PORT}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 2. Health check
            log("HEALTH", f"GET {base_url}/health")
            resp = await client.get(f"{base_url}/health")
            log("HEALTH", f"Status: {resp.status_code} — {resp.json()}")
            print()

            # 3. Audit BONK (known safe token)
            print("-" * 64)
            log("AUDIT", f"Querying token: BONK ({BONK_MINT[:16]}...)")
            log("AUDIT", f"GET {base_url}/audit/{BONK_MINT}")
            print("-" * 64)

            t0 = time.monotonic()
            resp = await client.get(f"{base_url}/audit/{BONK_MINT}")
            elapsed = time.monotonic() - t0

            if resp.status_code == 200:
                report = resp.json()
                action = report["action"]
                analysis = report["analysis"]
                evidence = report["evidence"]
                meta = report["metadata"]

                print()
                log("RESULT", f"Risk Score: {action['risk_score']}/100")
                log("RESULT", f"Risk Level: {action['risk_level']}")
                log("RESULT", f"Safe to Buy: {action['is_safe']}")
                print()
                log("ANALYSIS", analysis["summary"])
                if analysis["red_flags"]:
                    for flag in analysis["red_flags"]:
                        log("RED FLAG", f"[{flag['level']}] {flag['message']}")
                if analysis["green_flags"]:
                    for flag in analysis["green_flags"]:
                        log("GREEN", flag["message"])
                print()
                log("EVIDENCE", f"Price: ${evidence.get('price_usd', 'N/A')}")
                log("EVIDENCE", f"Liquidity: ${evidence.get('liquidity_usd', 'N/A')}")
                log("EVIDENCE", f"24h Volume: ${evidence.get('volume_24h_usd', 'N/A')}")
                log("EVIDENCE", f"Holders: {evidence.get('holder_count', 'N/A')}")
                print()
                log("META", f"Sources: {', '.join(meta['data_sources'])}")
                log("META", f"Completeness: {meta['data_completeness']}")
                log("META", f"Response Time: {meta['response_time_ms']}ms (total: {elapsed:.1f}s)")
                log("META", f"Cache Hit: {meta['cache_hit']}")
            else:
                log("ERROR", f"Status {resp.status_code}: {resp.text}")

            # 4. Cache hit demo
            print()
            print("-" * 64)
            log("CACHE", "Querying BONK again (should be cached)...")
            print("-" * 64)

            t0 = time.monotonic()
            resp2 = await client.get(f"{base_url}/audit/{BONK_MINT}")
            elapsed2 = time.monotonic() - t0

            if resp2.status_code == 200:
                report2 = resp2.json()
                log("CACHE", f"Cache Hit: {report2['metadata']['cache_hit']}")
                log("CACHE", f"Response Time: {elapsed2*1000:.0f}ms (vs {elapsed*1000:.0f}ms first time)")

            # 5. Invalid address test
            print()
            print("-" * 64)
            log("INVALID", "Testing invalid address handling...")
            print("-" * 64)
            resp3 = await client.get(f"{base_url}/audit/this-is-not-valid")
            log("INVALID", f"Status: {resp3.status_code} — {resp3.json()['detail']}")

            # 6. Stats
            print()
            print("-" * 64)
            log("STATS", f"GET {base_url}/stats")
            print("-" * 64)
            resp4 = await client.get(f"{base_url}/stats")
            log("STATS", json.dumps(resp4.json(), indent=2))

    finally:
        await server.stop()

    print()
    print("=" * 64)
    log("DONE", "Demo complete. Token RugCheck MCP is working.")
    print("=" * 64)
    print()


if __name__ == "__main__":
    asyncio.run(main())
