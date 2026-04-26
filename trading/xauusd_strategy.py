"""Level-based XAUUSD strategy for conservative buy/sell execution."""

from __future__ import annotations

from trading.seed_builder import fetch_market_snapshot, fetch_price_history
from trading.signal_parser import TradeSignal

TICKER = "XAUUSD"
SETUP_THRESHOLD = 68.0
NEAR_LEVEL_ATR = 0.6
BREAKOUT_ATR = 0.12
STOP_BUFFER_ATR = 0.35
BOUNCE_RR = 1.6
BREAKOUT_RR = 1.8


def _ema(series, span: int):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series, period: int = 14):
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + relative_strength))


def _atr(frame, period: int = 14):
    previous_close = frame["Close"].shift(1)
    true_range = (frame["High"] - frame["Low"]).to_frame("hl")
    true_range["hc"] = (frame["High"] - previous_close).abs()
    true_range["lc"] = (frame["Low"] - previous_close).abs()
    return true_range.max(axis=1).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _round_price(value: float | None) -> float:
    return round(float(value or 0.0), 2)


def _make_hold(reason: str, entry_price: float = 0.0, levels: dict | None = None) -> TradeSignal:
    return TradeSignal(
        ticker=TICKER,
        direction="HOLD",
        confidence=0.0,
        sentiment_score=0.0,
        reasoning=reason,
        raw_report=reason,
        strategy_name="xauusd_levels",
        entry_price=_round_price(entry_price),
        setup_score=0.0,
        levels=levels or {},
    )


def _build_levels(intraday, hourly, current_price: float) -> dict[str, float]:
    recent_intraday = intraday.iloc[:-1].tail(32)
    recent_session = intraday.iloc[:-1].tail(16)
    recent_hourly = hourly.iloc[:-1].tail(24)

    support_candidates = [
        float(recent_intraday["Low"].min()),
        float(recent_session["Low"].min()),
        float(recent_hourly["Low"].min()),
    ]
    resistance_candidates = [
        float(recent_intraday["High"].max()),
        float(recent_session["High"].max()),
        float(recent_hourly["High"].max()),
    ]

    supports_below = [level for level in support_candidates if level <= current_price]
    resistances_above = [level for level in resistance_candidates if level >= current_price]

    support = max(supports_below) if supports_below else min(support_candidates)
    resistance = min(resistances_above) if resistances_above else max(resistance_candidates)

    return {
        "support": _round_price(support),
        "resistance": _round_price(resistance),
        "session_low": _round_price(float(recent_session["Low"].min())),
        "session_high": _round_price(float(recent_session["High"].max())),
        "day_low": _round_price(float(recent_hourly["Low"].min())),
        "day_high": _round_price(float(recent_hourly["High"].max())),
    }


def _build_reason(
    *,
    setup_name: str,
    direction: str,
    score: float,
    entry: float,
    stop_loss: float,
    take_profit: float,
    levels: dict[str, float],
    rsi_value: float,
    atr_value: float,
    ema_fast: float,
    ema_slow: float,
    volume_ratio: float = 1.0,
) -> str:
    vol_label = "ACTIVE" if volume_ratio >= 1.5 else "normal"
    return (
        f"{setup_name} {direction.lower()} setup on XAUUSD. "
        f"Score {score:.0f}/100 with entry {entry:.2f}, stop {stop_loss:.2f}, target {take_profit:.2f}. "
        f"Support {levels['support']:.2f}, resistance {levels['resistance']:.2f}, "
        f"EMA20 {ema_fast:.2f}, EMA50 {ema_slow:.2f}, RSI14 {rsi_value:.1f}, ATR14 {atr_value:.2f}. "
        f"Volume {vol_label} ({volume_ratio:.1f}x avg). "
        "The setup only triggers when price reacts at a clear level or confirms a breakout."
    )


def analyze_xauusd_setup() -> TradeSignal:
    """Return a trade-ready XAUUSD setup or HOLD if conditions are weak."""
    intraday = fetch_price_history(TICKER, period="10d", interval="15m")
    hourly = fetch_price_history(TICKER, period="60d", interval="1h")
    snapshot = fetch_market_snapshot(TICKER)

    if intraday is None or hourly is None:
        return _make_hold("Price history unavailable for XAUUSD.")

    intraday = intraday.copy()
    intraday["ema20"] = _ema(intraday["Close"], 20)
    intraday["ema50"] = _ema(intraday["Close"], 50)
    intraday["rsi14"] = _rsi(intraday["Close"], 14)
    intraday["atr14"] = _atr(intraday, 14)
    intraday = intraday.dropna(subset=["ema20", "ema50", "rsi14", "atr14"])

    if len(intraday) < 80 or len(hourly) < 48:
        return _make_hold("Not enough XAUUSD candles to evaluate the setup.")

    # ── Market Closed Check ───────────────────────────────────────────
    # If the last candle is older than 12 hours, the market is likely closed for the weekend.
    from datetime import datetime, timezone, timedelta
    last_candle_time = intraday.index[-1]
    
    # Ensure last_candle_time is timezone-aware
    if last_candle_time.tzinfo is None:
        last_candle_time = last_candle_time.replace(tzinfo=timezone.utc)
        
    now_utc = datetime.now(timezone.utc)
    if (now_utc - last_candle_time) > timedelta(hours=12):
        return _make_hold(f"Market appears to be closed (last tick was {(now_utc - last_candle_time).total_seconds() / 3600:.1f} hours ago). Holding until market opens.")

    last = intraday.iloc[-1]
    previous = intraday.iloc[-2]
    current_price = float(last["Close"] or snapshot.get("current_price") or 0.0)
    if current_price <= 0:
        return _make_hold("Current XAUUSD price is unavailable.")

    atr_value = float(last["atr14"])
    rsi_value = float(last["rsi14"])
    ema_fast = float(last["ema20"])

    # ── Volume analysis ────────────────────────────────────────────────
    volume_ratio = 1.0
    if "Volume" in intraday.columns:
        vol_series = intraday["Volume"].dropna()
        if len(vol_series) >= 20:
            avg_vol = float(vol_series.rolling(20).mean().iloc[-1])
            cur_vol = float(vol_series.iloc[-1])
            volume_ratio = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        elif len(vol_series) > 0:
            avg_vol = float(vol_series.mean())
            cur_vol = float(vol_series.iloc[-1])
            volume_ratio = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 1.0
    ema_slow = float(last["ema50"])
    levels = _build_levels(intraday, hourly, current_price)
    levels["volume_ratio"] = volume_ratio
    levels["atr"] = atr_value

    candle_high = float(last["High"])
    candle_low = float(last["Low"])
    candle_open = float(last["Open"])
    candle_close = float(last["Close"])
    candle_range = max(candle_high - candle_low, 0.01)
    lower_wick = min(candle_open, candle_close) - candle_low
    upper_wick = candle_high - max(candle_open, candle_close)

    trend_up = current_price > ema_fast > ema_slow
    trend_down = current_price < ema_fast < ema_slow
    near_support = abs(current_price - levels["support"]) <= atr_value * NEAR_LEVEL_ATR
    near_resistance = abs(current_price - levels["resistance"]) <= atr_value * NEAR_LEVEL_ATR
    bullish_rejection = candle_close > candle_open and lower_wick >= candle_range * 0.35
    bearish_rejection = candle_close < candle_open and upper_wick >= candle_range * 0.35
    bullish_breakout = (
        current_price > levels["resistance"] + atr_value * BREAKOUT_ATR
        and float(previous["Close"]) <= levels["resistance"]
        and trend_up
    )
    bearish_breakdown = (
        current_price < levels["support"] - atr_value * BREAKOUT_ATR
        and float(previous["Close"]) >= levels["support"]
        and trend_down
    )

    long_score = 0.0
    short_score = 0.0
    long_setup_name = "No setup"
    short_setup_name = "No setup"

    if trend_up:
        long_score += 28
    if 48 <= rsi_value <= 68:
        long_score += 12
    if candle_close > float(previous["High"]):
        long_score += 8
    if near_support and bullish_rejection:
        long_score += 30
        long_setup_name = "Support bounce"
    elif bullish_breakout:
        long_score += 30
        long_setup_name = "Resistance breakout"
    elif near_support and candle_close > ema_fast:
        long_score += 18
        long_setup_name = "Support retest"
    if atr_value >= 4.0:
        long_score += 6

    if trend_down:
        short_score += 28
    if 32 <= rsi_value <= 52:
        short_score += 12
    if candle_close < float(previous["Low"]):
        short_score += 8
    if near_resistance and bearish_rejection:
        short_score += 30
        short_setup_name = "Resistance rejection"
    elif bearish_breakdown:
        short_score += 30
        short_setup_name = "Support breakdown"
    elif near_resistance and candle_close < ema_fast:
        short_score += 18
        short_setup_name = "Resistance retest"
    if atr_value >= 4.0:
        short_score += 6

    if long_score < SETUP_THRESHOLD and short_score < SETUP_THRESHOLD:
        reason = (
            f"No clean XAUUSD setup. Long score {long_score:.0f}, short score {short_score:.0f}. "
            f"Support {levels['support']:.2f}, resistance {levels['resistance']:.2f}, "
            f"EMA20 {ema_fast:.2f}, EMA50 {ema_slow:.2f}, RSI14 {rsi_value:.1f}, ATR14 {atr_value:.2f}."
        )
        return _make_hold(reason, entry_price=current_price, levels=levels)

    direction = "BUY" if long_score >= short_score else "SELL"
    setup_name = long_setup_name if direction == "BUY" else short_setup_name
    score = long_score if direction == "BUY" else short_score

    if direction == "BUY":
        is_breakout = setup_name == "Resistance breakout"
        stop_loss = min(candle_low, levels["support"]) - atr_value * STOP_BUFFER_ATR
        risk = current_price - stop_loss
        take_profit = current_price + risk * (BREAKOUT_RR if is_breakout else BOUNCE_RR)
        level_cap = levels["day_high"] - atr_value * 0.1
        if level_cap > current_price:
            take_profit = min(take_profit, level_cap) if not is_breakout else max(take_profit, level_cap)
    else:
        is_breakout = setup_name == "Support breakdown"
        stop_loss = max(candle_high, levels["resistance"]) + atr_value * STOP_BUFFER_ATR
        risk = stop_loss - current_price
        take_profit = current_price - risk * (BREAKOUT_RR if is_breakout else BOUNCE_RR)
        level_floor = levels["day_low"] + atr_value * 0.1
        if level_floor < current_price:
            take_profit = max(take_profit, level_floor) if not is_breakout else min(take_profit, level_floor)

    if risk <= 0:
        return _make_hold("XAUUSD setup invalid because the stop distance is not positive.", entry_price=current_price, levels=levels)

    rr_ratio = abs(take_profit - current_price) / risk
    if rr_ratio < 1.15:
        return _make_hold(
            f"XAUUSD setup rejected because reward-to-risk is too small ({rr_ratio:.2f}).",
            entry_price=current_price,
            levels=levels,
        )

    stop_loss = _round_price(stop_loss)
    take_profit = _round_price(take_profit)
    reason = _build_reason(
        setup_name=setup_name,
        direction=direction,
        score=score,
        entry=_round_price(current_price),
        stop_loss=stop_loss,
        take_profit=take_profit,
        levels=levels,
        rsi_value=rsi_value,
        atr_value=atr_value,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        volume_ratio=volume_ratio,
    )
    confidence = min(0.92, max(0.68, score / 100.0))

    return TradeSignal(
        ticker=TICKER,
        direction=direction,
        confidence=round(confidence, 3),
        sentiment_score=round(confidence if direction == "BUY" else -confidence, 3),
        reasoning=reason,
        raw_report=reason,
        strategy_name="xauusd_levels",
        entry_price=_round_price(current_price),
        stop_loss=stop_loss,
        take_profit=take_profit,
        setup_score=round(score, 1),
        levels=levels,
    )
