NAME = "50/200 day average crossover"

def signals(prices):
    # Hold a stock while its 50-day average price is above its 200-day average price.
    return prices.rolling(50).mean() > prices.rolling(200).mean()
    
