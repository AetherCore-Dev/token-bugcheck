"""FastAPI application — the audit API server."""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

from rugcheck.cache import TTLCache
from rugcheck.config import Config, load_config
from rugcheck.engine.risk_engine import build_report
from rugcheck.fetchers.aggregator import Aggregator
from rugcheck.models import AuditReport

logger = logging.getLogger(__name__)

# Solana address: base58, 32-44 chars
SOLANA_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def create_app(config: Config | None = None, aggregator: Aggregator | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Service configuration. Loaded from env if not provided.
        aggregator: Optional pre-built aggregator (for testing). If None,
                    one is created during lifespan startup.
    """
    cfg = config or load_config()

    cache = TTLCache(ttl_seconds=cfg.cache_ttl_seconds, max_size=cfg.cache_max_size)
    # Store aggregator in a mutable container so lifespan and routes can share it
    state = {"aggregator": aggregator, "total_requests": 0}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if state["aggregator"] is None:
            client = httpx.AsyncClient()
            state["aggregator"] = Aggregator(cfg, client=client)
        logger.info("[SERVER] Audit service ready on %s:%d", cfg.host, cfg.port)
        yield
        if state["aggregator"] is not None:
            await state["aggregator"].close()

    app = FastAPI(
        title="Token RugCheck MCP",
        description="Solana token safety audit for AI agents — rug pull detection powered by x402 micropayments",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/audit/{mint_address}", response_model=AuditReport)
    async def audit(mint_address: str) -> AuditReport:
        state["total_requests"] += 1

        if not SOLANA_ADDR_RE.match(mint_address):
            raise HTTPException(status_code=400, detail="Invalid Solana address format")

        cached = cache.get(mint_address)
        if cached is not None:
            logger.info("[AUDIT] Cache HIT for %s", mint_address[:16])
            cached.metadata.cache_hit = True
            return cached

        agg = state["aggregator"]
        if agg is None:
            raise HTTPException(status_code=503, detail="Service not initialized")

        t0 = time.monotonic()
        data = await agg.aggregate(mint_address)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if not data.sources_succeeded:
            raise HTTPException(
                status_code=503,
                detail="All upstream data sources unavailable. Please try again later.",
            )

        report = build_report(mint_address, data, response_time_ms=elapsed_ms)
        logger.info(
            "[AUDIT] %s -> risk=%d (%s) in %dms [%s]",
            mint_address[:16],
            report.action.risk_score,
            report.action.risk_level.value,
            elapsed_ms,
            ",".join(data.sources_succeeded),
        )

        cache.set(mint_address, report)
        return report

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "token-rugcheck-mcp", "version": "0.1.0"}

    @app.get("/stats")
    async def stats():
        return {
            "total_requests": state["total_requests"],
            "cache": cache.stats,
        }

    return app
