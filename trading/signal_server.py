"""Signal relay, execution journal, and dashboard for the MT5 bridge."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    from .journal_store import TradeJournalStore
except ImportError:
    from journal_store import TradeJournalStore

try:
    from flask import Flask, jsonify, request, send_file, redirect
except ModuleNotFoundError:
    class _MissingFlaskApp:
        def __init__(self):
            self.missing_dependency = "flask"

        def get(self, *_args, **_kwargs):
            def decorator(func):
                return func
            return decorator

        def post(self, *_args, **_kwargs):
            def decorator(func):
                return func
            return decorator

        def run(self, *_args, **_kwargs):
            raise RuntimeError("Flask is required to run trading.signal_server")

    app = _MissingFlaskApp()
    jsonify = lambda payload: payload
    request = None
    send_file = None
else:
    app = Flask(__name__)

_signals: dict[str, dict] = {}
_live_prices: dict[str, float] = {}
_lock = threading.Lock()
_journal = TradeJournalStore()
_dashboard_path = Path(__file__).resolve().with_name("journal_dashboard.html")

SIGNAL_TTL_SECONDS = 300  # 5 minutes


def _signal_response(record: dict) -> dict:
    return {
        "signal_id": record.get("signal_id", ""),
        "ticker": record.get("ticker", ""),
        "action": record.get("action", "SKIP"),
        "confidence": record.get("confidence", 0.0),
        "entry_price": record.get("entry_price", 0.0),
        "sl": record.get("sl", 0.0),
        "tp": record.get("tp", 0.0),
        "lot": record.get("lot", 0.0),
        "updated_at": record.get("updated_at", ""),
    }


def _is_expired(record: dict) -> bool:
    try:
        updated_at = datetime.fromisoformat(record["updated_at"])
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        return age > SIGNAL_TTL_SECONDS
    except (KeyError, ValueError):
        return True


def _mark_status(ticker: str, signal_id: str, status: str) -> None:
    with _lock:
        current = _signals.get(ticker.upper())
        if current and current.get("signal_id") == signal_id:
            current["status"] = status
            current["updated_at"] = datetime.now(timezone.utc).isoformat()
            if status == "closed":
                _signals.pop(ticker.upper(), None)


@app.post("/update")
def update_signal():
    if request is None:
        raise RuntimeError("Flask is required to handle requests")

    payload = request.get_json(silent=True) or {}
    ticker = str(payload.get("ticker", "")).upper().strip()
    if not ticker:
        return jsonify({"status": "error", "error": "ticker required"}), 400

    record = _journal.register_signal(payload)
    record["status"] = "signal_ready"
    with _lock:
        _signals[ticker] = record
    return jsonify({"status": "ok", "signal_id": record["signal_id"]})


@app.post("/execution/open")
def execution_open():
    if request is None:
        raise RuntimeError("Flask is required to handle requests")

    payload = request.get_json(silent=True) or {}
    signal_id = str(payload.get("signal_id", "")).strip()
    ticker = str(payload.get("ticker", "")).upper().strip()
    if not signal_id or not ticker:
        return jsonify({"status": "error", "error": "signal_id and ticker required"}), 400

    trade = _journal.mark_open(signal_id, payload)
    if trade is None:
        return jsonify({"status": "error", "error": "signal not found"}), 404

    print(f"\n🚀 [MT5] TRADE EXECUTED: {ticker} {trade.get('action')} @ {trade.get('entry_price')} (Signal: {signal_id})")
    _mark_status(ticker, signal_id, "open")
    return jsonify({"status": "ok", "signal_id": signal_id})


@app.post("/execution/close")
def execution_close():
    if request is None:
        raise RuntimeError("Flask is required to handle requests")

    payload = request.get_json(silent=True) or {}
    signal_id = str(payload.get("signal_id", "")).strip()
    ticker = str(payload.get("ticker", "")).upper().strip()
    if not signal_id or not ticker:
        return jsonify({"status": "error", "error": "signal_id and ticker required"}), 400

    trade = _journal.mark_close(signal_id, payload)
    if trade is None:
        return jsonify({"status": "error", "error": "signal not found"}), 404

    profit = trade.get('profit', 0)
    result = trade.get('result', 'unknown')
    emoji = '🟢' if result == 'win' else '🔴' if result == 'loss' else '⚪'
    print(f"\n{emoji} [MT5] TRADE CLOSED: {ticker} {result.upper()} P&L: ${profit:+.2f} (Signal: {signal_id})")

    _mark_status(ticker, signal_id, "closed")
    return jsonify({"status": "ok", "signal_id": signal_id})


@app.post("/price/update")
def price_update():
    if request is None:
        return jsonify({"status": "error"}), 400
    payload = request.get_json(silent=True) or {}
    ticker = str(payload.get("ticker", "")).upper().strip()
    price = float(payload.get("price", 0.0))
    if ticker and price > 0:
        with _lock:
            _live_prices[ticker] = price
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400


def get_live_broker_price(ticker: str) -> float | None:
    with _lock:
        return _live_prices.get(ticker.upper())


@app.get("/signal/")
def get_default_signal():
    return jsonify({"action": "SKIP", "reason": "no signal"})


@app.get("/signal/<ticker>")
def get_signal(ticker: str):
    with _lock:
        signal = _signals.get(ticker.upper())
    if not signal:
        return jsonify({"action": "SKIP", "reason": "no signal"})
    if signal.get("status") != "signal_ready":
        return jsonify({"action": "SKIP", "reason": f"signal {signal.get('status', 'inactive')}"})
    if _is_expired(signal):
        return jsonify({"action": "SKIP", "reason": "signal expired"})
    return jsonify(_signal_response(signal))


@app.get("/signals")
def get_signals():
    with _lock:
        active_signals = [
            _signal_response(signal)
            for signal in _signals.values()
            if signal.get("status") == "signal_ready" and not _is_expired(signal)
        ]
    return jsonify(active_signals)


@app.get("/api/journal/entries")
def get_journal_entries():
    limit = request.args.get("limit", 200, type=int) if request is not None else 200
    return jsonify({"entries": _journal.list_entries(limit=limit), "stats": _journal.stats()})


@app.get("/api/journal/stats")
def get_journal_stats():
    return jsonify(_journal.stats())


@app.get("/")
def index():
    return redirect("/journal")


@app.get("/journal")
def journal_dashboard():
    if send_file is None:
        raise RuntimeError("Flask is required to serve the journal dashboard")
    return send_file(_dashboard_path)


@app.get("/health")
def health():
    stats = _journal.stats()
    with _lock:
        total = len(_signals)
        active = sum(
            1
            for signal in _signals.values()
            if signal.get("status") == "signal_ready" and not _is_expired(signal)
        )
    return jsonify(
        {
            "status": "ok",
            "signals_total": total,
            "signals_active": active,
            "ttl_seconds": SIGNAL_TTL_SECONDS,
            "closed_trades": stats["closed_trades"],
            "win_rate": stats["win_rate"],
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
