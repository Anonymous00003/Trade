import numpy as np, pandas as pd

NAME = "Momentum 12-1 + market filter (top 8)"

# Weights style. Idea: hold the 8 strongest stocks, but (1) rank them by steady strength, not just the biggest jump,
# (2) skip any stock that is below its own 200-day average, and (3) move to cash (earning the idle-cash interest)
# whenever the average of all the stocks is below its 200-day average, to cut the deep falls that plain momentum suffers.
TOP = 8

def weights(prices):
    ret = prices.shift(21) / prices.shift(252) - 1                       # return from 12 months ago to 1 month ago (skips the latest month)
    vol = prices.pct_change().rolling(126).std() * np.sqrt(252)          # yearly ups-and-downs over the last 6 months
    score = (ret / vol).where(prices > prices.rolling(200).mean())       # strength per unit of bumpiness; only stocks in an uptrend
    pick = (score.rank(axis=1, ascending=False) <= TOP).astype(float) / TOP
    month = prices.index.to_series().dt.to_period("M")
    pick = pick.copy(); pick.loc[(month == month.shift()).values] = np.nan   # choose stocks on the first trading day of each month ...
    pick = pick.ffill().fillna(0)                                            # ... and hold them for the month
    market = (prices / prices.bfill().iloc[0]).mean(axis=1)                  # average of all stocks, each starting at 1
    risk_on = (market > market.rolling(200).mean()).astype(float)
    return pick.mul(risk_on, axis=0)                                         # market weak -> all cash, checked every day
