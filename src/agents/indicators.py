"""
APEE — Local Technical Indicators
===================================
All indicators computed from raw OHLCV candles.
No external dependencies beyond Python stdlib.
"""


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    result = [None] * (period - 1)
    result.append(sum(values[:period]) / period)
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def sma(values, period):
    return [
        None if i < period - 1
        else sum(values[i-period+1:i+1]) / period
        for i in range(len(values))
    ]


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return [None] * len(closes)
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    result = [None] * period
    gains  = [max(d, 0) for d in deltas[:period]]
    losses = [abs(min(d, 0)) for d in deltas[:period]]
    ag = sum(gains) / period
    al = sum(losses) / period
    result.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    for delta in deltas[period:]:
        ag = (ag * (period-1) + max(delta, 0)) / period
        al = (al * (period-1) + abs(min(delta, 0))) / period
        result.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return result


def macd(closes, fast=12, slow=26, signal=9):
    ef = ema(closes, fast)
    es = ema(closes, slow)
    ml = [f - s if f and s else None for f, s in zip(ef, es)]
    valid = [v for v in ml if v is not None]
    sig_raw = ema(valid, signal) if len(valid) >= signal else []
    pad = len(ml) - len(sig_raw)
    sl  = [None] * pad + sig_raw
    hist = [m - s if m and s else None for m, s in zip(ml, sl)]
    return ml, sl, hist


def bollinger(closes, period=20, std_dev=2):
    sm = sma(closes, period)
    upper, lower = [], []
    for i, s in enumerate(sm):
        if s is None:
            upper.append(None); lower.append(None)
        else:
            window = closes[max(0, i-period+1):i+1]
            std = (sum((x-s)**2 for x in window) / period) ** 0.5
            upper.append(s + std_dev * std)
            lower.append(s - std_dev * std)
    return upper, lower, sm


def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return [None] * len(candles)
    result = [None] * period
    avg = sum(trs[:period]) / period
    result.append(avg)
    for tr in trs[period:]:
        avg = (avg * (period - 1) + tr) / period
        result.append(avg)
    return result


def latest(lst):
    if not lst:
        return None
    return next((v for v in reversed(lst) if v is not None), None)


def compute_all(candles):
    if not candles or len(candles) < 20:
        return {}
    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [c["volume"] for c in candles]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50) if len(closes) >= 50 else [None]*len(closes)
    rsi14 = rsi(closes, 14)
    rsi7  = rsi(closes, 7)
    ml, sl, hist = macd(closes)
    bbu, bbl, bbm = bollinger(closes)
    atr14 = atr(candles, 14)

    cur = closes[-1]
    e20 = latest(ema20)
    e50 = latest(ema50)

    return {
        "current_price":   cur,
        "ema20":           e20,
        "ema50":           e50,
        "rsi14":           latest(rsi14),
        "rsi7":            latest(rsi7),
        "macd":            latest(ml),
        "macd_signal":     latest(sl),
        "macd_hist":       latest(hist),
        "bb_upper":        latest(bbu),
        "bb_lower":        latest(bbl),
        "bb_mid":          latest(bbm),
        "atr14":           latest(atr14),
        "volume":          volumes[-1],
        "ema_cross":       (e20 - e50) if e20 and e50 else 0,
        "price_vs_ema20":  (cur / e20 - 1) if e20 else 0,
        "price_vs_ema50":  (cur / e50 - 1) if e50 else 0,
        "return_1":        (closes[-1]/closes[-2]-1) if len(closes)>1 else 0,
        "return_5":        (closes[-1]/closes[-6]-1) if len(closes)>5 else 0,
        "return_20":       (closes[-1]/closes[-21]-1) if len(closes)>20 else 0,
        "recent_closes":   closes[-10:],
        "recent_highs":    highs[-10:],
        "recent_lows":     lows[-10:],
    }
