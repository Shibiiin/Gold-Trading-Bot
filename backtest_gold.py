import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

def _ema(series, span: int):
    return series.ewm(span=span, adjust=False).mean()

def _rsi(series, period: int = 14):
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

def _atr(frame, period: int = 14):
    prev_close = frame["Close"].shift(1)
    tr1 = frame["High"] - frame["Low"]
    tr2 = abs(frame["High"] - prev_close)
    tr3 = abs(frame["Low"] - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

def _bollinger_bands(series, period: int = 20, num_std: float = 3.0):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma, sma + (std * num_std), sma - (std * num_std)

def get_session(hour):
    if 0 <= hour < 8: return "Asian"
    elif 8 <= hour < 13: return "London"
    elif 13 <= hour < 21: return "New York"
    else: return "Late NY/Sydney"

print("Fetching 60 days of 15-minute XAUUSD data for high-resolution backtesting...")
df = yf.Ticker("GC=F").history(period="60d", interval="15m")
df = df.dropna()

df["ema20"] = _ema(df["Close"], 20)
df["ema50"] = _ema(df["Close"], 50)
df["rsi14"] = _rsi(df["Close"], 14)
df["atr14"] = _atr(df, 14)
df["sma20"], df["upper3sd"], df["lower3sd"] = _bollinger_bands(df["Close"], 20, 3.0)

# Simulate rolling Support/Resistance
df["Rolling_Low"] = df["Low"].rolling(32).min().shift(1)
df["Rolling_High"] = df["High"].rolling(32).max().shift(1)

df = df.dropna().reset_index()

trades = []

# Parameters grid search
print(f"Total 15m candles to process: {len(df)}")

results = []
for stop_buffer in [0.2, 0.4, 0.6, 0.8]:
    for rr in [1.0, 1.2, 1.5]:
        trades = []
        for i in range(1, len(df)-1):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            current_price = curr["Close"]
            atr = curr["atr14"]
            rsi = curr["rsi14"]
            session = get_session(curr["Datetime"].hour)
            
            # 1. 3SD Mean Reversion
            is_3sd_bullish = prev["Low"] < prev["lower3sd"] and curr["Close"] > curr["lower3sd"]
            is_3sd_bearish = prev["High"] > prev["upper3sd"] and curr["Close"] < curr["upper3sd"]
            
            # 2. SMC Liquidity Sweep
            candle_range = max(curr["High"] - curr["Low"], 0.01)
            lower_wick = min(curr["Open"], curr["Close"]) - curr["Low"]
            upper_wick = curr["High"] - max(curr["Open"], curr["Close"])
            bullish_rejection = curr["Close"] > curr["Open"] and lower_wick >= candle_range * 0.4
            bearish_rejection = curr["Close"] < curr["Open"] and upper_wick >= candle_range * 0.4
            
            near_support = abs(current_price - curr["Rolling_Low"]) <= atr * 0.3
            near_resistance = abs(current_price - curr["Rolling_High"]) <= atr * 0.3
            
            is_smc_bullish = near_support and bullish_rejection and rsi < 35
            is_smc_bearish = near_resistance and bearish_rejection and rsi > 65
            
            trade = None
            if is_3sd_bullish:
                trade = {"type": "BUY", "strategy": "3SD", "entry": current_price, "sl": min(curr["Low"], curr["Rolling_Low"]) - atr * stop_buffer}
            elif is_3sd_bearish:
                trade = {"type": "SELL", "strategy": "3SD", "entry": current_price, "sl": max(curr["High"], curr["Rolling_High"]) + atr * stop_buffer}
            elif is_smc_bullish:
                trade = {"type": "BUY", "strategy": "SMC", "entry": current_price, "sl": min(curr["Low"], curr["Rolling_Low"]) - atr * stop_buffer}
            elif is_smc_bearish:
                trade = {"type": "SELL", "strategy": "SMC", "entry": current_price, "sl": max(curr["High"], curr["Rolling_High"]) + atr * stop_buffer}

            if trade:
                risk = abs(trade["entry"] - trade["sl"])
                if risk <= 0: continue
                
                if trade["type"] == "BUY":
                    trade["tp"] = trade["entry"] + (risk * rr)
                else:
                    trade["tp"] = trade["entry"] - (risk * rr)
                    
                trade["session"] = session
                trade["rr"] = rr
                
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
            wins = len(df_t[df_t['result'] == 'WIN'])
            wr = (wins / len(df_t)) * 100
            
            # Asian only performance
            asian_t = df_t[df_t['session'] == 'Asian']
            asian_wr = 0
            if not asian_t.empty:
                asian_wins = len(asian_t[asian_t['result'] == 'WIN'])
                asian_wr = (asian_wins / len(asian_t)) * 100
                
            results.append({"Stop_Buffer": stop_buffer, "RR": rr, "Trades": len(df_t), "WinRate": wr, "Asian_WR": asian_wr, "Asian_Trades": len(asian_t)})

print("\n--- OPTIMIZATION RESULTS ---")
res_df = pd.DataFrame(results).sort_values(by="Asian_WR", ascending=False)
print(res_df.to_string(index=False))
