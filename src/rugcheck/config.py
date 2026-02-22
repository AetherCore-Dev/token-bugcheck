"""Configuration management — loads from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Immutable service configuration."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Cache
    cache_ttl_seconds: int = 30
    cache_max_size: int = 10_000

    # Upstream timeouts
    goplus_timeout: float = 5.0
    rugcheck_timeout: float = 5.0
    dexscreener_timeout: float = 3.0

    # GoPlus auth (optional)
    goplus_app_key: str = ""
    goplus_app_secret: str = ""

    # AgentPay
    agentpay_price: str = "0.05"
    agentpay_address: str = "fisJvtob3HfaTWoCynHLp9McFoFZ2gL3VEiA4p4QnNm"


def load_config() -> Config:
    """Build Config from environment variables with sensible defaults."""
    return Config(
        host=os.getenv("RUGCHECK_HOST", "0.0.0.0"),
        port=int(os.getenv("RUGCHECK_PORT", "8000")),
        log_level=os.getenv("RUGCHECK_LOG_LEVEL", "info"),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "30")),
        cache_max_size=int(os.getenv("CACHE_MAX_SIZE", "10000")),
        goplus_timeout=float(os.getenv("GOPLUS_TIMEOUT_SECONDS", "5")),
        rugcheck_timeout=float(os.getenv("RUGCHECK_API_TIMEOUT_SECONDS", "5")),
        dexscreener_timeout=float(os.getenv("DEXSCREENER_TIMEOUT_SECONDS", "3")),
        goplus_app_key=os.getenv("GOPLUS_APP_KEY", ""),
        goplus_app_secret=os.getenv("GOPLUS_APP_SECRET", ""),
        agentpay_price=os.getenv("AGENTPAY_PRICE", "0.05"),
        agentpay_address=os.getenv("AGENTPAY_ADDRESS", "fisJvtob3HfaTWoCynHLp9McFoFZ2gL3VEiA4p4QnNm"),
    )
