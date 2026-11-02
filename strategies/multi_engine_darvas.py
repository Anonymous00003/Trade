import numpy as np, pandas as pd

NAME = "Multi-Engine Darvas Strategy"

# Rules as stated in the video (weekly chart, 20-candle Donchian channel):
# 25 stocks at a time, 4 equal tranches per stock = 3 bearish (dip) tranches + 1 bullish tranche.
# Bearish tranches: bought on weekly bounces, each sold at +5%. Bullish tranche: bought on a 20-week-high breakout,
# sold when a weekly close falls below the 20-week low, but only if its annualised return is at least 15%. No stop loss.
SETTINGS = dict(max_stocks=25, tranches=4, bullish_tranches=1, bear_target=5, bull_min=None, bull_min_annual=15, dip_trigger="signal")

N = 20          # Donchian channel length, in weeks
LOOKBACK = 8    # ASSUMPTION: a pullback counts as "bearish" for 8 weeks after a weekly close below the 20-week low

def _weekly(prices):
    w = prices.resample("W-FRI").last().dropna(how="all")
    return w[w.index <= prices.index[-1]]                      # only finished weeks

def _daily_state(w_bool, idx):                                 # a weekly yes/no, known from the day that week ends
    return w_bool.reindex(idx, method="ffill").fillna(False).astype(bool)

def _daily_event(w_bool, idx):                                 # a weekly event, placed on the last trading day of that week
    out = pd.DataFrame(False, index=idx, columns=w_bool.columns)
    pos = idx.searchsorted(w_bool.index, side="right") - 1
    for i, p in enumerate(pos):
        if p >= 0: out.iloc[p] = out.iloc[p].values | w_bool.iloc[i].values
    return out

def signals(prices):
    # Bullish regime: ON after a weekly close above the previous 20-week high, OFF after a weekly close below the previous 20-week low.
    w = _weekly(prices)
    on = w > w.rolling(N).max().shift(1); off = w < w.rolling(N).min().shift(1)
    s = pd.DataFrame(np.nan, index=w.index, columns=w.columns); s[on] = 1.0; s[off] = 0.0
    return _daily_state(s.ffill().fillna(0).astype(bool), prices.index)

def dip_entry(prices):
    # Bearish buy: after a weekly close below the 20-week low, buy on a weekly bounce.
    # (The video says the bounce week must close above the previous week's HIGH; the platform only has closing prices,
    #  so this uses "closes above the previous week's close".)
    w = _weekly(prices)
    below = (w < w.rolling(N).min().shift(1)).astype(float)
    recent = below.rolling(LOOKBACK, min_periods=1).max().gt(0)
    return _daily_event(recent.shift(1, fill_value=False) & (w > w.shift(1)), prices.index)
