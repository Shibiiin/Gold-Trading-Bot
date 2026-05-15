# GoldBot — Automated XAUUSD Trading System

An automated, high-probability algorithmic trading system for Gold (XAUUSD) based on 3-Standard Deviation Mean Reversion and Smart Money Concepts.

## Features
- **Mean Reversion Strategy:** Engineered for high-probability Asian Session reversals.
- **Dynamic RR:** Adjusts Reward-to-Risk ratios (1:1 to 1:2+) based on volatility and momentum.
- **Risk Management:** Includes 2-consecutive-loss drawdown halting and news-event blackouts.
- **Remote Monitoring:** Integrated web dashboard for real-time trade journaling.

## Getting Started
1. **Requirements:** Python 3.11+, MetaTrader 5 (MT5).
2. **Setup:** Install dependencies in `backend/` and `frontend/`.
3. **Execution:** 
   ```bash
   python3 run_bot.py --live
   ```

## Disclaimer
Trading commodities on margin carries high risk. This software is for educational purposes.
