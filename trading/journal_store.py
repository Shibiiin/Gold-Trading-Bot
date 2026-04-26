"""Persistent trade journal storage for the local signal server."""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_PATH = Path(__file__).resolve().parent.parent / "trade_journal.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradeJournalStore:
    """JSON-backed journal for signals, executions, and outcomes."""

    def __init__(self, path: Path = JOURNAL_PATH):
        self._path = path
        self._lock = threading.Lock()

    def _default_data(self) -> dict:
        return {"version": 1, "trades": []}

    def _load_unlocked(self) -> dict:
        if not self._path.exists():
            return self._default_data()
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return self._default_data()
        if not isinstance(payload, dict):
            return self._default_data()
        payload.setdefault("version", 1)
        payload.setdefault("trades", [])
        if not isinstance(payload["trades"], list):
            payload["trades"] = []
        return payload

    def _save_unlocked(self, payload: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
        temp_path.replace(self._path)

    def _find_trade(self, trades: list[dict], signal_id: str) -> dict | None:
        return next((trade for trade in trades if trade.get("signal_id") == signal_id), None)

    def register_signal(self, payload: dict) -> dict:
        with self._lock:
            state = self._load_unlocked()
            signal_id = str(payload.get("signal_id") or f"sig_{uuid.uuid4().hex[:12]}")
            trade = self._find_trade(state["trades"], signal_id)
            now = _now()

            if trade is None:
                trade = {
                    "signal_id": signal_id,
                    "created_at": now,
                    "opened_at": None,
                    "closed_at": None,
                    "status": "signal_ready",
                    "result": "",
                    "close_price": None,
                    "profit": None,
                }
                state["trades"].insert(0, trade)

            trade.update(
                {
                    "ticker": str(payload.get("ticker", "")).upper(),
                    "action": str(payload.get("action", "SKIP")).upper(),
                    "confidence": float(payload.get("confidence", 0.0) or 0.0),
                    "entry_price": float(payload.get("entry_price", 0.0) or 0.0),
                    "sl": float(payload.get("sl", 0.0) or 0.0),
                    "tp": float(payload.get("tp", 0.0) or 0.0),
                    "lot": float(payload.get("lot", 0.0) or 0.0),
                    "rr_ratio": float(payload.get("rr_ratio", 0.0) or 0.0),
                    "sl_pips": float(payload.get("sl_pips", 0.0) or 0.0),
                    "tp_pips": float(payload.get("tp_pips", 0.0) or 0.0),
                    "reason": str(payload.get("reason", "") or ""),
                    "strategy_name": str(payload.get("strategy_name", "") or ""),
                    "setup_score": float(payload.get("setup_score", 0.0) or 0.0),
                    "levels": payload.get("levels") if isinstance(payload.get("levels"), dict) else {},
                    "updated_at": now,
                }
            )

            if trade.get("status") == "closed":
                trade["status"] = "signal_ready"
                trade["result"] = ""
                trade["opened_at"] = None
                trade["closed_at"] = None
                trade["close_price"] = None
                trade["profit"] = None

            self._save_unlocked(state)
            return deepcopy(trade)

    def mark_open(self, signal_id: str, payload: dict) -> dict | None:
        with self._lock:
            state = self._load_unlocked()
            trade = self._find_trade(state["trades"], signal_id)
            if trade is None:
                return None

            trade.update(
                {
                    "status": "open",
                    "opened_at": str(payload.get("opened_at") or _now()),
                    "updated_at": _now(),
                    "order_ticket": str(payload.get("order_ticket", "") or ""),
                    "deal_ticket": str(payload.get("deal_ticket", "") or ""),
                    "entry_price": float(payload.get("entry_price", trade.get("entry_price", 0.0)) or 0.0),
                    "lot": float(payload.get("lot", trade.get("lot", 0.0)) or 0.0),
                    "sl": float(payload.get("sl", trade.get("sl", 0.0)) or 0.0),
                    "tp": float(payload.get("tp", trade.get("tp", 0.0)) or 0.0),
                }
            )
            self._save_unlocked(state)
            return deepcopy(trade)

    def mark_close(self, signal_id: str, payload: dict) -> dict | None:
        with self._lock:
            state = self._load_unlocked()
            trade = self._find_trade(state["trades"], signal_id)
            if trade is None:
                return None

            profit = float(payload.get("profit", 0.0) or 0.0)
            result = str(payload.get("result", "") or "").lower()
            if result not in {"win", "loss", "breakeven"}:
                if profit > 0:
                    result = "win"
                elif profit < 0:
                    result = "loss"
                else:
                    result = "breakeven"

            trade.update(
                {
                    "status": "closed",
                    "result": result,
                    "profit": round(profit, 2),
                    "close_price": float(payload.get("close_price", 0.0) or 0.0),
                    "closed_at": str(payload.get("closed_at") or _now()),
                    "updated_at": _now(),
                    "close_deal_ticket": str(payload.get("deal_ticket", "") or ""),
                }
            )
            self._save_unlocked(state)
            return deepcopy(trade)

    def list_entries(self, limit: int = 200) -> list[dict]:
        with self._lock:
            state = self._load_unlocked()
            trades = state["trades"][: max(1, limit)]
            return deepcopy(trades)

    def stats(self) -> dict:
        with self._lock:
            state = self._load_unlocked()
            trades = state["trades"]

        closed = [trade for trade in trades if trade.get("status") == "closed"]
        wins = sum(1 for trade in closed if trade.get("result") == "win")
        losses = sum(1 for trade in closed if trade.get("result") == "loss")
        breakeven = sum(1 for trade in closed if trade.get("result") == "breakeven")
        closed_count = len(closed)

        return {
            "total_signals": len(trades),
            "open_trades": sum(1 for trade in trades if trade.get("status") == "open"),
            "pending_signals": sum(1 for trade in trades if trade.get("status") == "signal_ready"),
            "closed_trades": closed_count,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "win_rate": round((wins / closed_count) * 100.0, 2) if closed_count else 0.0,
            "total_profit": round(sum(float(trade.get("profit") or 0.0) for trade in closed), 2),
        }
