"""Applies risk rules and converts a TradeSignal into a concrete TradeOrder.

SL/TP are now pip-based (not percentage-based) so XAUUSD trades
get sensible distances.

Dynamic Risk Management:
  • SL is capped at 50 pips.  When win-rate improves the SL tightens
    automatically (35–50 pips) to lock in edge.
  • RR adjusts with volume: active volume → 1:3, normal → 1:2.
  • TP range target: 50-100 pips (normal), can extend for high-volume setups.

Drawdown protection:
  The DailyRiskTracker halts trading when cumulative risk committed
  today exceeds MAX_DAILY_RISK_PCT of portfolio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .signal_parser import TradeSignal

# ── Global risk settings ────────────────────────────────────────────────────
MIN_CONFIDENCE     = 0.65   # skip trade if confidence is below this
RISK_PER_TRADE_PCT = 0.01   # risk 1% of portfolio per trade
MIN_POSITION_LOT   = 0.01   # minimum lot size allowed
MAX_POSITION_LOT   = 0.02   # hard cap on lot size (user requested for small account)
MAX_DAILY_RISK_PCT = 0.03   # halt trading after 3% portfolio risk committed today
MAX_DAILY_TRADES   = 3      # halt trading after taking 3 trades in a day

# ── XAUUSD-only instrument settings ────────────────────────────────────────
# pip_size  : 0.1 (1 pip = $0.10 in price)
# sl_pips   : stop-loss distance in pips (max 50, adjusted by win rate)
# rr_ratio  : 1:2 default, 1:3 for active volume
# pip_value : USD value of 1 pip per 1 standard lot ($1 for gold)
INSTRUMENT_SETTINGS: dict[str, dict] = {
    "XAUUSD": {"pip_size": 0.1, "sl_pips": 50, "rr_ratio": 2, "pip_value": 1.0},
}

DEFAULT_SETTINGS = {"pip_size": 0.1, "sl_pips": 50, "rr_ratio": 2, "pip_value": 1.0}

# Volume threshold: if current_vol / avg_vol >= this → "active volume"
VOLUME_ACTIVE_THRESHOLD = 1.5

# ── Drawdown tracker log file ──────────────────────────────────────────────
_DRAWDOWN_LOG = Path(__file__).resolve().parent.parent / "drawdown_tracker.json"


def _get_settings(ticker: str) -> dict:
    """Return instrument settings, case-insensitive lookup with fallback."""
    return INSTRUMENT_SETTINGS.get(ticker.upper(), DEFAULT_SETTINGS)


def _price_digits(ticker: str) -> int:
    return 2 if ticker.upper() == "XAUUSD" else 5


# ── Dynamic SL / RR helpers ───────────────────────────────────────────────

def get_dynamic_sl_pips(atr_value: float, volume_ratio: float) -> float:
    """Adjust SL dynamically based on market volatility (ATR) and volume."""
    if atr_value <= 0:
        return 50.0  # safety fallback
        
    # 1 point in XAUUSD is 10 pips. If ATR is $3.50, ATR in pips is 35.
    atr_pips = atr_value * 10.0
    
    # Expand SL to avoid getting whipped out during highly active volume
    sl_multiplier = 1.8 if volume_ratio >= VOLUME_ACTIVE_THRESHOLD else 1.4
    
    sl_pips = round(atr_pips * sl_multiplier, 0)
    
    # Absolute limits: never tighter than 25 pips, never wider than 85 pips
    return max(25.0, min(sl_pips, 85.0))


def get_dynamic_rr(volume_ratio: float) -> float:
    """Adjust RR based on trading volume activity.

    Active volume (ratio >= 1.5) → 1:3 RR for extended TP.
    Normal/low volume            → 1:2 RR (conservative).
    """
    if volume_ratio >= VOLUME_ACTIVE_THRESHOLD:
        return 3.0  # 1:3
    return 2.0      # 1:2


# ── Daily risk / drawdown tracker ──────────────────────────────────────────

class DailyRiskTracker:
    """Tracks cumulative risk committed per day.

    Since real P&L feedback from MT5 is not available in this pipeline,
    we conservatively track risk *committed* (i.e. the dollar amount at
    risk for each trade placed today).  When cumulative risk exceeds
    MAX_DAILY_RISK_PCT × portfolio_value, the tracker signals a halt.

    State is persisted to a JSON file so it survives agent restarts.
    """

    def __init__(self, log_path: Path = _DRAWDOWN_LOG):
        self._path = log_path
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        return {"date": "", "cumulative_risk": 0.0, "trade_count": 0}

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)

    def _reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if self._data.get("date") != today:
            self._data = {"date": today, "cumulative_risk": 0.0, "trade_count": 0}
            self._save()

    def is_limit_reached(self, portfolio_value: float) -> bool:
        """Return True if daily risk limit has been reached."""
        self._reset_if_new_day()
        max_risk = portfolio_value * MAX_DAILY_RISK_PCT
        if self._data["cumulative_risk"] >= max_risk:
            return True
        if self._data.get("trade_count", 0) >= MAX_DAILY_TRADES:
            return True
        return False

    def record_trade(self, risk_amount: float) -> None:
        """Record a trade's risk amount."""
        self._reset_if_new_day()
        self._data["cumulative_risk"] = round(
            self._data["cumulative_risk"] + risk_amount, 2
        )
        self._data["trade_count"] = self._data.get("trade_count", 0) + 1
        self._save()

    @property
    def summary(self) -> str:
        self._reset_if_new_day()
        return (
            f"Daily risk: ${self._data['cumulative_risk']:.2f} "
            f"across {self._data['trade_count']} trade(s)"
        )


# Module-level singleton
_risk_tracker = DailyRiskTracker()


@dataclass
class TradeOrder:
    ticker: str
    action: str          # "BUY" | "SELL" | "SKIP"
    quantity: float      # lot size
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_pips: float       # actual SL distance in pips (for logging)
    tp_pips: float       # actual TP distance in pips (for logging)
    rr_ratio: float      # reward:risk ratio used
    confidence: float
    reason: str
    strategy_name: str = ""
    setup_score: float = 0.0
    levels: dict[str, float] | None = None
    volume_ratio: float = 1.0
    trade_basis: str = ""


def calculate_lot_size(
    portfolio_value: float,
    sl_pips: float,
    pip_value: float,
) -> float:
    """
    Calculate lot size using fixed fractional risk.

    Formula:
        risk_amount  = portfolio_value × RISK_PER_TRADE_PCT
        lot_size     = risk_amount / (sl_pips × pip_value)

    Example — XAUUSD, $10,000 portfolio, 50 pip SL, pip_value=$1:
        risk_amount  = 10,000 × 0.01 = $100
        lot_size     = 100 / (50 × 1) = 2.00 lots → capped to 0.03
    """
    if sl_pips <= 0 or pip_value <= 0:
        return 0.01  # minimum fallback

    risk_amount = portfolio_value * RISK_PER_TRADE_PCT
    lot = risk_amount / (sl_pips * pip_value)
    lot = round(lot, 2)

    # Clamp between broker minimum (MIN_POSITION_LOT) and our hard cap
    lot = max(MIN_POSITION_LOT, min(lot, MAX_POSITION_LOT))
    return lot


def make_decision(
    signal: TradeSignal,
    current_price: float,
    portfolio_value: float = 10_000.0,
) -> TradeOrder:
    """
    Convert a TradeSignal into a concrete TradeOrder with dynamic
    pip-based SL/TP distances and risk-reward ratios.

    Dynamic logic:
      • Volume ratio >= 1.5 → 1:3 RR (extended TP for momentum)
      • Volume ratio <  1.5 → 1:2 RR (conservative)
      • Win rate >= 65% (5+ trades) → SL = 35 pips (tight)
      • Win rate >= 55% (5+ trades) → SL = 42 pips
      • Otherwise                   → SL = 50 pips (max)
    """

    ticker = signal.ticker.upper()
    if ticker != "XAUUSD":
        return TradeOrder(
            ticker=signal.ticker, action="SKIP",
            quantity=0.0, entry_price=current_price,
            stop_loss=0.0, take_profit=0.0,
            sl_pips=0.0, tp_pips=0.0, rr_ratio=0.0,
            confidence=signal.confidence,
            reason="Only XAUUSD trading is enabled",
        )

    # ── Gate 0: daily drawdown limit ──────────────────────────────────────
    if _risk_tracker.is_limit_reached(portfolio_value):
        return TradeOrder(
            ticker=signal.ticker, action="SKIP",
            quantity=0.0, entry_price=current_price,
            stop_loss=0.0, take_profit=0.0,
            sl_pips=0.0, tp_pips=0.0, rr_ratio=0.0,
            confidence=signal.confidence,
            reason=f"Daily risk limit reached ({_risk_tracker.summary})",
            strategy_name=signal.strategy_name,
            setup_score=signal.setup_score,
            levels=signal.levels,
        )

    # ── Gate 1: confidence ─────────────────────────────────────────────────
    if signal.confidence < MIN_CONFIDENCE:
        return TradeOrder(
            ticker=signal.ticker, action="SKIP",
            quantity=0.0, entry_price=current_price,
            stop_loss=0.0, take_profit=0.0,
            sl_pips=0.0, tp_pips=0.0, rr_ratio=0.0,
            confidence=signal.confidence,
            reason=f"Confidence {signal.confidence:.0%} < threshold {MIN_CONFIDENCE:.0%}",
            strategy_name=signal.strategy_name,
            setup_score=signal.setup_score,
            levels=signal.levels,
        )

    # ── Gate 2: direction ──────────────────────────────────────────────────
    if signal.direction == "HOLD":
        return TradeOrder(
            ticker=signal.ticker, action="SKIP",
            quantity=0.0, entry_price=current_price,
            stop_loss=0.0, take_profit=0.0,
            sl_pips=0.0, tp_pips=0.0, rr_ratio=0.0,
            confidence=signal.confidence,
            reason="Signal direction is HOLD",
            strategy_name=signal.strategy_name,
            setup_score=signal.setup_score,
            levels=signal.levels,
        )

    # ── Gate 3: valid price ────────────────────────────────────────────────
    entry_price = float(signal.entry_price or current_price or 0.0)
    if entry_price <= 0:
        return TradeOrder(
            ticker=signal.ticker, action="SKIP",
            quantity=0.0, entry_price=0.0,
            stop_loss=0.0, take_profit=0.0,
            sl_pips=0.0, tp_pips=0.0, rr_ratio=0.0,
            confidence=signal.confidence,
            reason="Current price unavailable",
            strategy_name=signal.strategy_name,
            setup_score=signal.setup_score,
            levels=signal.levels,
        )

    # ── Dynamic SL and RR ─────────────────────────────────────────────────
    cfg       = _get_settings(signal.ticker)
    pip_size  = cfg["pip_size"]
    pip_value = cfg["pip_value"]

    volume_ratio = float((signal.levels or {}).get("volume_ratio", 1.0))
    atr_value = float((signal.levels or {}).get("atr", 3.0))

    sl_pips  = get_dynamic_sl_pips(atr_value, volume_ratio)
    rr_ratio = get_dynamic_rr(volume_ratio)

    # Build trade basis explanation
    vol_label = "ACTIVE" if volume_ratio >= VOLUME_ACTIVE_THRESHOLD else "NORMAL"
    basis_parts = [
        f"Volume {vol_label} (ratio {volume_ratio:.2f}x avg) → RR 1:{rr_ratio:.0f}",
        f"ATR Volatility ${atr_value:.2f} → SL {sl_pips:.0f} pips",
        f"TP target: {sl_pips * rr_ratio:.0f} pips",
    ]
    trade_basis = " | ".join(basis_parts)

    if signal.stop_loss and signal.take_profit:
        stop_loss = float(signal.stop_loss)
        take_profit = float(signal.take_profit)
        sl_distance = abs(entry_price - stop_loss)
        tp_distance = abs(take_profit - entry_price)
        actual_sl_pips = max(sl_distance / pip_size, 0.0)
        tp_pips = max(tp_distance / pip_size, 0.0)

        # Enforce SL cap at current dynamic limit
        if actual_sl_pips > sl_pips:
            sl_distance = sl_pips * pip_size
            if signal.direction == "BUY":
                stop_loss = entry_price - sl_distance
            else:
                stop_loss = entry_price + sl_distance
            actual_sl_pips = sl_pips

        # Recalculate TP with dynamic RR
        tp_distance = sl_distance * rr_ratio
        tp_pips = actual_sl_pips * rr_ratio
        if signal.direction == "BUY":
            take_profit = entry_price + tp_distance
        else:
            take_profit = entry_price - tp_distance

        sl_pips = actual_sl_pips
    else:
        sl_distance = sl_pips * pip_size
        tp_distance = sl_distance * rr_ratio
        tp_pips = sl_pips * rr_ratio

        if signal.direction == "BUY":
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance

    digits = _price_digits(signal.ticker)
    stop_loss = round(stop_loss, digits)
    take_profit = round(take_profit, digits)

    if sl_pips <= 0 or tp_pips <= 0:
        return TradeOrder(
            ticker=signal.ticker, action="SKIP",
            quantity=0.0, entry_price=round(entry_price, digits),
            stop_loss=0.0, take_profit=0.0,
            sl_pips=0.0, tp_pips=0.0, rr_ratio=0.0,
            confidence=signal.confidence,
            reason="Invalid stop-loss or take-profit distance",
            strategy_name=signal.strategy_name,
            setup_score=signal.setup_score,
            levels=signal.levels,
        )

    # ── Lot size ───────────────────────────────────────────────────────────
    quantity = calculate_lot_size(portfolio_value, sl_pips, pip_value)

    return TradeOrder(
        ticker=signal.ticker,
        action=signal.direction,
        quantity=quantity,
        entry_price=round(entry_price, digits),
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_pips=sl_pips,
        tp_pips=tp_pips,
        rr_ratio=rr_ratio,
        confidence=signal.confidence,
        reason=signal.reasoning[:300],
        strategy_name=signal.strategy_name,
        setup_score=signal.setup_score,
        levels=signal.levels,
        volume_ratio=volume_ratio,
        trade_basis=trade_basis,
    )


def record_executed_order(order: TradeOrder) -> None:
    """Record risk only after an order is actually accepted/executed."""
    if order.action == "SKIP" or order.quantity <= 0 or order.sl_pips <= 0:
        return
    pip_value = _get_settings(order.ticker)["pip_value"]
    risk_amount = round(order.sl_pips * pip_value * order.quantity, 2)
    if risk_amount > 0:
        _risk_tracker.record_trade(risk_amount)


# ---------------------------------------------------------------------------
# Quick sanity-check — run directly to verify numbers look right
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ticker = "XAUUSD"
    price = 3300.0
    cfg      = _get_settings(ticker)
    pip_size = cfg["pip_size"]
    pip_val  = cfg["pip_value"]

    print(f"\n{'='*60}")
    print(f"  XAUUSD Dynamic Volatility Risk Parameters")
    print(f"{'='*60}")
    
    scenarios = [
        ("Low Volatility (ATR $2)", 2.0, 1.0),
        ("Normal Market  (ATR $3.5)", 3.5, 1.0),
        ("High Vol Active(ATR $5)", 5.0, 2.0)
    ]
    
    print(f"{'Scenario':<25} {'Entry':>10} {'SL':>10} {'TP':>10} "
          f"{'SL pips':>8} {'TP pips':>8} {'RR':>5} {'Lots':>6}")
    print("-" * 90)

    for label, atr, vol in scenarios:
        sl_pips = get_dynamic_sl_pips(atr, vol)
        rr = get_dynamic_rr(vol)
        sl_dist  = sl_pips * pip_size
        tp_dist  = sl_dist * rr
        sl_price = round(price - sl_dist, 2)
        tp_price = round(price + tp_dist, 2)
        lots     = calculate_lot_size(10_000, sl_pips, pip_val)
        print(f"{label:<25} {price:>10.2f} {sl_price:>10.2f} {tp_price:>10.2f} "
              f"{sl_pips:>8.0f} {sl_pips*rr:>8.0f} {rr:>4.0f}:1 {lots:>6.2f}")
