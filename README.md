# Token RugCheck MCP

Solana token safety audit for AI Agents — detect Rug Pulls before your agent buys. Powered by x402 micropayments.

> **Currently runs on Solana Devnet by default. Zero real funds required to test.**

## What It Does

Input a Solana token contract address, get a three-layer safety audit report:

- **Action Layer** — machine-readable verdict (`is_safe`, `risk_score`, `risk_level`)
- **Analysis Layer** — LLM-friendly risk summary with red/green flags
- **Evidence Layer** — raw data for human cross-verification

Data sources: RugCheck.xyz + DexScreener + GoPlus Security (concurrent fetch, graceful degradation).

## Quick Start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Run server
python -m rugcheck.main
# Server starts on http://localhost:8000

# 3. Query a token
curl http://localhost:8000/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/audit/{mint_address}` | Full safety audit report |
| GET | `/health` | Health check |
| GET | `/stats` | Service statistics + cache hit rate |

## Response Example

```json
{
  "contract_address": "7X...",
  "chain": "solana",
  "action": {
    "is_safe": false,
    "risk_level": "CRITICAL",
    "risk_score": 85
  },
  "analysis": {
    "summary": "该代币存在多项致命风险...",
    "red_flags": [
      {"level": "CRITICAL", "message": "合约拥有增发权限 (Mintable)..."}
    ],
    "green_flags": []
  },
  "evidence": {
    "price_usd": 0.00012,
    "liquidity_usd": 8500.0,
    "is_mintable": true
  },
  "metadata": {
    "data_sources": ["RugCheck", "GoPlus Security", "DexScreener"],
    "cache_hit": false,
    "response_time_ms": 1200
  }
}
```

## With AgentPay (x402 Micropayments)

Deploy behind an AgentPay gateway to charge per audit:

> **0.05 USDC per audit.** Save your AI agent from buying a $500 Rug Pull token for the price of a gumball.

```bash
# Start audit server
python -m rugcheck.main &

# Start x402 payment gateway (Devnet — no real funds needed)
agentpay serve \
  --target http://localhost:8000 \
  --price 0.05 \
  --address fisJvtob3HfaTWoCynHLp9McFoFZ2gL3VEiA4p4QnNm \
  --port 8001
```

### Buyer Integration (3 lines of Python)

```python
import httpx
import agentpay_core

agentpay_core.enable()  # Auto-pays on 402

async with httpx.AsyncClient() as client:
    resp = await client.get("https://your-server:8001/audit/{mint}")
    report = resp.json()

    if not report["action"]["is_safe"]:
        print("DANGER: Do not buy this token!")
```

## Docker Deployment

```bash
cp .env.example .env
# Edit .env with your settings
docker compose up -d
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # Run tests
ruff check src/ tests/    # Lint
python examples/demo_agent.py  # E2E demo
```

## Architecture

```
src/rugcheck/
├── config.py              # Environment-based configuration
├── models.py              # Pydantic models (report schema)
├── cache.py               # In-memory TTL cache (LRU eviction)
├── server.py              # FastAPI application
├── main.py                # Entry point
├── fetchers/
│   ├── base.py            # BaseFetcher ABC
│   ├── goplus.py          # GoPlus Security API
│   ├── rugcheck.py        # RugCheck.xyz API
│   ├── dexscreener.py     # DexScreener API
│   └── aggregator.py      # Concurrent fetch + merge
└── engine/
    └── risk_engine.py     # Deterministic rule-based scoring
```

**Cache policy:** TTL is strictly 30 seconds. For on-chain security data, freshness beats speed — a 5-minute-old "SAFE" verdict is worthless if the LP was pulled 4 minutes ago.

**Liquidity exemption:** Tokens with >= $1M liquidity are auto-exempt from LP-protection and holder-concentration rules. High liquidity is itself anti-rug — this prevents false positives on established tokens (BONK, WIF, JUP) while keeping strict rules for new/small tokens.

## License

MIT
