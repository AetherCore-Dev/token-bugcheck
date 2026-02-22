"""Tests for TTL cache."""

import time

from rugcheck.cache import TTLCache
from rugcheck.models import (
    ActionLayer,
    AnalysisLayer,
    AuditMetadata,
    AuditReport,
    EvidenceLayer,
    RiskLevel,
)


def _make_report(mint: str = "TESTMINT") -> AuditReport:
    return AuditReport(
        contract_address=mint,
        action=ActionLayer(is_safe=True, risk_level=RiskLevel.SAFE, risk_score=0),
        analysis=AnalysisLayer(summary="Safe"),
        evidence=EvidenceLayer(),
        metadata=AuditMetadata(data_sources=["RugCheck"]),
    )


def test_set_and_get():
    cache = TTLCache(ttl_seconds=60)
    report = _make_report()
    cache.set("key1", report)
    assert cache.get("key1") is not None
    assert cache.get("key1").contract_address == "TESTMINT"


def test_miss_returns_none():
    cache = TTLCache()
    assert cache.get("nonexistent") is None


def test_ttl_expiry():
    cache = TTLCache(ttl_seconds=0)  # expires immediately
    cache.set("key1", _make_report())
    time.sleep(0.01)
    assert cache.get("key1") is None


def test_max_size_eviction():
    cache = TTLCache(ttl_seconds=60, max_size=2)
    cache.set("a", _make_report("A"))
    cache.set("b", _make_report("B"))
    cache.set("c", _make_report("C"))

    # "a" should be evicted
    assert cache.get("a") is None
    assert cache.get("b") is not None
    assert cache.get("c") is not None


def test_stats():
    cache = TTLCache(ttl_seconds=60)
    cache.set("k", _make_report())

    cache.get("k")       # hit
    cache.get("missing")  # miss

    s = cache.stats
    assert s["hits"] == 1
    assert s["misses"] == 1
    assert s["hit_rate"] == 50.0
    assert s["size"] == 1
