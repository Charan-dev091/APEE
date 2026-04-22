# APEE — Autonomous Personal Economy Engine
## Technical Report

---

## 1. System Overview

**APEE** (Autonomous Personal Economy Engine) is a multi-agent AI system designed to make autonomous financial decisions across two distinct domains:

| Mode | Domain | Data Sources | Execution |
|------|---------|--------------|-----------|
| **Trading** | Stocks & crypto (NVDA, AAPL, TSLA, BTC, ETH…) | yfinance, Hyperliquid SDK, CoinGecko | Simulated Paymaster (paper trading) |
| **E-Commerce** | Consumer products (GPUs, laptops, sneakers…) | Best Buy API, Walmart API, SerpAPI, mock | Buy signal + purchase log |

The system runs as three concurrent processes:

```
Terminal 1 →  python main.py        (Backend: pipelines + WebSocket + webhook)
Terminal 2 →  python rag_server.py  (RAG: ChromaDB knowledge base HTTP server)
Terminal 3 →  cd dashboard && npm run dev  (Frontend: Next.js dashboard)
```

All three communicate via:
- **WebSocket (port 8765)** — live event stream to dashboard
- **Webhook server (port 8766)** — biometric mandate approval endpoint
- **RAG server (port 8767)** — semantic product knowledge queries
- **`logs/state.json`** — polled by dashboard `/api/state` route for cycle state

---

## 2. Architecture

### 2.1 High-Level Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     main.py  (Orchestrator)                      │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │ WSBroadcaster│  │ Mode Controller  │  │ AsyncMandateManager│  │
│  │  (port 8765) │  │ (watches config) │  │  (biometric flow)  │  │
│  └──────────────┘  └─────────────────┘  └────────────────────┘  │
└───────────────────────────┬──────────────────────────────────────┘
              ┌─────────────┴─────────────┐
              │                           │
     TRADING PIPELINE              E-COMMERCE PIPELINE
              │                           │
     Scout → Quant                 ProductScout → PriceQuant
     Visionary → Sentiment         PriceVisionary
              │                           │
              └────────────┬──────────────┘
                    Consensus Gate
                   (EXECUTE/HOLD/REVIEW)
                           │
                  Auditor (Trading only)
                           │
                  Biometric Passkey
                   (6-condition Valid(M))
                           │
                       Paymaster
                  (trade / buy execution)
```

### 2.2 Dual Entry Points

The codebase contains two entry points at different evolution stages:

| File | Status | LLM Backend | Exchange |
|------|--------|-------------|----------|
| `main.py` (root) | ✅ **Canonical — use this** | Groq / Llama-3.3-70B | yfinance (paper) |
| `src/main.py` | ⚠️ Experimental / Incomplete | Anthropic Claude + LightGBM | Hyperliquid (live perps) |

`src/main.py` is missing five modules not yet committed to the repository (`risk_manager`, `config_loader`, `hyperliquid_api`, `utils/formatting`, `utils/prompt_utils`) and cannot run as-is. Both files now carry clear status headers.

---

## 3. Agent Pipeline

### 3.1 Scout (Data Ingestion Layer)

**Role:** Fetch raw market data from any configured source and deliver a standardized `DataPacket` to the orchestrator. Zero opinion about data meaning.

**Plugin architecture** — adding a new source requires only registering a new function:

| Plugin | Data | Mode |
|--------|------|------|
| `hyperliquid` | OHLCV, funding rate, open interest | STREAM (live) |
| `yfinance` | US stocks OHLCV (2010 → present) | BATCH + STREAM |
| `coingecko` | BTC/USD daily back to 2010 | BATCH |
| `ccxt` | Crypto OHLCV via Binance (2017 → present) | BATCH |

**Failure handling:** On primary source failure, falls back to `backup_source` if configured. Both failing → `PacketStatus.FAILED`. The Orchestrator decides what to do — the Scout never does.

**Confidence output:** Binary — `1.0` if price fetched, `0.0` on failure.

---

### 3.2 Quant / Analyst (Fast Signal Layer)

**Role:** Compute a directional signal with confidence from raw OHLCV candles. Inference < 50ms.

**Indicators computed:**

| Category | Indicators |
|----------|-----------|
| Momentum | RSI (7, 14), MACD, MACD histogram, Stochastic RSI |
| Trend | EMA (20, 50), EMA crossover, ADX |
| Volatility | ATR (3, 14), Bollinger Bands (upper, lower, width) |
| Volume | OBV, VWAP |
| Returns | 1-bar, 5-bar, 20-bar returns |
| Structure | H/L ratio, close position within candle |

**Two model layers (Analyst — advanced path only):**
1. **LightGBM model** (primary) — trained offline on 2010→present data. 27-feature vector. Temporal train/test split.
2. **Rule-based heuristic** (fallback) — RSI (0.25 weight) + MACD histogram (0.25) + EMA cross (0.30) + Bollinger position (0.20). Used when model file not loaded. Also used as the ablation baseline in the research paper.

**Output:** `direction` (long / short / neutral) + `confidence` (0.0 – 0.90)

---

### 3.3 Visionary / Strategist (Structural Analysis Layer)

**Role:** Identify the structural backdrop — price regime, key levels, multi-timeframe context — against which the Quant's fast signals are evaluated.

**Key design choice:** The Strategist is *intentionally slow-moving*. It caches its signal for **24 hours** unless explicitly invalidated. This represents the structural view, not a reaction to each 5-minute candle.

**LLM call (Claude / Groq):**
- Input: 4h candles, EMA series, RSI series, MACD series, ATR, current price, price range (10-day)
- Output (strict JSON): `structural_bias` (bullish/bearish/neutral), `regime` (trending/ranging/volatile/uncertain), `confidence` (0–1), `key_levels` (support/resistance lists), `rationale` (one paragraph), `signal_valid_hours`

**Fallback (no API key):** Uses Quant direction as a proxy with a 10% confidence penalty.

---

### 3.4 Sentiment Analyzer

**Role:** Provide a soft sentiment signal from recent price action and order book context.

- Called once per cycle per asset, cached for 12 cycles
- Uses Groq/Llama with a strict JSON response schema
- Fallback: `confidence = 0.3`, `sentiment = neutral` (when no API key)
- Output: `sentiment` (bullish/bearish/neutral), `score` (-1.0 – 1.0), `confidence` (0–1)
- Not used in the E-Commerce pipeline (fixed at `confidence = 0.3`)

---

### 3.5 Consensus Gate ⭐ Core Innovation

**Role:** The primary safety mechanism preventing impulsive trades. Both the quantitative and qualitative agents must independently agree before any EXECUTE is issued.

**7-step sequential algorithm:**

| Step | Condition | Failure → |
|------|-----------|-----------|
| 1 | Either agent returns `neutral` | **HOLD** |
| 2 | Quant confidence < τ_quant (default 0.55) | **HOLD** |
| 3 | Visionary confidence < τ_visionary (default 0.55) | **HOLD** |
| 4 | Hard divergence \|q_conf − v_conf\| ≥ δ_hard (default 0.35) | **HOLD** |
| 5 | Direction disagreement (long ≠ bullish, etc.) | **REVIEW** |
| 6 | Soft divergence ≥ δ_divergence (default 0.25) | **REVIEW** |
| 7 | Combined confidence < τ_combined (default 0.58) | **HOLD** |
| ✓ | All checks passed | **EXECUTE** |

**Combined confidence formula:**
```
combined = 0.45 × quant_conf + 0.55 × visionary_conf
```
With optional sentiment boost (+5%, capped at 0.95) when sentiment direction aligns with signal direction and `sentiment_conf > 0.5`.

**All thresholds are configurable** via `.env` (`GATE_TAU_QUANT`, `GATE_TAU_VISIONARY`, etc.).

**Gate output per decision:**
```json
{
  "asset": "NVDA",
  "decision": "EXECUTE | HOLD | REVIEW",
  "action": "long | short | neutral",
  "combined_confidence": 0.7210,
  "quant_confidence": 0.7500,
  "visionary_confidence": 0.6900,
  "sentiment_confidence": 0.6200,
  "divergence": 0.0600,
  "reason": "Consensus: Quant=long@0.75, Visionary=bullish@0.69, Sentiment@0.62, ..."
}
```

---

### 3.6 Auditor Agent (Risk Enforcement Layer)

**Role:** Pure rule-based validation before any EXECUTE trade reaches execution. No ML. No LLM. Deterministic only.

**Five checks (in order):**
1. **Minimum balance reserve** — balance must exceed `initial_balance × 20%`
2. **Max concurrent positions** — default 5; new asset blocked if limit reached
3. **Position size cap** — capped to `total_value × 20%` (adjusts allocation, doesn't reject)
4. **Minimum order size** — allocation must be ≥ $11.00
5. **Total exposure check** — `(current_exposure + new_alloc) ≤ total_value × 60%`

**Approval confidence formula:**
```
exposure_ratio = (current_exposure + alloc) / max_exposure_usd
position_ratio = (open_positions + 1) / max_positions
confidence     = max(0.1,  1.0 − max(exposure_ratio, position_ratio) × 0.6)
```
Examples:
- 1/5 positions, 10% exposure used → confidence ≈ **0.88**
- 4/5 positions, 55% exposure used → confidence ≈ **0.34**
- Any rule violation → confidence = **0.0**

---

### 3.7 Security Layer

#### BiometricPasskey — 6-Condition Valid(M)

Every trade that passes the Gate and Auditor must clear six cryptographic/risk conditions before execution:

| Condition | Mechanism |
|-----------|-----------|
| 1. Challenge binding | SHA-256 of mandate fields must match `webauthn.challenge` |
| 2. WebAuthn UV required | `user_verification = "required"` enforced |
| 3. TEE attestation | SGX mrenclave must be present (simulated in PoC) |
| 4. Oracle consensus | Two independent yfinance samples averaged; warns if delta > 0.5% |
| 5. Atomic daily quota | Thread-safe `AtomicQuotaManager` enforces daily spending cap |
| 6. Revocation check | In-memory `RevocationRegistry`; any revoked mandate is rejected |

#### AsyncMandateManager — Non-Blocking Approval Flow

**Problem solved:** The original blocking approach (`run_in_executor(None, passkey.authorize...)`) would stall the event loop while waiting for biometric confirmation — with 10 concurrent assets, the thread pool exhausted and the entire system froze.

**Solution:** The mandate lifecycle uses `asyncio.Future` so the event loop stays free:

```
1. request()            → PendingMandate created, Future set, returns immediately
2. WebSocket push       → Frontend receives biometric prompt
3. User approves        → POST /mandate/approve (with HMAC signature)
4. approve()            → Future resolved, orchestrator unblocks
5. paymaster.execute()  → Trade filled
```

Mandates expire after **120 seconds** if not approved. A background task runs every 30s to clean up expired mandates.

#### WebAuthn Signature (PoC Mode)

After fixes applied in this work:
- Signatures are verified using **HMAC-SHA256** (`hmac.compare_digest` — timing-safe)
- Server signs `mandate.challenge` with `APEE_WEBAUTHN_SECRET` (from `.env`)
- Frontend must return the correct HMAC; any other value → `REJECTED`
- **Production upgrade path** is documented inline: replace HMAC with `py_webauthn` assertion verification against a stored credential public key

---

### 3.8 Paymaster (Execution Layer)

**Trading Paymaster:**
- Manages a simulated portfolio (balance, positions, P&L)
- Executes long/short orders at current market price
- Tracks position history and total return
- `get_portfolio(prices)` returns full portfolio snapshot per cycle

**E-Commerce Paymaster:**
- Tracks a budget (default $2,000)
- Logs purchases with price, source, timestamp
- No actual API calls to checkout — records intent

---

## 4. RAG System

A **Retrieval-Augmented Generation** knowledge base provides product context to the chat assistant.

| Component | Technology |
|-----------|-----------|
| Vector store | ChromaDB (persisted to `logs/chroma_db/`) |
| Embeddings | `sentence-transformers` (all-MiniLM-L6-v2) |
| Knowledge base | ~50 hand-curated products across 10 categories |
| Server | Plain Python `HTTPServer` on port 8767 |

**Categories in knowledge base:** GPUs (NVIDIA + AMD), CPUs (Intel + AMD), Laptops, Phones, Consoles, Headphones, Sneakers, Monitors, Peripherals, Stocks, Crypto.

Each product entry includes: `typical_min`, `typical_max`, `msrp` — enabling the agent to judge whether a current price is a good deal.

**API:**
```
GET  /rag/query?q=RTX+4070    → {query, context: {text, similarity, category, ...}}
GET  /rag/health              → {status: "ok", documents: N}
POST /rag/query               → same, body: {query: "..."}
```

---

## 5. Dashboard

A **Next.js** (App Router) application served on `http://localhost:3000`.

**Design language:** Terminal/HUD aesthetic — deep dark backgrounds (`#05070f`), JetBrains Mono for all numeric values, animated live-dot pulse, scanline overlay, corner accent brackets, glow effects on key numbers.

**Data flow:**
- Polls `/api/state` (reads `logs/state.json`) every N seconds
- WebSocket connection to port 8765 for live event push
- POST to `/api/chat` to send natural language commands (start trading, set wishlist, etc.)
- POST to `/api/mandate/approve` or `/api/mandate/reject` for biometric decisions

**Key views:**
| View | Content |
|------|---------|
| Chat | Natural language interface; starts trading/ecommerce mode; sets config |
| Overview | Portfolio balance, P&L, prices, gate stats (EXECUTE/HOLD/REVIEW counts) |
| Agents | Per-agent confidence scores (Scout, Quant, Visionary, Sentiment, Auditor, Gate) |
| Gate Log | Full decision history table with columns: Time, Asset, Decision, Action, Quant, Vision, Sent, Combined, Reason |
| Biometric | Pending mandate cards (yellow pulsing border); Approve / Reject buttons |

---

## 6. Persistent State & Logging

| File | Written by | Content |
|------|-----------|---------|
| `logs/state.json` | Main pipeline (per cycle) | Full system state — mode, cycle, prices, portfolio, gate_stats, agent_signals |
| `logs/events.jsonl` | WSBroadcaster (every event) | Append-only timestamped event log |
| `logs/gate_decisions.jsonl` | GateLogger (every decision) | Full gate outputs with action_taken |
| `logs/portfolio_history.jsonl` | Trading pipeline (per cycle) | Portfolio snapshots over time |
| `logs/app_config.json` | Dashboard `/api/chat` | Mode + config; deleted by Mode Controller after reading |
| `logs/rag_result.json` | RAG server | Last query/result pair |

**`agent_signals` structure in `state.json`:**
```json
{
  "agent_signals": {
    "NVDA": {
      "scout":     1.0,
      "quant":     0.7500,
      "visionary": 0.6900,
      "sentiment": 0.6200,
      "auditor":   0.8800,
      "gate":      0.7210
    }
  }
}
```

---

## 7. Configuration Reference

All configurable via `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | — | Groq/Llama API key (required for Visionary + Sentiment) |
| `SERPAPI_KEY` | — | SerpAPI key (optional; e-commerce price enrichment) |
| `ASSETS` | `NVDA AAPL TSLA` | Whitespace-separated asset list |
| `INTERVAL_MINUTES` | `5` | Pipeline cycle interval |
| `INITIAL_BALANCE` | `10000` | Paper trading starting balance ($) |
| `BASE_ALLOCATION_USD` | `300` | Base allocation per trade before confidence scaling |
| `MAX_ALLOC_PER_TRADE` | `1000` | Hard cap per trade ($) |
| `DAILY_CAP` | `3000` | Daily spending limit enforced by quota manager ($) |
| `GATE_TAU_QUANT` | `0.55` | Minimum Quant confidence to pass Gate Step 2 |
| `GATE_TAU_VISIONARY` | `0.55` | Minimum Visionary confidence to pass Gate Step 3 |
| `GATE_TAU_COMBINED` | `0.58` | Minimum combined confidence to pass Gate Step 7 |
| `GATE_DELTA_DIVERGENCE` | `0.25` | Soft divergence threshold (→ REVIEW) |
| `GATE_DELTA_HARD` | `0.35` | Hard divergence threshold (→ HOLD) |
| `WS_PORT` | `8765` | WebSocket server port |
| `WEBHOOK_PORT` | `8766` | Biometric webhook HTTP port |
| `RAG_PORT` | `8767` | RAG knowledge base HTTP port |
| `STOP_CHECK_SECS` | `30` | Mandate cleanup interval |
| `LOG_DIR` | `./logs` | Log and state file directory |
| `APEE_WEBAUTHN_SECRET` | *(dev default)* | HMAC-SHA256 signing secret for mandate approval |

---

## 8. Dependencies

```
# Core (root main.py — Trading + E-Commerce pipeline)
groq>=0.9.0
python-dotenv>=1.0.0
requests>=2.31.0
yfinance>=0.2.36
websockets>=12.0
chromadb>=0.4.0
sentence-transformers>=2.2.0

# Advanced path (src/agents/orchestrator.py + Strategist)
anthropic>=0.25.0
numpy>=1.26.0

# Optional — LightGBM model training & inference
# pip install lightgbm pandas pyarrow
```

**Dashboard:**
```json
{
  "next": "latest",
  "tailwindcss": "^3",
  "postcss": "^8"
}
```

---

## 9. Critical Issues Found & Fixed

### Issue 1 — Two Divergent Entry Points

**Problem:** Both `main.py` (root) and `src/main.py` claimed to be the entry point. `src/main.py` targets a completely different stack (Anthropic Claude + LightGBM + Hyperliquid live exchange) and is missing five modules not committed to the repository, making it non-runnable.

**Fix applied:**
- `main.py` (root) docstring updated: `★ CANONICAL ENTRY POINT ★` — clearly states it's what `START.md` means
- `src/main.py` docstring replaced with a full `⚠ EXPERIMENTAL / INCOMPLETE ⚠` status block listing every missing module and what's needed to complete it

**Files changed:** `main.py`, `src/main.py`

---

### Issue 2 — Missing Packages in `requirements.txt`

**Problem:** `src/agents/orchestrator.py` and `src/agents/strategist.py` import `anthropic` and use `numpy`, but neither appeared in `requirements.txt`. `src/agents/analyst.py` needs `lightgbm` for ML inference.

**Fix applied:** `requirements.txt` restructured into three labeled sections:
1. **Core** — all packages for `main.py` (already correct)
2. **Advanced** — `anthropic>=0.25.0`, `numpy>=1.26.0`
3. **Optional (commented)** — `lightgbm`, `pandas`, `pyarrow` with install instructions

**Files changed:** `requirements.txt`

---

### Issue 3 — Real SerpAPI Key Committed to Repository

**Problem:** `.env.example` contained a real, live SerpAPI API key (`23a944ee7b2429d717633a0e0ca8a6f9f76ac25303ad11e8f441badc28246dec`) rather than a placeholder. Anyone with repository access could use or abuse the key.

**Fix applied:** Replaced with `your_serpapi_key_here`.

> ⚠️ **Action required:** If this file was ever committed to a git repository (even privately), the key should be considered compromised. Revoke it at [serpapi.com](https://serpapi.com) and generate a new one.

**Files changed:** `.env.example`

---

### Issue 4 — Simulated WebAuthn Accepted Any String

**Problem:** `AsyncMandateManager.approve()` contained this logic:
```python
# For PoC: accept any non-empty signature
if not signature:
    ...reject...
# Otherwise: proceed to approve (NO VERIFICATION)
```
Any caller who passed a non-empty string — including `"x"` or `"fake"` — would bypass the entire biometric layer and execute a trade.

**Fix applied:**

**`src/security/mandate_manager.py`:**
- Added `_POC_SIGNING_SECRET` (read from `APEE_WEBAUTHN_SECRET` env var)
- Added `_make_expected_sig(challenge)` → HMAC-SHA256 of the mandate challenge
- `approve()` now runs `hmac.compare_digest(signature, expected)` — timing-safe comparison
- Any signature that doesn't match → `REJECTED`, Future resolved with failure
- Full production upgrade path documented inline (pointing to `py_webauthn` library)

**`src/security/webhook_server.py`:**
- Removed hardcoded `"simulated_webauthn_sig"` default
- Auto-approve path now computes `_make_expected_sig(mandate.challenge)` from the live mandate object

**`.env.example`:**
- Added `APEE_WEBAUTHN_SECRET=change-me-to-a-random-secret`

**Files changed:** `src/security/mandate_manager.py`, `src/security/webhook_server.py`, `.env.example`

---

## 10. Remaining Medium-Priority Issues (Not Fixed)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| M1 | `src/indicators/` and `src/utils/` are empty | `src/indicators/`, `src/utils/` | `src/main.py` path cannot run; `src/agents/analyst.py` + `orchestrator.py` fail to import |
| M2 | `src/agent/` directory is empty | `src/agent/` | Dead directory; cosmetic confusion |
| M3 | No SerpAPI rate limiting in e-commerce scout | `src/mcp/hub_ecommerce.py` | Risk of SerpAPI quota burn on high-frequency cycles |
| M4 | Oracle DELTA_MAX (0.5%) too tight for volatile stocks | `src/security/passkey.py` line 96 | Excessive "price fluctuation" warnings in normal operation on TSLA/NVDA |
| M5 | `calculate_total_return()` hardcodes initial balance | `src/main.py` line 618 | Incorrect return % if balance ≠ $10,000 |

---

## 11. Strengths Summary

| Strength | Why It Matters |
|----------|---------------|
| **7-step Consensus Gate** | Requires independent quant + structural agreement; eliminates single-model overconfidence |
| **Dual-mode shared framework** | Trading and e-commerce share gate, confidence scoring, WebSocket, mandate flow |
| **Non-blocking async mandate** | asyncio.Future keeps event loop free during biometric wait; prevents thread pool exhaustion |
| **Plugin-based Scout** | Adding forex, real estate, or commodities needs only a new `register_plugin()` call |
| **6-condition biometric** | Challenge binding + oracle consensus + atomic quota + revocation = multiple independent safety layers |
| **LightGBM + Claude hybrid** | Fast ML (<50ms) for intraday signals + slow LLM (24h cached) for structural regime — architecturally complementary |
| **Per-agent confidence transparency** | Every agent emits a scored 0–1 confidence; full `agent_signals` dict flows live to the dashboard |
| **Fail-safe defaults** | Failed Scout → `confidence=0.0` → Gate blocks at Step 2 automatically |
| **HMAC mandate verification** | After fix: mandate approvals require cryptographic proof, not just a non-empty string |
