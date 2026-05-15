# XAUUSD Dedicated Trading Setup (Status Document)

This document tracks the current completion state of the GoldBot Gold Trading project.

## ✅ Completed (Currently Active)

The system is currently running in **Dedicated Technical Analysis Mode**. This mode bypasses the LLM to provide lightning-fast, mathematically precise trading logic completely focused on Gold.

- **XAUUSD Specialization:** The script exclusively tracks Gold (`GC=F` / `XAUUSD`) using 15M (entry) and 1H (context) timeframe candles.
- **Dynamic Stop Loss:** Hardcoded SL is completely removed. Stop Losses are now dynamically sized based on live market volatility using the Average True Range (ATR). It shrinks during quiet markets and expands during heavy momentum.
- **Volume-Based Take Profit:** Reward-to-Risk (RR) logic is fully automated. If the current volume spikes >1.5x the average, it automatically targets a 1:3 RR. In normal conditions, it targets 1:2 RR.
- **Live News Blackout:** Integrated APIs that scan the web for major macroeconomic keywords (FOMC, CPI, Rate Cuts) and force the agent to skip trades during heavily volatile news hours.
- **Smart Trailing Stop:** A robust `ManageTrailingStop()` function is coded directly into the `GoldBotEA.mq5` file. Once a trade clears +35 pips in profit, MT5 automatically trails the price by 15 pips to lock in profits without needing the Python server.
- **Mobile Web Dashboard:** Deployed a beautiful `journal_dashboard.html` that shows real-time stats, win rates, and daily/weekly/monthly profit history. It is securely tunneled via LocalTunnel so the user can watch the trades from their phone.

## 🔜 Planned (Future Phases)

After allowing the Dedicated Technical Engine to log a week of baseline trade data, the following features will be activated and tested:

- **Phase 2 (Hybrid Mode):** Relaunching the script using `--engine hybrid`. This will allow the mathematically precise Technical Analysis to propose a setup, but will require the GPT-4o LLM (the AI Brain) to read global news and the DXY to give the final "Approval" before taking the trade.
- **Phase 3 (Full GoldBot AI Mode):** Testing `--engine goldbot`, where the LLM is given complete autonomy over market analysis, risk sizing, and trade selection.
- **VPS Deployment:** Moving the entire system from the local MacBook to a cheap $10/month Windows VPS to ensure true 24/5 uptime.

- **Weekly trading** For Week 1 (Technical Only): Stop your current terminal (Ctrl + C) and run: npm run dev:week1
  For Week 2 (Pure AI Mode): npm run dev:week2
  For Week 3 (Hybrid / Tech + AI): npm run dev:week3
