NAME = "Paiso Ka Jungle (PKJ)"

def signals(prices):
    # PKJ: Long-term compounding base. Stays invested when price is above 200 DMA,
    # and triggers dip-buying/profit-harvesting when deviations occur.
    ma_200 = prices.rolling(200).mean()
    # Stay invested in trend, allowing dip-buying additions
    return prices >= (ma_200 * 0.90)  # Allows holding through minor -10% dips for multi-tranche accumulation
