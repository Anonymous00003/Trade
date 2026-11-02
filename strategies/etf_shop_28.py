NAME = "ETF Shop 28 (28 SMA Momentum)"

def signals(prices):
    # ETF Shop 28: 28 SMA Momentum Strategy
    # Requires price above 28 SMA for 2 consecutive days with 3.14% profit target tracking
    sma_28 = prices.rolling(28).mean()
    above_sma = prices > sma_28
    # 2 consecutive days confirmation rule
    return above_sma & above_sma.shift(1)
  
