import yfinance as yf
import pandas as pd
import numpy as np

def _bollinger_bands(series, period: int = 20, num_std: float = 3.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma, sma + (std * num_std), sma - (std * num_std)

def _atr(frame, period: int = 14):
    prev_close = frame["Close"].shift(1)
    tr1 = frame["High"] - frame["Low"]
    tr2 = abs(frame["High"] - prev_close)
    tr3 = abs(frame["Low"] - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

def get_session(hour):
    if 0 <= hour < 8: return "Asian"
    elif 8 <= hour < 13: return "London"
    elif 13 <= hour < 21: return "New York"
    else: return "Late NY/Sydney"

timeframes = {
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d"  # 1h allows up to 2 years (730 days) of data
}

results = []

for tf, period in timeframes.items():
    print(f"\nFetching {period} of {tf} XAUUSD data...")
    try:
        df = yf.Ticker("GC=F").history(period=period, interval=tf)
        if df.empty:
            continue
    except Exception as e:
        print(f"Failed to fetch {tf}: {e}")
        continue
        
    df = df.dropna()
    df["atr14"] = _atr(df, 14)
    df["sma20"], df["upper3sd"], df["lower3sd"] = _bollinger_bands(df["Close"], 20, 3.0)
    df["Rolling_Low"] = df["Low"].rolling(32).min().shift(1)
    df["Rolling_High"] = df["High"].rolling(32).max().shift(1)
    df = df.dropna().reset_index()

    trades = []
    stop_buffer = 0.2
    rr = 1.0

    print(f"Processing {len(df)} candles for {tf}...")

    for i in range(1, len(df)-1):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        current_price = curr["Close"]
        atr = curr["atr14"]
        session = get_session(curr["Datetime"].hour)
        
        # 3SD Mean Reversion ONLY (Our best strategy)
        is_3sd_bullish = prev["Low"] < prev["lower3sd"] and curr["Close"] > curr["lower3sd"]
        is_3sd_bearish = prev["High"] > prev["upper3sd"] and curr["Close"] < curr["upper3sd"]
        
        trade = None
        if is_3sd_bullish:
            trade = {"type": "BUY", "entry": current_price, "sl": min(curr["Low"], curr["Rolling_Low"]) - atr * stop_buffer}
        elif is_3sd_bearish:
            trade = {"type": "SELL", "entry": current_price, "sl": max(curr["High"], curr["Rolling_High"]) + atr * stop_buffer}

        if trade:
            risk = abs(trade["entry"] - trade["sl"])
            if risk <= 0: continue
            
            if trade["type"] == "BUY":
                trade["tp"] = trade["entry"] + (risk * rr)
            else:
                trade["tp"] = trade["entry"] - (risk * rr)
                
            trade["session"] = session
            
            # Fast-forward to resolve trade
            for j in range(i+1, len(df)):
                fut = df.iloc[j]
                if trade["type"] == "BUY":
                    if fut["Low"] <= trade["sl"]:
                        trade["result"] = "LOSS"
                        trades.append(trade)
                        break
                    elif fut["High"] >= trade["tp"]:
                        trade["result"] = "WIN"
                        trades.append(trade)
                        break
                else:
                    if fut["High"] >= trade["sl"]:
                        trade["result"] = "LOSS"
                        trades.append(trade)
                        break
                    elif fut["Low"] <= trade["tp"]:
                        trade["result"] = "WIN"
                        trades.append(trade)
                        break

    df_t = pd.DataFrame(trades)
    if not df_t.empty:
        total = len(df_t)
        wins = len(df_t[df_t['result'] == 'WIN'])
        wr = (wins / total) * 100
        
        asian_t = df_t[df_t['session'] == 'Asian']
        asian_wr = 0
        if not asian_t.empty:
            asian_wins = len(asian_t[asian_t['result'] == 'WIN'])
            asian_wr = (asian_wins / len(asian_t)) * 100
            
        results.append({
            "Timeframe": tf,
            "Total_Trades": total,
            "Overall_WR": wr,
            "Asian_Trades": len(asian_t),
            "Asian_WR": asian_wr
        })

print("\n=== MULTI-TIMEFRAME BACKTEST RESULTS (RR 1.0, 3SD Mean Reversion) ===")
res_df = pd.DataFrame(results).sort_values(by="Asian_WR", ascending=False)
print(res_df.to_string(index=False))