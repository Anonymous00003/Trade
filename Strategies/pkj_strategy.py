NAME = "PKJ (rough version, not the video's rules)"

# One long-term core tranche, plus two dip tranches bought after 10% and 20% falls (each sold at +10% profit).
SETTINGS = dict(max_stocks=10, tranches=3, bullish_tranches=1, step=10, bear_target=10, bull_min=None)

def signals(prices):
    # Core holding stays on while price is above 90% of its 200-day average.
    return prices >= prices.rolling(200).mean() * 0.90

def dip_ok(prices):
    # Dip tranches are bought on the fall itself, whatever the trend.
    return prices.notna()
