# STRATEGY FILE. Copy this file to make a new strategy; the engine picks up every .py file
# in this folder (files starting with _ are ignored).
NAME = "Equal weight, all stocks"

def weights(prices):
    # prices: one row per day, one column per stock (closing prices).
    # Return a table of the same shape: the share of your money (0 to 1) you want in each stock that day.
    # Each row should add up to 1 or less. Money not allocated stays in cash.
    have = prices.notna()
    return have.div(have.sum(axis=1), axis=0)
  
