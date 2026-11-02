# STRATEGY FILE. Copy this file to make a new strategy; every .py file in this folder is picked up
# (files starting with _ are ignored).
NAME = "Buy and hold"

def signals(prices):
    # prices: one row per day, one column per stock (closing prices).
    # Return a table of the same shape with True on days you want to HOLD that stock, False when you want to be out.
    # The platform decides how many stocks to hold at once, splits money into tranches and does the buying/selling.
    return prices.notna()
    
