"""Executes trades via MetaTrader 5 Python API or REST signal server."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .trade_decision import TradeOrder, record_executed_order

SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
}

mt5 = None


def _mode() -> str:
    return os.getenv("MT5_MODE", "rest").strip().lower() or "rest"


def _signal_server_url() -> str:
    return os.getenv("SIGNAL_SERVER_URL", "http://127.0.0.1:8080").rstrip("/")


def connect() -> bool:
    """Connect to MetaTrader or validate REST mode."""
    global mt5

    mode = _mode()
    if mode == "rest":
        print("REST mode — no MT5 connection needed")
        return True

    try:
        if mode == "windows":
            import MetaTrader5 as mt5_module
        elif mode == "linux":
            from mt5linux import MetaTrader5 as mt5_module
        else:
            print(f"Unsupported MT5 mode: {mode}")
            return False
    except Exception as exc:
        print(f"Failed to import MT5 client for mode {mode}: {exc}")
        return False

    mt5 = mt5_module
    host = os.getenv("MT5LINUX_HOST", "localhost")
    port = int(os.getenv("MT5LINUX_PORT", "18812"))

    try:
        initialized = (
            mt5.initialize(host=host, port=port)
            if mode == "linux"
            else mt5.initialize()
        )
    except TypeError:
        initialized = mt5.initialize()
    except Exception as exc:
        print(f"MT5 initialize failed: {exc}")
        return False

    if not initialized:
        print("MT5 initialize returned False")
        return False

    login = os.getenv("MT5_LOGIN", "").strip()
    if not login:
        return True

    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    try:
        ok = mt5.login(login=int(login), password=password, server=server)
    except TypeError:
        ok = mt5.login(int(login), password=password, server=server)
    except Exception as exc:
        print(f"MT5 login failed: {exc}")
        return False

    if not ok:
        print("MT5 login returned False")
    return bool(ok)


def disconnect():
    """Shutdown the active MT5 client when needed."""
    mode = _mode()
    if mode != "rest" and mt5 is not None:
        mt5.shutdown()


def get_current_price(symbol: str) -> tuple[float, float]:
    """Return the current bid and ask for a mapped MT5 symbol."""
    if mt5 is None:
        raise RuntimeError("MT5 is not connected")
    mt5_symbol = SYMBOL_MAP.get(symbol, symbol)
    tick = mt5.symbol_info_tick(mt5_symbol)
    if tick is None:
        raise RuntimeError(f"No tick data for {mt5_symbol}")
    return float(tick.bid), float(tick.ask)


def _log_trade(payload: dict) -> None:
    payload = dict(payload)
    payload["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open("trades.log", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def place_order(order: TradeOrder) -> dict:
    """Execute a trade order via REST relay or MT5 API."""
    mode = _mode()

    if order.action == "SKIP":
        print(order.reason)
        return {"status": "skipped", "reason": order.reason}

    if mode == "rest":
        import requests

        payload = {
            "ticker": order.ticker,
            "action": order.action,
            "confidence": order.confidence,
            "entry_price": order.entry_price,
            "sl": order.stop_loss,
            "tp": order.take_profit,
            "lot": order.quantity,
            "reason": order.reason,
            "strategy_name": order.strategy_name,
            "setup_score": order.setup_score,
            "levels": order.levels or {},
            "rr_ratio": order.rr_ratio,
            "sl_pips": order.sl_pips,
            "tp_pips": order.tp_pips,
        }
        response = requests.post(
            f"{_signal_server_url()}/update",
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    if mode not in ("windows", "linux") or mt5 is None:
        return {"status": "error", "error": f"MT5 unavailable for mode {mode}"}

    mt5_symbol = SYMBOL_MAP.get(order.ticker, order.ticker)
    if not mt5.symbol_select(mt5_symbol, True):
        return {"status": "error", "error": f"Unable to select symbol {mt5_symbol}"}

    bid, ask = get_current_price(order.ticker)
    is_buy = order.action == "BUY"
    price = ask if is_buy else bid
    symbol_info = mt5.symbol_info(mt5_symbol)
    if symbol_info is None:
        return {"status": "error", "error": f"Unable to fetch symbol info for {mt5_symbol}"}

    lot = max(float(symbol_info.volume_min), round(float(order.quantity), 2))
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": mt5_symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": order.stop_loss,
        "tp": order.take_profit,
        "deviation": 20,
        "magic": 20260418,
        "comment": f"MiroFish {order.confidence:.0%}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    result_dict = result._asdict() if hasattr(result, "_asdict") else {"result": str(result)}
    success_retcodes = {
        value
        for value in (
            getattr(mt5, "TRADE_RETCODE_DONE", None),
            getattr(mt5, "TRADE_RETCODE_PLACED", None),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", None),
        )
        if value is not None
    }
    if result_dict.get("retcode") in success_retcodes:
        record_executed_order(order)
    _log_trade(
        {
            "ticker": order.ticker,
            "action": order.action,
            "request": request,
            "result": result_dict,
            "reason": order.reason,
            "strategy_name": order.strategy_name,
            "setup_score": order.setup_score,
        }
    )
    return result_dict
