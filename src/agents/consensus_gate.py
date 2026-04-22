"""
APEE — Consensus Gate
======================
Algorithm 1 from the research paper.
Quant + Visionary must agree before EXECUTE is issued.
This is what separates APEE from single-LLM systems.
"""

import logging

logger = logging.getLogger(__name__)

DIR_MAP = {"long": "bullish", "short": "bearish", "neutral": "neutral"}


def consensus_gate(
    quant:      dict,
    visionary:  dict,
    sentiment:  dict,
    tau_quant:         float = 0.55,
    tau_visionary:     float = 0.55,
    tau_combined:      float = 0.58,
    delta_divergence:  float = 0.20,
    delta_hard:        float = 0.35,
) -> dict:
    """
    Evaluate consensus between Quant and Visionary signals.

    Returns:
        decision:   EXECUTE | HOLD | REVIEW
        action:     long | short | neutral
        confidence: combined weighted confidence
        reason:     human-readable explanation
    """
    asset    = quant["asset"]
    q_dir    = quant["direction"]
    q_conf   = quant["confidence"]
    v_bias   = visionary["structural_bias"]
    v_conf   = visionary["confidence"]
    s_score  = sentiment.get("score", 0.0)
    s_conf   = sentiment.get("confidence", 0.3)

    # Step 1: Neutral → HOLD
    if q_dir == "neutral" or v_bias == "neutral":
        return _result(asset, "HOLD", "neutral", 0.0, q_conf, v_conf, s_conf,
                       "Neutral signal — waiting for clearer setup")

    # Step 2: Minimum confidence checks
    if q_conf < tau_quant:
        return _result(asset, "HOLD", "neutral", 0.0, q_conf, v_conf, s_conf,
                       f"Quant confidence {q_conf:.2f} below τ={tau_quant}")
    if v_conf < tau_visionary:
        return _result(asset, "HOLD", "neutral", 0.0, q_conf, v_conf, s_conf,
                       f"Visionary confidence {v_conf:.2f} below τ={tau_visionary}")

    # Step 3: Hard divergence → HOLD
    divergence = abs(q_conf - v_conf)
    if divergence >= delta_hard:
        return _result(asset, "HOLD", "neutral", 0.0, q_conf, v_conf, s_conf,
                       f"Hard divergence {divergence:.2f} — models too far apart")

    # Step 4: Direction agreement
    expected = DIR_MAP.get(q_dir, "neutral")
    agree    = (expected == v_bias)

    if not agree:
        return _result(asset, "REVIEW", "neutral", 0.0, q_conf, v_conf, s_conf,
                       f"Direction conflict: Quant={q_dir}, Visionary={v_bias}")

    # Step 5: Soft divergence → REVIEW
    if divergence >= delta_divergence:
        return _result(asset, "REVIEW", "neutral", 0.0, q_conf, v_conf, s_conf,
                       f"Soft divergence {divergence:.2f} — human review recommended")

    # Step 6: Combined confidence with sentiment boost
    combined = 0.45 * q_conf + 0.55 * v_conf
    if s_conf > 0.5:
        sentiment_dir = s_score > 0
        signal_dir    = q_dir == "long"
        if sentiment_dir == signal_dir:
            combined = min(combined * 1.05, 0.95)  # small sentiment boost

    if combined < tau_combined:
        return _result(asset, "HOLD", "neutral", combined, q_conf, v_conf, s_conf,
                       f"Combined confidence {combined:.2f} below τ={tau_combined}")

    # Step 7: All checks passed → EXECUTE
    reason = (
        f"Consensus: Quant={q_dir}@{q_conf:.2f}, "
        f"Visionary={v_bias}@{v_conf:.2f}, "
        f"Sentiment@{s_conf:.2f}, "
        f"Combined={combined:.2f}, Divergence={divergence:.2f}"
    )
    logger.info("[Gate] EXECUTE %s %s | %s", q_dir, asset, reason)

    return _result(asset, "EXECUTE", q_dir, combined, q_conf, v_conf, s_conf, reason,
                   divergence=divergence)


def _result(asset, decision, action, combined,
            quant_conf, visionary_conf, sentiment_conf, reason, divergence=None):
    if decision != "EXECUTE":
        logger.info("[Gate] %s %s | %s", decision, asset, reason)
    return {
        "asset":                  asset,
        "decision":               decision,
        "action":                 action,
        "combined_confidence":    round(combined, 4),
        "quant_confidence":       round(quant_conf, 4),
        "visionary_confidence":   round(visionary_conf, 4),
        "sentiment_confidence":   round(sentiment_conf, 4),
        "divergence":             round(abs(quant_conf - visionary_conf), 4)
                                  if divergence is None else round(divergence, 4),
        "reason":                 reason,
    }
