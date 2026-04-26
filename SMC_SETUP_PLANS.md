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

*Note: These will be built in the `trading/strategies/` folder in the future.*
