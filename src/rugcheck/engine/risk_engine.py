"""Risk scoring engine — pure deterministic rules, zero LLM.

Rule design principles (validated against real Solana ecosystem 2026-02):
  - LP "locked" (RugCheck) and LP "burned" (GoPlus) are tracked separately.
    Locked LP may unlock later; burned LP is permanent.
  - Solana's "closable" refers to token account rent reclamation, NOT token
    destruction. It is demoted from HIGH to LOW.
  - "Metadata mutable" is common for legitimate Solana tokens and demoted to LOW.
  - A combined "LP unprotected" rule checks if LP is neither burned NOR locked.
  - Buy/sell ratio from DexScreener is used to detect active dumps.
  - **Liquidity exemption**: tokens with >= $1M liquidity are exempt from
    LP-protection and holder-concentration rules. High liquidity is itself
    a strong anti-rug signal for established tokens (BONK, WIF, JUP, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from rugcheck.models import (
    ActionLayer,
    AggregatedData,
    AnalysisLayer,
    AuditReport,
    AuditMetadata,
    EvidenceLayer,
    RiskFlag,
    RiskLevel,
)


@dataclass
class Rule:
    """A single risk assessment rule."""

    name: str
    level: str  # CRITICAL, HIGH, MEDIUM, LOW
    score: int  # points added to risk_score (0-100)
    flag_message: str
    evaluate: Callable[[AggregatedData], bool | None]  # True = risk triggered, None = data unavailable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tokens with liquidity >= this threshold are exempt from LP-protection
# and holder-concentration rules. High liquidity is itself anti-rug.
LIQUIDITY_EXEMPTION_USD = 1_000_000


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _pair_age_hours(data: AggregatedData) -> float | None:
    if data.pair_created_at is None:
        return None
    now = datetime.now(timezone.utc)
    ts = data.pair_created_at.replace(tzinfo=timezone.utc) if data.pair_created_at.tzinfo is None else data.pair_created_at
    return (now - ts).total_seconds() / 3600


def _is_high_liquidity(data: AggregatedData) -> bool:
    """Check if the token has enough liquidity to qualify for exemptions."""
    return data.liquidity_usd is not None and data.liquidity_usd >= LIQUIDITY_EXEMPTION_USD


def _lp_unprotected(data: AggregatedData) -> bool | None:
    """Returns True if LP is neither sufficiently burned NOR sufficiently locked.

    Exempt if liquidity >= $1M — established high-liquidity pools are
    inherently resistant to rug pulls even without LP burn/lock.
    """
    if _is_high_liquidity(data):
        return False
    burned = data.lp_burned_pct
    locked = data.lp_locked_pct
    # If both are unknown, skip the rule
    if burned is None and locked is None:
        return None
    # Safe if EITHER burned >= 50% OR locked >= 50%
    if burned is not None and burned >= 50:
        return False
    if locked is not None and locked >= 50:
        return False
    # If we have data and neither is sufficient, flag it
    return True


def _top10_concentrated(data: AggregatedData) -> bool | None:
    """Top 10 holders > 80% is risky, but exempt for high-liquidity tokens."""
    if data.top10_holder_pct is None:
        return None
    if _is_high_liquidity(data):
        return False
    return data.top10_holder_pct > 80


def _sell_pressure(data: AggregatedData) -> bool | None:
    """Detects heavy sell-side pressure: sells > 3x buys in 24h."""
    if data.buy_count_24h is None or data.sell_count_24h is None:
        return None
    if data.buy_count_24h == 0:
        return data.sell_count_24h > 0
    return data.sell_count_24h > data.buy_count_24h * 3


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

RULES: list[Rule] = [
    # === Critical (any single one = extreme danger) ===
    Rule(
        name="mintable",
        level="CRITICAL",
        score=40,
        flag_message="合约拥有增发权限 (Mintable)，庄家可无限增发砸盘。",
        evaluate=lambda d: d.is_mintable,
    ),
    Rule(
        name="lp_unprotected",
        level="CRITICAL",
        score=35,
        flag_message="流动性池既未销毁也未充分锁仓 (LP Unprotected)，庄家可撤资 (Rug Pull)。",
        evaluate=_lp_unprotected,
    ),
    Rule(
        name="freezable",
        level="CRITICAL",
        score=30,
        flag_message="合约拥有冻结权限 (Freezable)，庄家可冻结任何持币地址。",
        evaluate=lambda d: d.is_freezable,
    ),
    # === High ===
    Rule(
        name="top10_concentrated",
        level="HIGH",
        score=25,
        flag_message="前 10 大地址持仓超 80%，筹码过度集中。",
        evaluate=_top10_concentrated,
    ),
    Rule(
        name="low_liquidity",
        level="HIGH",
        score=20,
        flag_message="流动性极低 (< $10,000)，极易被控盘或砸盘归零。",
        evaluate=lambda d: d.liquidity_usd < 10_000 if d.liquidity_usd is not None else None,
    ),
    Rule(
        name="sell_pressure",
        level="HIGH",
        score=15,
        flag_message="24h 卖单数量远超买单 (>3x)，疑似抛售砸盘。",
        evaluate=_sell_pressure,
    ),
    # === Medium ===
    Rule(
        name="very_new_pair",
        level="MEDIUM",
        score=10,
        flag_message="交易对创建不到 24 小时，极早期代币风险高。",
        evaluate=lambda d: _pair_age_hours(d) < 24 if _pair_age_hours(d) is not None else None,
    ),
    Rule(
        name="low_volume",
        level="MEDIUM",
        score=5,
        flag_message="24h 交易量极低 (< $1,000)，流动性不足。",
        evaluate=lambda d: d.volume_24h_usd < 1_000 if d.volume_24h_usd is not None else None,
    ),
    # === Low (informational, not alarming) ===
    Rule(
        name="metadata_mutable",
        level="LOW",
        score=3,
        flag_message="代币元数据可被修改 (Metadata Mutable)，在 Solana 生态中较常见。",
        evaluate=lambda d: d.is_metadata_mutable,
    ),
    Rule(
        name="closable",
        level="LOW",
        score=3,
        flag_message="合约拥有关闭权限 (Closable)，通常用于 Solana 租金回收。",
        evaluate=lambda d: d.is_closable,
    ),
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def evaluate(data: AggregatedData) -> tuple[int, list[RiskFlag], list[RiskFlag]]:
    """Run all rules and return (risk_score, red_flags, green_flags)."""
    risk_score = 0
    red_flags: list[RiskFlag] = []
    green_flags: list[RiskFlag] = []

    for rule in RULES:
        try:
            triggered = rule.evaluate(data)
        except Exception:  # noqa: BLE001
            continue  # data unavailable → skip rule

        if triggered is True:
            risk_score += rule.score
            red_flags.append(RiskFlag(level=rule.level, message=rule.flag_message))
        elif triggered is False:
            # Explicitly safe on this dimension — only show green for critical rules
            if rule.level == "CRITICAL":
                green_flags.append(RiskFlag(level="SAFE", message=_invert_message(rule.name)))

    risk_score = min(risk_score, 100)
    return risk_score, red_flags, green_flags


def build_report(
    mint_address: str,
    data: AggregatedData,
    response_time_ms: int = 0,
    cache_hit: bool = False,
) -> AuditReport:
    """Build a complete three-layer audit report."""
    risk_score, red_flags, green_flags = evaluate(data)

    if risk_score >= 70:
        risk_level = RiskLevel.CRITICAL
    elif risk_score >= 40:
        risk_level = RiskLevel.HIGH
    elif risk_score >= 20:
        risk_level = RiskLevel.MEDIUM
    elif risk_score >= 5:
        risk_level = RiskLevel.LOW
    else:
        risk_level = RiskLevel.SAFE

    is_safe = risk_score < 40

    if risk_level == RiskLevel.CRITICAL:
        summary = "该代币存在多项致命风险，极大概率为 Rug Pull 骗局，强烈建议回避。"
    elif risk_level == RiskLevel.HIGH:
        summary = "该代币存在显著风险因素，请谨慎评估后再决定是否交易。"
    elif risk_level == RiskLevel.MEDIUM:
        summary = "该代币存在中等风险，建议仔细核查后再做决策。"
    elif risk_level == RiskLevel.LOW:
        summary = "该代币风险较低，但仍需注意市场波动风险。"
    else:
        summary = "未检测到明显风险信号，但请始终做好自己的研究 (DYOR)。"

    if len(data.sources_failed) == 0:
        completeness = "full"
    elif len(data.sources_succeeded) >= 2:
        completeness = "partial"
    else:
        completeness = "minimal"

    return AuditReport(
        contract_address=mint_address,
        chain="solana",
        action=ActionLayer(is_safe=is_safe, risk_level=risk_level, risk_score=risk_score),
        analysis=AnalysisLayer(summary=summary, red_flags=red_flags, green_flags=green_flags),
        evidence=EvidenceLayer(
            token_name=data.token_name,
            token_symbol=data.token_symbol,
            price_usd=data.price_usd,
            liquidity_usd=data.liquidity_usd,
            volume_24h_usd=data.volume_24h_usd,
            top_10_holders_pct=data.top10_holder_pct,
            is_mintable=data.is_mintable,
            is_freezable=data.is_freezable,
            is_closable=data.is_closable,
            lp_burned_pct=data.lp_burned_pct,
            lp_locked_pct=data.lp_locked_pct,
            pair_created_at=data.pair_created_at.isoformat() if data.pair_created_at else None,
            holder_count=data.holder_count,
            rugcheck_score=data.rugcheck_score,
        ),
        metadata=AuditMetadata(
            data_sources=data.sources_succeeded,
            data_completeness=completeness,
            cache_hit=cache_hit,
            response_time_ms=response_time_ms,
        ),
    )


def _invert_message(rule_name: str) -> str:
    """Generate a positive message for rules that passed."""
    messages = {
        "mintable": "增发权限已放弃 (Mint Renounced)。",
        "freezable": "无冻结权限 (Not Freezable)。",
        "lp_unprotected": "流动性池已充分保护 (LP Burned 或 Locked)。",
    }
    return messages.get(rule_name, f"{rule_name}: OK")
