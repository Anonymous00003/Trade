NAME = "50/200 day average crossover"

def weights(prices):
    fast = prices.rolling(50).mean()
    slow = prices.rolling(200).mean()
    hold = (fast > slow).astype(float)      # 1 when a stock's 50-day average is above its 200-day average
    return hold / prices.shape[1]           # each stock gets an equal slice; unused slices stay cash
