"""Base class for upstream data source fetchers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from rugcheck.models import FetcherResult


class BaseFetcher(ABC):
    """Abstract fetcher — one per upstream API."""

    source_name: str = "unknown"

    def __init__(self, client: httpx.AsyncClient, timeout: float = 5.0):
        self.client = client
        self.timeout = timeout

    async def fetch(self, mint_address: str) -> FetcherResult:
        """Fetch data with unified error handling."""
        try:
            return await self._do_fetch(mint_address)
        except httpx.TimeoutException:
            return FetcherResult(source=self.source_name, success=False, error="timeout")
        except httpx.HTTPStatusError as exc:
            return FetcherResult(
                source=self.source_name,
                success=False,
                error=f"http_{exc.response.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            return FetcherResult(source=self.source_name, success=False, error=str(exc))

    @abstractmethod
    async def _do_fetch(self, mint_address: str) -> FetcherResult:
        """Subclass implements the actual HTTP call + parsing."""
        ...
