import numpy as np

NAME = "Top-5 momentum (monthly rebalance)"

# This strategy uses the "weights" style: it decides its own allocation instead of using tranches.
def weights(prices):
    mom = prices.pct_change(126)                                          # return over the last ~6 months
    pick = (mom.rank(axis=1, ascending=False) <= 5).astype(float) / 5     # equal money in the 5 strongest stocks
    month = prices.index.to_series().dt.to_period("M")
    pick = pick.copy(); pick.loc[(month == month.shift()).values] = np.nan   # keep only the first trading day of each month ...
    return pick.ffill().fillna(0)                                         # ... and hold that choice for the rest of the month
