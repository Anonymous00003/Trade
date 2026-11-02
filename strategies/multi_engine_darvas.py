NAME = "Multi-Engine Darvas Strategy"

def signals(prices):
    # Multi-engine Darvas core trend-following logic using Donchian channels / moving averages
    return prices > prices.rolling(50).max().shift(1)
  
