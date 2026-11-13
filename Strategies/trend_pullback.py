"""
Trend-following pullback strategy for the existing Trade-main backtest engine.

Important data constraint:
- The project downloads adjusted/unadjusted daily CLOSE only (plus dividends).
- Therefore this strategy uses a close-to-close volatility proxy for its initial stop distance.
- It is NOT true ATR. A true ATR implementation requires High, Low and Close data.
- Stop and target fills are simulated at the daily close when crossed; gaps/intraday fills are not modelled.

Signal timing:
- Signals are shifted by the engine and acted on the next trading day.
- The benchmark filter is also shifted by the engine integration.
"""

import numpy as np
import pandas as pd

NAME = "Trend Pullback (20 EMA + 50/200 trend, 2.5R)"

SETTINGS = dict(
    max_stocks=10,       # engine allocates roughly 1/10 of portfolio per first entry
    tranches=1,          # one entry only; no averaging down
    bullish_tranches=1,
    step=5.0,            # unused when there are no dip tranches
    bear_target=5.0,     # unused when there are no dip tranches
    bull_min=None,       # signal exit is allowed at any P&L
    bearish_exit="target",
    bull_min_annual=None,
    dip_trigger="step",
    dip_basis="touch",
    reserve_pct=None,
    bull_target_r=2.5,   # target = entry + 2.5 x initial stop distance
)

def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def signals(prices):
    """
    Entry event:
      1) Close > 50 SMA > 200 SMA.
      2) 50 SMA is rising versus 10 sessions ago.
      3) Close is within 1.5% of 20 EMA (close-only pullback approximation).
      4) RSI(14) is 40–60.
      5) Close is higher than previous close (daily confirmation).

    Hold state exits when close falls below 50 SMA. A stop-loss or 2.5R target
    can exit earlier inside the shared engine.
    """
    ema20 = prices.ewm(span=20, adjust=False, min_periods=20).mean()
    sma50 = prices.rolling(50, min_periods=50).mean()
    sma200 = prices.rolling(200, min_periods=200).mean()
    rsi = prices.apply(_rsi)

    trend = (prices > sma50) & (sma50 > sma200) & (sma50 > sma50.shift(10))
    near_pullback = ((prices / ema20) - 1).abs() <= 0.015
    momentum_reset = rsi.apply(lambda col: col.between(40, 60))
    confirmation = prices > prices.shift(1)
    entry = trend & near_pullback & momentum_reset & confirmation

    exit_ = prices < sma50
    state = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    state[entry] = 1.0
    state[exit_] = 0.0
    return state.ffill().fillna(0).astype(bool)

def market_filter(benchmark):
    """Only open/hold long trades while NIFTY 50 is above its 50-day SMA."""
    sma50 = benchmark.rolling(50, min_periods=50).mean()
    return benchmark > sma50

def stop_distances(prices):
    """
    Initial stop distance = 2 x 14-session mean absolute close-to-close move.
    This is deliberately called a volatility proxy, not ATR, because High/Low
    data are not available in this repository's current data pipeline.
    """
    close_change = prices.diff().abs()
    proxy = close_change.rolling(14, min_periods=14).mean() * 2.0
    # Avoid implausibly tiny stops caused by flat/rounded prices.
    floor = prices.abs() * 0.01
    return pd.DataFrame(np.maximum(proxy.to_numpy(), floor.to_numpy()),
                        index=prices.index, columns=prices.columns)
