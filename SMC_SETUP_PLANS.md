# 📈 Planned Strategies & SMC Setups

This document outlines the advanced technical analysis setups and Smart Money Concepts (SMC) that are planned to be integrated into the trading engine at a later phase.

**Currently Active Strategy:** `xauusd_strategy.py` (Focuses on Momentum, EMA crossovers, and standard Support/Resistance bounds).

## Phase 4: SMC Integration (Planned)

We will introduce a secondary scoring module (`smc_strategy.py`) that strictly looks for institutional footprints.

### 1. Order Blocks (OB)

- **Identification:** Detecting the last bearish candle before a strong bullish push that breaks structure (BOS), or the last bullish candle before a strong bearish push.
- **Trading Rule:** Wait for the price to return to this block, look for rejection wicks on the 15M chart, and enter with a tight SL below the block.

### 2. Fair Value Gaps (FVG)

- **Identification:** Detecting 3-candle sequences where the 1st candle's wick and the 3rd candle's wick do not overlap, leaving an imbalance in price.
- **Trading Rule:** Price will often gravitate back to fill this gap. Use FVGs as Take Profit targets, or as Entry points if they align with an Order Block.

### 3. Liquidity Sweeps

- **Identification:** Identifying Equal Highs (EQH) and Equal Lows (EQL) on the 1H chart. These are zones where retail traders place their Stop Losses.
- **Trading Rule:** If price aggressively wicks past an EQH/EQL and immediately reverses (a "Judas Swing" or Liquidity Grab), take the trade in the opposite direction.

## Phase 5: ICT (Inner Circle Trader) High-Probability Setups

ICT concepts rely heavily on the _time_ of day combined with SMC price action. These are considered some of the highest win-rate strategies for Gold.

### 1. The Silver Bullet (Time-Based FVG)

- **Identification:** Strict time windows (e.g., NY Session 10:00 AM - 11:00 AM EST).
- **Trading Rule:** Wait for the market to sweep obvious liquidity just before the window opens. During the window, look for a sharp move that leaves a Fair Value Gap (FVG). Enter the trade exactly when the price retraces to touch the FVG. Target 1:2 to 1:3 RR.

### 2. ICT Killzones (London & New York Opens)

- **Identification:** High-volatility trading windows during the London Open (2:00 AM - 5:00 AM EST) and New York Open (7:00 AM - 10:00 AM EST).
- **Trading Rule:** The algorithm will restrict entries _only_ to these windows. It looks for the "Judas Swing"—a fakeout move in the opposite direction of the true trend to trap retail breakout traders, before reversing hard.

### 3. Market Structure Shift (MSS) with Displacement

- **Identification:** Following a Liquidity Sweep, the price violently breaks a recent Swing High (if bullish) or Swing Low (if bearish) with large, high-volume candles (Displacement).
- **Trading Rule:** Do not enter on the breakout. Wait for the price to pull back to the Order Block or FVG created by the displacement candle, and enter in the direction of the new structure.

## Phase 6: Custom Asian Session Sweep & Volume Profile

This is a highly specific, time-based 1-Minute (1M) strategy designed exclusively for the Gold Asian Session.

### 1. The 1M Asian Session Range Sweep

- **Time Window:** **IST 4:30 AM - 5:30 AM** (Asian Session).
- **Identification:** On the 1M chart, strictly mark the absolute High and absolute Low created between 4:30 AM and 5:30 AM IST.
- **Buy Setup:**
  1. Wait for price to drop below the marked Low (sweeping downside liquidity).
  2. Wait for a bullish Market Structure Shift (MSS) breaking a previous 1M lower-high.
  3. Ensure the MSS leaves a bullish Fair Value Gap (FVG).
  4. **Entry:** Buy limit at the FVG.
  5. **Stop Loss:** Placed just below the low of the candle that created the FVG.
  6. **Target:** 1:2 RR (or 1:3 RR if volume is high).
- **Sell Setup:**
  1. Wait for price to break above the marked High (sweeping upside liquidity).
  2. Wait for a bearish MSS breaking a previous 1M higher-low.
  3. Ensure the MSS leaves a bearish FVG.
  4. **Entry:** Sell limit at the FVG.
  5. **Stop Loss:** Placed just above the high of the candle that created the FVG.
  6. **Target:** 1:2 RR (or 1:3 RR if volume is high).

### 2. Session-Based Fixed Range Volume Profile

- **Concept:** Instead of using standard EMAs, calculate the Volume Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL) exclusively for each distinct trading session.
- **Usage:** If the Asian Session Sweep triggers, use the Session's POC as a magnet for Take Profit targets.

## Global Trading Sessions (IST Reference)

For the time-based algorithms, the system will use the following session boundaries (converted to Indian Standard Time - IST):

- **Sydney / Tokyo (Asian Session):** ~ 5:30 AM IST to 1:30 PM IST _(Note: The custom range above uses a tight 4:30 - 5:30 AM prep window)._
- **London Session:** 12:30 PM / 1:30 PM IST to 9:30 PM IST _(London Open Killzone is highly volatile)._
- **New York Session:** 6:30 PM IST to 2:30 AM IST _(Overlap with London between 6:30 PM - 9:30 PM IST is the highest volume period for Gold)._

## Phase 7: Quantitative & Mathematical Strategies (High Win Rate)

Based on algorithmic backtesting globally, these two mathematical strategies achieve highly consistent win rates (above **55% to 70%**) when coded correctly with strict confluence rules.

### 1. Fibonacci Confluence Strategy (Win Rate: ~55% - 65%)

- **Concept:** Markets naturally retrace in mathematical proportions before continuing the macro trend. The "Golden Zone" (0.5 to 0.618) is where institutional algorithms reload.
- **Identification:** Draw a Fibonacci sequence from the recent Swing Low to Swing High (in an uptrend) on the 1H chart.
- **Trading Rule:**
  1. Wait for price to drop back into the 0.5 - 0.618 Golden Zone.
  2. **Confluence Check:** Only take the trade if there is an Order Block (OB) or Fair Value Gap (FVG) resting directly inside the Golden Zone.
  3. **Entry:** Limit order at the 0.5 level. **SL:** Placed slightly below the 0.786 level. **Target:** The original 0.0 level (Swing High) for a guaranteed >1:2 RR.

### 2. Standard Deviation Mean Reversion (Win Rate: ~65% - 75%)

- **Concept:** Price acts like a rubber band. Statistically, price stays within 2 Standard Deviations (SD) of the mean 95% of the time. If it breaks out to 3 SD, it aggressively snaps back.
- **Identification:** Overlay a Volume Weighted Average Price (VWAP) anchored to the daily or weekly open, and mathematically plot the 2 SD and 3 SD bands.
- **Trading Rule:**
  1. Wait for a massive, exhaustive fundamental news spike that pushes the price completely outside the 3rd Standard Deviation band.
  2. Wait for the very first 5M or 15M candle to close back _inside_ the 3 SD band.
  3. **Entry:** Trade back toward the center. **Target:** The VWAP (Mean). **SL:** The absolute extreme wick of the spike. _(Note: This strategy naturally has a slightly smaller reward target, but makes up for it with a massive, reliable win rate)._

_Note: These will be built in the `trading/strategies/` folder in the future once the baseline data is collected._
