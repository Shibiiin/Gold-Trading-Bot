import yfinance as yf
import pandas as pd

print("Fetching last 6 months of XAUUSD (GC=F) data...")
gold = yf.Ticker("GC=F")

# Daily data for macro volatility
hist_daily = gold.history(period="6mo", interval="1d")
if not hist_daily.empty:
    hist_daily['Range'] = hist_daily['High'] - hist_daily['Low']
    hist_daily['Body'] = abs(hist_daily['Close'] - hist_daily['Open'])
    
    print("\n--- DAILY VOLATILITY (Last 6 Months) ---")
    print(f"Average Daily Range (High to Low): ${hist_daily['Range'].mean():.2f}")
    print(f"Median Daily Range: ${hist_daily['Range'].median():.2f}")
    print(f"Max Daily Range: ${hist_daily['Range'].max():.2f}")
    print(f"Average Daily Body (Open to Close): ${hist_daily['Body'].mean():.2f}")

# 15m data for intraday strategy parameters (limit is 60d for intraday in yfinance)
hist_15m = gold.history(period="60d", interval="15m")
if not hist_15m.empty:
    hist_15m['Range'] = hist_15m['High'] - hist_15m['Low']
    hist_15m['Prev_Close'] = hist_15m['Close'].shift(1)
    hist_15m['TR1'] = hist_15m['Range']
    hist_15m['TR2'] = abs(hist_15m['High'] - hist_15m['Prev_Close'])
    hist_15m['TR3'] = abs(hist_15m['Low'] - hist_15m['Prev_Close'])
    hist_15m['TR'] = hist_15m[['TR1', 'TR2', 'TR3']].max(axis=1)
    
    print("\n--- INTRADAY 15m VOLATILITY (Last 60 Days) ---")
    print(f"Average 15m Candle Range: ${hist_15m['Range'].mean():.2f}")
    print(f"Average 15m True Range (ATR Proxy): ${hist_15m['TR'].mean():.2f}")
    print(f"95th Percentile 15m Move: ${hist_15m['TR'].quantile(0.95):.2f}")
