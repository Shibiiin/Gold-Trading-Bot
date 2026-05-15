"""Parses GoldBot report text into a structured trading signal.

Improvements over the original keyword-counting approach:
  • Negation-aware sentiment — "not bullish" counts as bearish.
  • Explicit direction extraction — recognises "Direction: BUY" patterns
    emitted by both the real GoldBot backend and the local stub.
  • Falls back gracefully to sentiment scoring when no explicit markers
    are present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TradeSignal:
    ticker: str
    direction: str
    confidence: float
    sentiment_score: float
    reasoning: str
    raw_report: str
    strategy_name: str = ""
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    setup_score: float = 0.0
    levels: dict[str, float] = field(default_factory=dict)


BULLISH_WORDS = [
    "bullish",
    "surge",
    "rally",
    "positive",
    "growth",
    "profit",
    "beat expectations",
    "strong demand",
    "upside",
    "buy",
    "outperform",
]
BEARISH_WORDS = [
    "bearish",
    "drop",
    "decline",
    "negative",
    "loss",
    "miss",
    "downside",
    "sell",
    "underperform",
    "risk",
    "concern",
    "fall",
]

# Words within a 3-word window before a keyword that flip its polarity
NEGATION_WORDS = frozenset({
    "not", "no", "never", "neither", "hardly", "barely",
    "don't", "doesn't", "didn't", "won't", "isn't",
    "aren't", "wasn't", "weren't", "cannot", "can't",
})


# ── Negation-aware counting ────────────────────────────────────────────────

def _count_with_negation(words: list[str], terms: list[str]) -> tuple[int, int]:
    """Count *terms* in the word list and return (affirmed, negated).

    A match is "negated" if any word in the 3-word look-back window
    belongs to NEGATION_WORDS (e.g. "not bullish" → negated bullish).
    """
    affirmed = 0
    negated = 0
    n = len(words)

    for term in terms:
        term_tokens = term.lower().split()
        tlen = len(term_tokens)
        for i in range(n - tlen + 1):
            if words[i : i + tlen] == term_tokens:
                lookback = words[max(0, i - 3) : i]
                if any(w in NEGATION_WORDS for w in lookback):
                    negated += 1
                else:
                    affirmed += 1
    return affirmed, negated


def score_sentiment(text: str) -> float:
    """Score report sentiment with negation-aware counting.

    Negated bullish words count as bearish and vice versa, so
    "The outlook is not bullish" correctly pushes sentiment negative.
    """
    words = (text or "").lower().split()
    if not words:
        return 0.0

    bull_affirmed, bull_negated = _count_with_negation(words, BULLISH_WORDS)
    bear_affirmed, bear_negated = _count_with_negation(words, BEARISH_WORDS)

    # Flipped polarities: negated bull → bear, negated bear → bull
    effective_bull = bull_affirmed + bear_negated
    effective_bear = bear_affirmed + bull_negated

    total = effective_bull + effective_bear
    if total == 0:
        return 0.0
    return round((effective_bull - effective_bear) / total, 3)


# ── Explicit structured extraction ─────────────────────────────────────────

def _extract_explicit_direction(text: str) -> str | None:
    """Extract an explicit direction from structured report text.

    Matches patterns such as:
        Direction: BUY
        Recommendation: SELL
        Signal: HOLD
        Action: BUY
    """
    patterns = (
        r"direction\s*:\s*(BUY|SELL|HOLD)",
        r"recommendation\s*:\s*(BUY|SELL|HOLD)",
        r"signal\s*:\s*(BUY|SELL|HOLD)",
        r"action\s*:\s*(BUY|SELL|HOLD)",
    )
    for pat in patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def extract_confidence(text: str) -> float:
    """Extract explicit confidence or derive one from sentiment strength."""
    haystack = text or ""
    patterns = (
        r"confidence\s*:\s*(\d{1,3})%",
        r"(\d{1,3})%\s*confident",
    )
    for pattern in patterns:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return min(int(match.group(1)) / 100.0, 1.0)
    return round(min(abs(score_sentiment(haystack)) * 1.5, 0.95), 3)


def parse_report(ticker: str, report_text: str) -> TradeSignal:
    """Convert free-form report text into a structured TradeSignal.

    1. First tries explicit direction markers (e.g. "Direction: BUY").
    2. Falls back to negation-aware sentiment scoring.
    """
    cleaned = (report_text or "").strip()
    sentiment = score_sentiment(cleaned)
    confidence = extract_confidence(cleaned)

    # Prefer explicit direction from report if available
    explicit = _extract_explicit_direction(cleaned)
    if explicit:
        direction = explicit
    elif sentiment > 0.15:
        direction = "BUY"
    elif sentiment < -0.15:
        direction = "SELL"
    else:
        direction = "HOLD"

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
    reasoning = next((p for p in paragraphs if len(p) > 40), "") or cleaned[:300]

    return TradeSignal(
        ticker=ticker,
        direction=direction,
        confidence=confidence,
        sentiment_score=sentiment,
        reasoning=reasoning,
        raw_report=cleaned,
    )
