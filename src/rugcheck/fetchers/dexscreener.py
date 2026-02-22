"""DexScreener API fetcher — liquidity, price, and volume data."""

from __future__ import annotations

from datetime import datetime, timezone

from rugcheck.fetchers.base import BaseFetcher
from rugcheck.models import FetcherResult

DEXSCREENER_URL = "https://api.dexscreener.com/tokens/v1/solana"


class DexScreenerFetcher(BaseFetcher):
    source_name = "DexScreener"

    async def _do_fetch(self, mint_address: str) -> FetcherResult:
        resp = await self.client.get(
            f"{DEXSCREENER_URL}/{mint_address}",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        pairs = resp.json()

        if not isinstance(pairs, list) or not pairs:
            return FetcherResult(source=self.source_name, success=False, error="no_pairs")

        parsed = _parse_dexscreener(pairs)
        return FetcherResult(source=self.source_name, success=True, data=parsed)


def _parse_dexscreener(pairs: list[dict]) -> dict:
    """Extract data from the highest-liquidity pair."""
    best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))

    data: dict = {}
    base = best.get("baseToken") or {}
    data["token_name"] = base.get("name")
    data["token_symbol"] = base.get("symbol")

    data["price_usd"] = _safe_float(best.get("priceUsd"))

    liq = best.get("liquidity") or {}
    data["liquidity_usd"] = _safe_float(liq.get("usd"))

    vol = best.get("volume") or {}
    data["volume_24h_usd"] = _safe_float(vol.get("h24"))

    txns = best.get("txns") or {}
    h24 = txns.get("h24") or {}
    data["buy_count_24h"] = h24.get("buys")
    data["sell_count_24h"] = h24.get("sells")

    created = best.get("pairCreatedAt")
    if created:
        try:
            data["pair_created_at"] = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            pass

    return data


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
