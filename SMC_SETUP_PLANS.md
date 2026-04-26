# 📈 Planned Strategies & SMC Setups

This document outlines the advanced technical analysis setups and Smart Money Concepts (SMC) that are planned to be integrated into the trading engine at a later phase. 

**Currently Active Strategy:** `xauusd_strategy.py` (Focuses on Momentum, EMA crossovers, and standard Support/Resistance bounds).

## Phase 4: SMC Integration (Planned)
We will introduce a secondary scoring module (`smc_strategy.py`) that strictly looks for institutional footprints. 

### 1. Order Blocks (OB)
*   **Identification:** Detecting the last bearish candle before a strong bullish push that breaks structure (BOS), or the last bullish candle before a strong bearish push.
*   **Trading Rule:** Wait for the price to return to this block, look for rejection wicks on the 15M chart, and enter with a tight SL below the block.

### 2. Fair Value Gaps (FVG)
*   **Identification:** Detecting 3-candle sequences where the 1st candle's wick and the 3rd candle's wick do not overlap, leaving an imbalance in price.
*   **Trading Rule:** Price will often gravitate back to fill this gap. Use FVGs as Take Profit targets, or as Entry points if they align with an Order Block.

### 3. Liquidity Sweeps
*   **Identification:** Identifying Equal Highs (EQH) and Equal Lows (EQL) on the 1H chart. These are zones where retail traders place their Stop Losses.
*   **Trading Rule:** If price aggressively wicks past an EQH/EQL and immediately reverses (a "Judas Swing" or Liquidity Grab), take the trade in the opposite direction.

## Phase 5: ICT (Inner Circle Trader) High-Probability Setups
ICT concepts rely heavily on the *time* of day combined with SMC price action. These are considered some of the highest win-rate strategies for Gold.

### 1. The Silver Bullet (Time-Based FVG)
*   **Identification:** Strict time windows (e.g., NY Session 10:00 AM - 11:00 AM EST).
*   **Trading Rule:** Wait for the market to sweep obvious liquidity just before the window opens. During the window, look for a sharp move that leaves a Fair Value Gap (FVG). Enter the trade exactly when the price retraces to touch the FVG. Target 1:2 to 1:3 RR.

### 2. ICT Killzones (London & New York Opens)
*   **Identification:** High-volatility trading windows during the London Open (2:00 AM - 5:00 AM EST) and New York Open (7:00 AM - 10:00 AM EST).
*   **Trading Rule:** The algorithm will restrict entries *only* to these windows. It looks for the "Judas Swing"—a fakeout move in the opposite direction of the true trend to trap retail breakout traders, before reversing hard.

### 3. Market Structure Shift (MSS) with Displacement
*   **Identification:** Following a Liquidity Sweep, the price violently breaks a recent Swing High (if bullish) or Swing Low (if bearish) with large, high-volume candles (Displacement).
*   **Trading Rule:** Do not enter on the breakout. Wait for the price to pull back to the Order Block or FVG created by the displacement candle, and enter in the direction of the new structure.

*Note: These will be built in the `trading/strategies/` folder in the future once the baseline data is collected.*
