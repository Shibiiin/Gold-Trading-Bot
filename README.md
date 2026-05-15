# 🐟 GoldBot — XAUUSD Trading Agent

GoldBot is a fully automated, algorithmic trading agent built exclusively for trading **Gold (XAUUSD)** on MetaTrader 5 (MT5). It is designed to act like a disciplined institutional trader, combining technical analysis, dynamic risk management, and live news monitoring.

## 🚀 Key Features

- **Algorithmic Setup Scoring:** Analyzes the 15M and 1H timeframes using EMA Crossovers, RSI, ATR, and strict Price Action patterns (Bounce, Breakout, Rejection, Breakdown). It only takes trades that score >= 68/100.
- **Dynamic Stop Loss (Volatility-Based):** Abandons fixed stop losses. Uses live ATR (Average True Range) to dynamically calculate a stop loss based on market volatility, expanding during heavy volume and tightening when the market slows down.
- **Dynamic Take Profit:** Adjusts the Reward-to-Risk (RR) ratio automatically. Uses 1:2 RR in normal markets, and extends to 1:3 RR during high-volume pushes.
- **Live News Blackout:** Connects to live news feeds to detect high-impact fundamental events (e.g., FOMC, CPI, NFP). Automatically halts all trading to protect capital from extreme slippage.
- **Smart Trailing Stops:** The MT5 Expert Advisor natively trails profits tick-by-tick once a trade reaches +35 pips in profit, locking in gains.
- **Mobile Live Dashboard:** Features a beautiful, mobile-friendly live journaling web application that securely tunnels via LocalTunnel to let you monitor your trades, win-rates, and live signals from your phone anywhere in the world.

## 🛠 Prerequisites

- **MetaTrader 5 (MT5)** installed and logged into your broker.
- **Python 3.10+** (macOS/Windows)
- **Node.js & npm** (for tunneling the live dashboard)

## 📦 Installation & Setup

1. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   npm install
   ```

2. **Configure MT5:**
   - Open MT5 > Tools > Options > Expert Advisors.
   - Check **"Allow WebRequest for listed URL"** and add `http://127.0.0.1:8080`.
   - Open MetaEditor, copy the code from `trading/GoldBotEA.mq5`, compile it, and attach it to an **XAUUSD** chart.
   - Ensure `EnableTrading` is set to `true` in the EA inputs.

## 🚦 How to Run the Bot

To launch both the Python trading agent and the mobile-tunnel dashboard simultaneously, run:

```bash
npm run dev
```

The terminal will print out a secure `https://...loca.lt/journal` link. Open this on your mobile phone to watch the bot trade in real-time!

## 🔐 Risk Warning

_Trading foreign exchange and commodities on margin carries a high level of risk. This software is provided for educational and experimental purposes. Always use a demo account before risking real capital._
