# APEE — Per-Agent Confidence Scores

## What Changed

Every agent in the pipeline now produces a real confidence score (0.0–1.0) that flows from backend → state.json → dashboard.

---

## Agent Confidence Reference

| Agent | Score Range | Meaning |
|-------|-------------|---------|
| **Scout** | 0.0 or 1.0 | Data quality — 1.0 if price fetched, 0.0 if fetch failed |
| **Quant** | 0.0–0.90 | Technical signal strength from RSI, MACD, EMA cross, Bollinger |
| **Visionary** | 0.0–1.0 | Structural bias confidence returned by Groq/Llama |
| **Sentiment** | 0.0–1.0 | Sentiment confidence returned by Groq/Llama (0.3 if no API key) |
| **Auditor** | 0.0–1.0 | Headroom score — how far from position/exposure limits; 0.0 if rejected |
| **Gate** | 0.0–0.95 | Combined weighted confidence (0.45×Quant + 0.55×Visionary + sentiment boost) |

---

## Files Modified

### 1. `src/agents/consensus_gate.py`
- `_result()` now accepts and emits `sentiment_confidence` in every gate output
- All 8 call sites inside `consensus_gate()` pass `s_conf`
- EXECUTE reason string now includes `Sentiment@{s_conf:.2f}`
- New field in gate output dict: `"sentiment_confidence": float`

### 2. `src/agents/auditor.py`
- `validate()` return type changed from `tuple[bool, str, float]` → `tuple[bool, str, float, float]`
- 4th value is `approval_confidence`:
  - Rejected for any rule → `0.0`
  - Approved → `1.0 - max(exposure_ratio, position_ratio) * 0.6`, clamped to `[0.1, 1.0]`
  - Reflects how comfortably the trade fits within all limits

### 3. `main.py`

**Trading pipeline (`run_trading → eval_asset`)**
- Auditor unpack updated: `approved, reason, adjusted, aud_conf = auditor.validate(...)`
- `agent_signals` dict collected per cycle, per asset:
  ```python
  agent_signals[asset] = {
      "scout":     1.0 | 0.0,
      "quant":     q_sig["confidence"],
      "visionary": v_sig["confidence"],
      "sentiment": sent["confidence"],
      "auditor":   aud_conf,   # None if gate didn't EXECUTE
      "gate":      gate["combined_confidence"],
  }
  ```
- `state.json` now includes `"agent_signals": { "NVDA": {...}, "AAPL": {...}, ... }`

**Ecommerce pipeline (`run_ecommerce → eval_product`)**
- Same `agent_signals` structure collected per product
- `sentiment` fixed at `0.3` (ecommerce pipeline has no sentiment agent)
- `auditor` is `None` (no auditor in ecommerce mode)

### 4. `dashboard/app/page.js`

**Agents tab**
- Reads `state.agent_signals`, averages across all assets for display
- `Scout` confidence: live from `avgConf('scout')` instead of hardcoded `1.0`
- `Sentiment` confidence: live from `last.sentiment_confidence` (gate log) or `avgConf('sentiment')` instead of hardcoded `0.6`
- `Auditor` confidence: live from `audAvg()` instead of hardcoded `1.0`; shows `STANDBY` when no EXECUTE decision was made this cycle

**Gate Log table**
- New **Sent** column showing `sentiment_confidence` per decision row (yellow)
- Column order: Time → Asset → Decision → Action → Quant → Vision → **Sent** → Combined → Reason

---

## Data Flow

```
eval_asset()
  ├── Scout.fetch_all()        → scout_conf   (1.0 / 0.0)
  ├── SentimentAnalyzer()      → sent["confidence"]
  ├── QuantAgent.analyze()     → q_sig["confidence"]
  ├── VisionaryAgent.analyze() → v_sig["confidence"]
  ├── consensus_gate()         → gate["combined_confidence"]
  │                               gate["sentiment_confidence"]  ← NEW
  └── AuditorAgent.validate()  → aud_conf                       ← NEW
          ↓
  agent_signals[asset] = { scout, quant, visionary, sentiment, auditor, gate }
          ↓
  state.json  →  /api/state  →  dashboard Agents tab + Gate Log
```

---

## Gate Log Schema (updated)

```json
{
  "asset":                 "NVDA",
  "decision":              "EXECUTE | HOLD | REVIEW",
  "action":                "long | short | neutral",
  "combined_confidence":   0.7210,
  "quant_confidence":      0.7500,
  "visionary_confidence":  0.6900,
  "sentiment_confidence":  0.6200,
  "divergence":            0.0600,
  "reason":                "Consensus: Quant=long@0.75, Visionary=bullish@0.69, Sentiment@0.62, ...",
  "action_taken":          "executed_long",
  "timestamp":             "2026-04-22T10:00:00+00:00"
}
```

---

## Auditor Confidence Formula

```
exposure_ratio = (current_exposure + alloc_usd) / max_exposure_usd
position_ratio = (open_positions + 1) / max_positions
confidence     = max(0.1,  1.0 - max(exposure_ratio, position_ratio) * 0.6)
```

Examples:
- 1 position open out of 5, 10% exposure used → confidence ≈ **0.88**
- 4 positions open out of 5, 55% exposure used → confidence ≈ **0.34**
- Any rule violation → confidence = **0.0** (rejected)
