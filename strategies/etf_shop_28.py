import numpy as np, pandas as pd

NAME = "ETF Shop 28 (28 SMA Momentum)"

# Rules as stated in the video: daily chart, 28-day SMA. 70% of capital is for first buys, 30% is reserved for averaging.
# Entry: 2 closes in a row above the 28 SMA. Averaging: a fresh breakout above the 28 SMA while price is 5% or more below the last purchase.
# Exit: 2 closes in a row below the 28 SMA, only if profit is at least 3.14%. No stop loss. Every tranche follows the same exit.
# ASSUMPTIONS: 3 tranches per ETF (1 first buy + 2 averaging) and 30 holdings at a time (the video's example limit).
# NOTE: the video trades ETFs; the platform currently has only the Nifty 50 stocks, so this runs on those as a stand-in.
SETTINGS = dict(max_stocks=30, tranches=3, bullish_tranches=1, step=5, bear_target=3.14, bull_min=3.14,
                bearish_exit="signal", dip_basis="current", reserve_pct=30)

def _sma(prices): return prices.rolling(28).mean()

def signals(prices):
    sma = _sma(prices); above = prices > sma; below = prices < sma
    on = above & above.shift(1, fill_value=False)                       # 2 closes above the 28 SMA
    off = below & below.shift(1, fill_value=False)                      # 2 closes below the 28 SMA
    fast = prices.pct_change(21).shift(1) > 0.18                        # fast mover: up more than 18% in about a month ...
    off = off | (fast & (prices < prices.shift(1)))                     # ... then leave on the first red day instead
    s = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns); s[on] = 1.0; s[off] = 0.0
    return s.ffill().fillna(0).astype(bool)

def dip_ok(prices):
    # Averaging only on the day price breaks back above the 28 SMA.
    sma = _sma(prices)
    return (prices > sma) & ~(prices.shift(1) > sma.shift(1))
    
