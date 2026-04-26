"""XAUUSD trading agent with setup-based execution and news blackout.

Runs in a loop, analysing XAUUSD setups and logging every decision
to the trade journal (trade_journal.json) so the live dashboard
always reflects the latest state.

Trade Basis (printed to terminal for every scan):
  • Technical setup — support/resistance levels, EMA crossover, RSI, ATR
  • Volume activity — current volume vs 20-period average
  • Dynamic risk    — SL (35-50 pips based on win rate), RR (1:2 or 1:3
                      based on volume), lot sizing per 1% risk rule
  • News blackout   — high-impact macro events pause trading
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

from trading.mt5_executor import connect, disconnect, place_order
from trading.mirofish_adapter import run_real_mirofish_report
from trading.seed_builder import build_seed_document, fetch_news
from trading.signal_parser import TradeSignal, parse_report
from trading.trade_decision import make_decision
from trading.xauusd_strategy import TICKER, analyze_xauusd_setup
from trading.journal_store import TradeJournalStore

PORTFOLIO_VALUE = float(os.getenv("PORTFOLIO_VALUE", "10000"))
DEFAULT_WATCHLIST = [TICKER]
DRY_RUN = False
SIGNAL_ENGINE = os.getenv("SIGNAL_ENGINE", "hybrid").strip().lower() or "hybrid"
MIROFISH_VETO_CONFIDENCE = float(os.getenv("MIROFISH_VETO_CONFIDENCE", "0.60"))
HIGH_IMPACT_LOOKBACK_HOURS = int(os.getenv("HIGH_IMPACT_LOOKBACK_HOURS", "12"))
HIGH_IMPACT_TERMS = (
    "fomc",
    "fed rate",
    "interest rate",
    "rate decision",
    "powell",
    "ecb",
    "boe",
    "boj",
    "nonfarm payroll",
    "nfp",
    "cpi",
    "inflation",
    "ppi",
    "gdp",
    "unemployment",
    "jobless claims",
    "retail sales",
    "pmi",
    "central bank",
    "treasury yields",
    "us dollar",
    "dollar index",
    "war",
    "geopolitical",
    "tariff",
    "sanction",
)

# Module-level journal for direct logging
_journal = TradeJournalStore()


def _engine_mode() -> str:
    mode = SIGNAL_ENGINE.strip().lower()
    if mode not in {"dedicated", "hybrid", "mirofish"}:
        return "hybrid"
    return mode


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def detect_high_impact_news(ticker: str = TICKER) -> list[dict]:
    """Return recent articles that imply macro or event-risk volatility."""
    lookback_start = datetime.now(timezone.utc) - timedelta(hours=HIGH_IMPACT_LOOKBACK_HOURS)
    matches: list[dict] = []

    for article in fetch_news(ticker):
        published_at = _parse_published_at(str(article.get("publishedAt", "")))
        if published_at is not None and published_at < lookback_start:
            continue

        haystack = " ".join(
            [
                str(article.get("title", "")),
                str(article.get("description", "")),
                str(article.get("content", "")),
            ]
        ).lower()
        if any(term in haystack for term in HIGH_IMPACT_TERMS):
            matches.append(article)

    return matches


def _normalize_tickers(raw_tickers: list[str]) -> list[str]:
    tickers = [str(ticker).upper().strip() for ticker in raw_tickers if str(ticker).strip()]
    if tickers and any(ticker != TICKER for ticker in tickers):
        print("Only XAUUSD is enabled. Ignoring non-XAUUSD symbols.")
    return [TICKER]


def _mirofish_query(ticker: str) -> str:
    return (
        f"Analyze {ticker} for the next 6-24 hours and return one directional trading verdict. "
        "Your answer must include `Direction: BUY`, `Direction: SELL`, or `Direction: HOLD`, "
        "and also include `Confidence: NN%`. Focus on macro sentiment, crowd behavior, risk events, "
        "US dollar dynamics, treasury yields, and gold-specific flows."
    )


def _hold_from_signal(base_signal: TradeSignal, reason: str, strategy_name: str, raw_report: str = "") -> TradeSignal:
    return replace(
        base_signal,
        direction="HOLD",
        confidence=0.0,
        sentiment_score=0.0,
        reasoning=reason,
        raw_report=raw_report or reason,
        strategy_name=strategy_name,
    )


def _merge_signal_with_mirofish(base_signal: TradeSignal) -> TradeSignal:
    mode = _engine_mode()
    if mode == "dedicated" or base_signal.direction == "HOLD":
        return replace(base_signal, strategy_name=f"{base_signal.strategy_name or 'xauusd_levels'}:{mode}")

    try:
        report_text = run_real_mirofish_report(
            seed_text=build_seed_document(base_signal.ticker),
            simulation_requirement=_mirofish_query(base_signal.ticker),
            project_name=f"{base_signal.ticker} Trading Analysis",
        )
    except Exception as exc:
        if mode == "mirofish":
            return _hold_from_signal(
                base_signal,
                f"MiroFish mode required backend confirmation, but the real backend failed: {exc}",
                strategy_name="mirofish_required",
            )
        return replace(
            base_signal,
            reasoning=f"{base_signal.reasoning} MiroFish backend unavailable, kept dedicated setup only: {exc}",
            strategy_name=f"{base_signal.strategy_name or 'xauusd_levels'}:dedicated_fallback",
        )

    miro_signal = parse_report(base_signal.ticker, report_text)

    if miro_signal.direction == base_signal.direction and miro_signal.direction in {"BUY", "SELL"}:
        return replace(
            base_signal,
            confidence=round(min(0.95, max(base_signal.confidence, miro_signal.confidence)), 3),
            sentiment_score=round(
                min(0.95, max(abs(base_signal.sentiment_score), abs(miro_signal.sentiment_score))) *
                (1 if base_signal.direction == "BUY" else -1),
                3,
            ),
            reasoning=(
                f"{base_signal.reasoning} MiroFish confirmed {miro_signal.direction} "
                f"with confidence {miro_signal.confidence:.0%}. {miro_signal.reasoning}"
            ),
            raw_report=report_text,
            strategy_name=f"{base_signal.strategy_name or 'xauusd_levels'}+mirofish_confirmed",
            setup_score=round(min(100.0, base_signal.setup_score + 8.0), 1),
        )

    if miro_signal.direction in {"BUY", "SELL"} and miro_signal.direction != base_signal.direction:
        if miro_signal.confidence >= MIROFISH_VETO_CONFIDENCE or mode == "mirofish":
            return _hold_from_signal(
                base_signal,
                (
                    f"Dedicated {base_signal.direction} setup was vetoed by MiroFish, which returned "
                    f"{miro_signal.direction} at {miro_signal.confidence:.0%}. "
                    f"Technical reason: {base_signal.reasoning} MiroFish reason: {miro_signal.reasoning}"
                ),
                strategy_name="hybrid_veto",
                raw_report=report_text,
            )
        return replace(
            base_signal,
            confidence=round(max(0.65, base_signal.confidence - 0.05), 3),
            reasoning=(
                f"{base_signal.reasoning} MiroFish leaned {miro_signal.direction} "
                f"at only {miro_signal.confidence:.0%}, so the dedicated setup was kept."
            ),
            raw_report=report_text,
            strategy_name=f"{base_signal.strategy_name or 'xauusd_levels'}+mirofish_soft_disagree",
        )

    if mode == "mirofish":
        return _hold_from_signal(
            base_signal,
            f"MiroFish returned HOLD/neutral, so no trade was taken. {miro_signal.reasoning}",
            strategy_name="mirofish_neutral",
            raw_report=report_text,
        )

    return replace(
        base_signal,
        confidence=round(max(0.64, base_signal.confidence - 0.02), 3),
        reasoning=f"{base_signal.reasoning} MiroFish was neutral, so the trade remained technical-led.",
        raw_report=report_text,
        strategy_name=f"{base_signal.strategy_name or 'xauusd_levels'}+mirofish_neutral",
    )


def _print_trade_basis(signal: TradeSignal) -> None:
    """Print a clear, human-readable explanation of the trade basis."""
    levels = signal.levels or {}
    vol_ratio = levels.get("volume_ratio", 1.0)
    vol_label = "🔥 ACTIVE" if vol_ratio >= 1.5 else "📊 Normal"

    print(f"\n  ┌─────────────────────────────────────────────────────────")
    print(f"  │ 📈 TRADE BASIS — {signal.ticker}")
    print(f"  ├─────────────────────────────────────────────────────────")
    print(f"  │ Direction:    {signal.direction}  (confidence {signal.confidence:.0%})")
    print(f"  │ Strategy:     {signal.strategy_name or 'xauusd_levels'}")
    print(f"  │ Setup Score:  {signal.setup_score:.0f}/100")
    print(f"  │ Entry:        ${signal.entry_price or 0:.2f}")

    if levels.get("support"):
        print(f"  │ Support:      ${levels['support']:.2f}")
    if levels.get("resistance"):
        print(f"  │ Resistance:   ${levels['resistance']:.2f}")

    print(f"  │ Volume:       {vol_label} ({vol_ratio:.1f}x avg)")
    print(f"  │ Engine:       {_engine_mode()}")
    print(f"  ├─────────────────────────────────────────────────────────")
    print(f"  │ Reasoning: {signal.reasoning[:200]}")
    print(f"  └─────────────────────────────────────────────────────────\n")


def _print_order_details(order) -> None:
    """Print the final order details after risk management."""
    if order.action == "SKIP":
        print(f"  ⏭️  SKIP: {order.reason}")
        return

    icon = "🟢" if order.action == "BUY" else "🔴"
    print(f"\n  ┌─────────────────────────────────────────────────────────")
    print(f"  │ {icon} ORDER: {order.action} {order.ticker}")
    print(f"  ├─────────────────────────────────────────────────────────")
    print(f"  │ Entry:      ${order.entry_price:.2f}")
    print(f"  │ Stop Loss:  ${order.stop_loss:.2f}  ({order.sl_pips:.0f} pips)")
    print(f"  │ Take Profit:${order.take_profit:.2f}  ({order.tp_pips:.0f} pips)")
    print(f"  │ RR Ratio:   1:{order.rr_ratio:.0f}")
    print(f"  │ Lot Size:   {order.quantity:.2f}")
    print(f"  │ Confidence:  {order.confidence:.0%}")
    if hasattr(order, 'trade_basis') and order.trade_basis:
        print(f"  │ Basis:      {order.trade_basis}")
    print(f"  └─────────────────────────────────────────────────────────\n")


def _log_to_journal(order, signal: TradeSignal) -> None:
    """Log every trade decision to the journal (including skips and dry-runs)."""
    try:
        payload = {
            "ticker": order.ticker,
            "action": order.action,
            "confidence": order.confidence,
            "entry_price": order.entry_price,
            "sl": order.stop_loss,
            "tp": order.take_profit,
            "lot": order.quantity,
            "reason": order.reason,
            "strategy_name": order.strategy_name or signal.strategy_name,
            "setup_score": order.setup_score or signal.setup_score,
            "levels": order.levels or signal.levels or {},
            "rr_ratio": order.rr_ratio,
            "sl_pips": order.sl_pips,
            "tp_pips": order.tp_pips,
        }
        # Add dynamic risk info to the reason for dashboard display
        if hasattr(order, 'trade_basis') and order.trade_basis:
            payload["reason"] = f"{order.reason} [{order.trade_basis}]"

        _journal.register_signal(payload)
    except Exception as exc:
        print(f"  ⚠️  Journal logging failed: {exc}")


def process_ticker(ticker: str) -> None:
    """Run the level-based XAUUSD strategy for a single pass."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  🔍 SCANNING {ticker} — {now}")
    print(f"{'='*60}")

    high_impact_articles = detect_high_impact_news(ticker)
    if high_impact_articles:
        top_titles = ", ".join((article.get("title") or "untitled") for article in high_impact_articles[:2])
        print(
            f"  ⚠️  Skipping {ticker}: high-impact news blackout active "
            f"({len(high_impact_articles)} article(s): {top_titles})"
        )
        return

    signal = _merge_signal_with_mirofish(analyze_xauusd_setup())

    # Print clear trade basis
    _print_trade_basis(signal)

    order = make_decision(signal, signal.entry_price or 0.0, PORTFOLIO_VALUE)

    # Print order details
    _print_order_details(order)

    # Always log to journal (even in dry-run)
    if order.action != "SKIP":
        _log_to_journal(order, signal)

    if DRY_RUN or os.getenv("MT5_MODE", "rest").lower() == "skip":
        if order.action != "SKIP":
            print("  📋 [DRY-RUN] Order logged to journal but NOT executed on MT5")
        return

    result = place_order(order)
    print(result)


def main():
    current_engine = _engine_mode()
    parser = argparse.ArgumentParser(description="XAUUSD trading agent for MT5")
    parser.add_argument("--loop", type=int, default=0, help="seconds between runs, 0 = run once")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_WATCHLIST,
        help="kept for compatibility; only XAUUSD is traded",
    )
    parser.add_argument(
        "--mt5",
        choices=["windows", "linux", "rest", "skip"],
        default="rest",
        help="MT5 integration mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="evaluate setups but do not execute orders",
    )
    parser.add_argument(
        "--signal-engine",
        choices=["dedicated", "hybrid", "mirofish"],
        default=current_engine,
        help="dedicated technical engine, hybrid with MiroFish confirmation, or MiroFish-required mode",
    )
    args = parser.parse_args()

    global DRY_RUN, SIGNAL_ENGINE
    DRY_RUN = args.dry_run
    os.environ["MT5_MODE"] = args.mt5
    SIGNAL_ENGINE = args.signal_engine

    tickers = _normalize_tickers(args.tickers)

    connected = True
    if args.mt5 != "skip":
        connected = connect()
        if not connected:
            raise SystemExit(1)

    try:
        while True:
            for ticker in tickers:
                try:
                    process_ticker(ticker)
                except Exception as exc:
                    print(f"Error on {ticker}: {exc}")

            if args.loop <= 0:
                break

            print(f"\n⏳ Sleeping {args.loop}s...")
            time.sleep(args.loop)
    finally:
        if connected:
            disconnect()


if __name__ == "__main__":
    main()
