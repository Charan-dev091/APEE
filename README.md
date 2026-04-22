# APEE — Autonomous Personal Economy Engine

> A **domain-agnostic multi-agent decision framework** for autonomous financial decision-making.

Trading and e-commerce are included as **two proof-of-concept implementations** that demonstrate the framework operating across entirely different financial domains — using the same core pipeline, unchanged.

---

## The Framework Idea

Most AI trading tools are single-domain, hard-coded systems.  
**APEE separates the decision logic from the data domain.**

```
┌─────────────────────────────────────────────────────────────────┐
│                    APEE CORE FRAMEWORK                          │
│                                                                 │
│   Consensus Gate  ·  Confidence Scoring  ·  Security Layer      │
│   AsyncMandateManager  ·  WebSocket  ·  RAG  ·  Dashboard       │
└───────────────────────────┬─────────────────────────────────────┘
                            │  domain plugins
          ┌─────────────────┼──────────────────┐
          │                 │                  │
   TRADING POC       E-COMMERCE POC       YOUR DOMAIN
   (included)        (included)           (plug in)
```

A new financial domain requires implementing only:
- A **Scout plugin** (data source)
- A **Quant agent** (fast signal)
- A **Visionary agent** (structural analysis)

The Consensus Gate, security layer, mandate flow, confidence scoring, dashboard, and WebSocket all work immediately — no changes to the core.

---

## How the Core Works

Every domain goes through the same 8-stage pipeline:

```
Scout → Quant → Visionary → Sentiment → Consensus Gate → Auditor → Biometric Passkey → Paymaster
```

### Stage 1 — Scout (Data Ingestion)
Fetches raw data via a plugin registry. Adding a new source = one `register_plugin()` call.

| Plugin | Asset class | Source |
|--------|-------------|--------|
| `yfinance` | US Stocks, Crypto | Yahoo Finance |
| `hyperliquid` | Crypto Perps | Hyperliquid SDK |
| `bestbuy` | Consumer Electronics | Best Buy API |
| `walmart` | Consumer Products | Walmart API |
| `coingecko` | Crypto | CoinGecko |

### Stage 2 — Quant (Fast Signal, < 50ms)
Computes a directional signal from raw OHLCV or price data.  
For trading: RSI, MACD, EMA, Bollinger Bands, ATR, OBV, VWAP, ADX, Stochastic RSI.  
Optionally backed by a LightGBM model (27-feature vector, trained offline).

### Stage 3 — Visionary (Structural Analysis, LLM-backed)
Identifies the structural backdrop — regime, key levels, multi-timeframe context.  
Signal cached for 24 hours (slow-moving view vs. fast Quant signal). Uses Groq/Llama or Anthropic Claude.

### Stage 4 — Sentiment (Soft Signal)
12-cycle cache. Provides a sentiment score that adds a ±5% confidence boost to the gate.

### Stage 5 — Consensus Gate ⭐
The core innovation. Both quantitative and qualitative agents must agree before EXECUTE is issued.

**7-step sequential algorithm:**

| Step | Check | Fail → |
|------|-------|--------|
| 1 | Either agent is `neutral` | HOLD |
| 2 | Quant confidence < τ_quant | HOLD |
| 3 | Visionary confidence < τ_visionary | HOLD |
| 4 | Hard divergence ≥ δ_hard | HOLD |
| 5 | Direction disagreement | REVIEW |
| 6 | Soft divergence ≥ δ_divergence | REVIEW |
| 7 | Combined confidence < τ_combined | HOLD |
| ✓ | All passed | **EXECUTE** |

Combined confidence: `0.45 × quant + 0.55 × visionary` (+ sentiment boost up to 0.95 cap).  
All thresholds configurable via `.env`.

### Stage 6 — Auditor (Deterministic Risk)
Pure rule-based. No ML. Enforces: min balance reserve, max positions (5), max position size (20%), min order ($11), max total exposure (60%).

### Stage 7 — Biometric Passkey (6-Condition Valid(M))
Every EXECUTE clears six independent conditions before a trade is placed:

| # | Condition | Mechanism |
|---|-----------|-----------|
| 1 | Challenge binding | SHA-256 of mandate fields |
| 2 | WebAuthn UV required | `user_verification = "required"` |
| 3 | TEE attestation | SGX mrenclave check |
| 4 | Oracle consensus | Dual yfinance samples averaged |
| 5 | Atomic daily quota | Thread-safe spending cap |
| 6 | Revocation check | In-memory revocation registry |

Mandate approval is **non-blocking** via `asyncio.Future` — the event loop never stalls regardless of how long the user takes to approve.

### Stage 8 — Paymaster (Execution)
Domain-specific: paper-trades positions (trading) or logs purchases (e-commerce).

---

## Proof of Concept #1 — Trading

**Domain:** US stocks and crypto (NVDA, AAPL, TSLA, BTC, ETH, …)  
**Data:** `yfinance` (stocks) + Hyperliquid SDK (crypto perps)  
**Signal:** RSI + MACD + EMA cross + Bollinger Bands  
**Structural analysis:** Groq/Llama — identifies regime (trending/ranging/volatile)  
**Execution:** Paper trading with simulated portfolio, P&L tracking, Sharpe ratio

```
Scout (yfinance) → Quant (RSI/MACD/EMA) → Visionary (Groq) → Gate → Auditor → Passkey → Paymaster
```

What it proves about the framework:
- Handles real-time streaming market data
- LLM structural analysis works on candlestick / indicator context
- Confidence gate correctly filters low-agreement signals (HOLD)
- Auditor enforces position limits deterministically
- Biometric mandate flow works without blocking trades on other assets

---

## Proof of Concept #2 — E-Commerce

**Domain:** Consumer electronics, sneakers, laptops, phones, consoles, …  
**Data:** Best Buy API → Walmart API → SerpAPI → mock (in order of availability)  
**Signal:** Price vs. 30-day average, discount %, price trend  
**Structural analysis:** Groq/Llama — identifies if price is at a historical low  
**Execution:** Purchase log with budget tracking

```
Scout (BestBuy/Walmart) → PriceQuant (discount %) → PriceVisionary (Groq) → Gate → Passkey → Paymaster
```

What it proves about the framework:
- The **same Consensus Gate** works for binary buy/no-buy decisions, not just trading
- The **same mandate flow** works for purchase authorization
- **Zero changes to core** — only Scout + Quant + Visionary were swapped
- The **same dashboard** displays both modes via mode-switching

---

## Adding a New Domain (How the Framework Extends)

To add, for example, **Flight Prices** or **Gold Prices**:

1. **Scout plugin** — fetch price data from a flights/gold API
2. **Quant agent** — compute a price signal (e.g., price vs. 90-day average, seasonal patterns)
3. **Visionary agent** — LLM analyzes seasonal context, demand patterns

```python
# That's it. The framework handles everything else:
orchestrator.register_domain("flights", FlightScout, FlightQuant, FlightVisionary)
```

The Consensus Gate, security layer, biometric mandate, WebSocket events, and dashboard slots all work immediately.

---

## Architecture Diagram

```
                    ┌──────── main.py ────────┐
                    │  WSBroadcaster (8765)    │
                    │  MandateManager          │
                    │  Mode Controller         │
                    │  Webhook Server (8766)   │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │                                     │
       TRADING PIPELINE                    E-COMMERCE PIPELINE
              │                                     │
    Scout (yfinance/HL)              Scout (BestBuy/Walmart/SerpAPI)
    Quant (RSI/MACD/EMA)             PriceQuant (discount/trend)
    Visionary (Groq/Claude)          PriceVisionary (Groq)
    Sentiment (Groq)                       │
              │                            │
              └──────────┬─────────────────┘
                         │
                  Consensus Gate
                 (EXECUTE / HOLD / REVIEW)
                         │
                  Auditor Agent
                  (risk limits)
                         │
                  Biometric Passkey
                  (6-condition Valid(M))
                         │
                     Paymaster
               (trade / purchase log)
                         │
               logs/state.json ←────────── RAG Server (8767)
                         │                 (ChromaDB knowledge base)
               Next.js Dashboard (3000)
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
cd dashboard && npm install && cd ..

# 2. Configure
cp .env.example .env
# Edit .env — add your GROQ_API_KEY

# 3. Run all three terminals

# Terminal 1 — Backend
python main.py

# Terminal 2 — RAG knowledge server
python rag_server.py

# Terminal 3 — Dashboard
cd dashboard && npm run dev
```

Open **http://localhost:3000** → use the chat to start a mode:
- *"Start trading NVDA AAPL TSLA"*
- *"Monitor RTX 4090, MacBook Pro, AirPods"*

---

## Configuration

All via `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | — | Required for Visionary + Sentiment agents |
| `ASSETS` | `NVDA AAPL TSLA` | Assets to monitor (trading mode) |
| `INTERVAL_MINUTES` | `5` | Pipeline cycle interval |
| `INITIAL_BALANCE` | `10000` | Paper trading starting balance ($) |
| `GATE_TAU_QUANT` | `0.55` | Min Quant confidence (Gate Step 2) |
| `GATE_TAU_VISIONARY` | `0.55` | Min Visionary confidence (Gate Step 3) |
| `GATE_TAU_COMBINED` | `0.58` | Min combined confidence (Gate Step 7) |
| `GATE_DELTA_DIVERGENCE` | `0.25` | Soft divergence → REVIEW |
| `GATE_DELTA_HARD` | `0.35` | Hard divergence → HOLD |
| `DAILY_CAP` | `3000` | Daily spending limit ($) |
| `APEE_WEBAUTHN_SECRET` | *(dev)* | HMAC-SHA256 mandate signing secret |

---

## Project Structure

```
APEE/
├── main.py                     # ★ Canonical entry point
├── rag_server.py               # RAG knowledge base HTTP server
├── requirements.txt
├── .env.example
│
├── src/
│   ├── agents/
│   │   ├── consensus_gate.py   # 7-step gate algorithm
│   │   ├── auditor.py          # Deterministic risk enforcement
│   │   ├── sentiment.py        # Shared sentiment layer
│   │   ├── scout_trading.py    # POC 1: trading data ingestion
│   │   ├── quant_trading.py    # POC 1: fast technical signal
│   │   ├── visionary_trading.py# POC 1: LLM structural analysis
│   │   ├── scout_ecommerce.py  # POC 2: product price ingestion
│   │   ├── quant_ecommerce.py  # POC 2: price signal
│   │   └── visionary_ecommerce.py # POC 2: LLM deal analysis
│   │
│   ├── security/
│   │   ├── passkey.py          # 6-condition Valid(M)
│   │   ├── mandate_manager.py  # AsyncMandateManager (HMAC-SHA256)
│   │   └── webhook_server.py   # Mandate approval endpoint
│   │
│   ├── mcp/
│   │   ├── hub_trading.py      # yfinance MCP router
│   │   └── hub_ecommerce.py    # Multi-source product price router
│   │
│   ├── rag/
│   │   ├── rag_engine.py       # ChromaDB + sentence-transformers
│   │   └── knowledge_base.py   # 50-product knowledge base
│   │
│   ├── trading/
│   │   └── paymaster.py        # POC 1: paper trade executor
│   │
│   └── commerce/
│       └── paymaster_ecommerce.py  # POC 2: purchase log executor
│
└── dashboard/                  # Next.js live dashboard
    └── app/
        ├── page.js             # Mission control UI
        ├── globals.css         # Terminal/HUD design system
        └── api/
            ├── state/          # Reads logs/state.json
            ├── chat/           # Natural language command interface
            └── mandate/        # Biometric approval endpoint
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent LLM | Groq / Llama-3.3-70B (fast inference) |
| Structural LLM | Anthropic Claude (24h cached, advanced path) |
| ML Model | LightGBM (optional, 27-feature directional signal) |
| Vector DB | ChromaDB + sentence-transformers |
| Data | yfinance, Best Buy API, Walmart API, SerpAPI |
| Dashboard | Next.js, Tailwind CSS |
| Real-time | WebSockets (asyncio) |
| Security | HMAC-SHA256 (PoC) → py_webauthn (production path) |

---

## License

MIT
