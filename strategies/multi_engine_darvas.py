NAME = "Multi-Engine Darvas Strategy"

def signals(prices):
    # Multi-Engine Darvas: 50/100-day Donchian channel breakout for bullish momentum 
    # combined with 5% dip tranches and 5% fixed targets on bearish bounces.
    high_50 = prices.rolling(50).max()
    low_50 = prices.rolling(50).min()
    
    # Bullish breakout condition
    bullish = prices > high_50.shift(1)
    
    # Bearish bounce condition (price dropped below recent low then recovered)
    dropped = prices < low_50.shift(1)
    bounce = prices > prices.shift(1)
    
    return bullish | (dropped & bounce)
