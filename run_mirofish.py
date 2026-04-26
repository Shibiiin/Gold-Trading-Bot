#!/usr/bin/env python3
"""MiroFish XAUUSD Trading System — Unified Launcher

Starts the signal server (Flask dashboard + API) and trading agent together.

Usage:
    python run_mirofish.py                       # dry-run, scan every 60s
    python run_mirofish.py --live                 # live trading via MT5 REST
    python run_mirofish.py --interval 120         # scan every 120s
    python run_mirofish.py --live --interval 90   # live, 90s intervals

Dashboard:  http://localhost:8080/journal
API:        http://localhost:8080/api/journal/entries
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _start_signal_server(port: int) -> None:
    """Start the Flask signal server in a daemon thread."""
    from trading.signal_server import app

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def _run_agent_loop(interval: int, dry_run: bool, engine: str) -> None:
    """Run the trading agent in a loop."""
    import trading_agent

    trading_agent.DRY_RUN = dry_run
    trading_agent.SIGNAL_ENGINE = engine

    ticker = trading_agent.TICKER

    while True:
        try:
            trading_agent.process_ticker(ticker)
        except Exception as exc:
            print(f"Error: {exc}")

        if interval <= 0:
            break
        print(f"\n⏳ Next scan in {interval}s...\n")
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MiroFish XAUUSD Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run_mirofish.py                  # dry-run, 60s loop\n"
            "  python run_mirofish.py --live            # live trading\n"
            "  python run_mirofish.py --interval 120    # 120s between scans\n"
        ),
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Enable live trading (default: dry-run with MT5 skip)",
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="Seconds between scans (default: 60)",
    )
    parser.add_argument(
        "--port", type=int, default=8080,
        help="Dashboard / API port (default: 8080)",
    )
    parser.add_argument(
        "--engine",
        choices=["dedicated", "hybrid", "mirofish"],
        default="dedicated",
        help="Signal engine mode (default: dedicated)",
    )
    args = parser.parse_args()

    # Configure MT5 mode based on --live flag
    if args.live:
        os.environ["MT5_MODE"] = "rest"
    else:
        os.environ["MT5_MODE"] = "skip"

    mode_label = "LIVE" if args.live else "DRY-RUN"

    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║           🐟  MiroFish XAUUSD Trading System             ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f"║  Mode:       {mode_label:<44} ║")
    print(f"║  Engine:     {args.engine:<44} ║")
    print(f"║  Interval:   {args.interval}s{'':<41}  ║")
    print(f"║  Dashboard:  http://localhost:{args.port}/journal{'':<17} ║")
    print(f"║  API:        http://localhost:{args.port}/api/journal/entries{'':<4} ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    if args.live:
        print("  🔴 LIVE MODE — real orders will be sent to MT5 signal server!")
    else:
        print("  🟡 DRY-RUN — setups will be analysed and logged but NOT executed.")
    print()

    # Start signal server in background thread
    server_thread = threading.Thread(
        target=_start_signal_server,
        args=(args.port,),
        daemon=True,
    )
    server_thread.start()
    time.sleep(1)  # Let the server start

    # Run agent in main thread
    try:
        _run_agent_loop(args.interval, not args.live, args.engine)
    except KeyboardInterrupt:
        print("\n\n🛑 MiroFish stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
