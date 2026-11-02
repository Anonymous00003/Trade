import glob, os, json, importlib.util, datetime as dt
import numpy as np, pandas as pd

# ---- SETTINGS (same for every strategy) ----
CAPITAL = 1_500_000        # starting money, rupees
START = "2019-01-01"       # everyone starts on this date
COST = 0.002               # 0.2% charged on every rupee bought or sold (brokerage + charges + price slippage). Taxes NOT included yet.
BENCH = "^NSEI"            # Nifty 50 index, shown for comparison
STOCKS = """RELIANCE TCS HDFCBANK INFY ICICIBANK HINDUNILVR ITC SBIN BHARTIARTL KOTAKBANK LT AXISBANK
ASIANPAINT MARUTI SUNPHARMA TITAN ULTRACEMCO BAJFINANCE NESTLEIND WIPRO HCLTECH NTPC POWERGRID ONGC
TATASTEEL JSWSTEEL COALINDIA BAJAJFINSV TECHM GRASIM HINDALCO DRREDDY CIPLA EICHERMOT BRITANNIA
DIVISLAB HEROMOTOCO BPCL TATACONSUM""".split()

def get_prices():
    import yfinance as yf
    begin = (pd.Timestamp(START) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    raw = yf.download([s + ".NS" for s in STOCKS] + [BENCH], start=begin, auto_adjust=True, progress=False)["Close"]
    return raw.dropna(axis=1, how="all").ffill(limit=5)

def curve_from(ret):
    return CAPITAL * (1 + ret.loc[START:]).cumprod()

def stats(c):
    days = max((c.index[-1] - c.index[0]).days, 1)
    end = float(c.iloc[-1])
    return {"xirr": (end / CAPITAL) ** (365 / days) - 1, "total": end / CAPITAL - 1,
            "maxdd": float((c / c.cummax() - 1).min()), "final": end}

def row(name, c, kind="strategy"):
    s = stats(c); w = c.resample("W").last().dropna()
    s.update(name=name, kind=kind, curve=[[d.strftime("%Y-%m-%d"), round(float(v))] for d, v in w.items()])
    return s

def main(px=None):
    px = get_prices() if px is None else px
    bench = px[BENCH] if BENCH in px else None
    stocks = px.drop(columns=[BENCH], errors="ignore")
    r = stocks.pct_change().fillna(0)
    rows, broken = [], []
    if bench is not None:
        rows.append(row("Nifty 50 index (for comparison)", curve_from(bench.pct_change().fillna(0)), "benchmark"))
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "strategies", "*.py"))):
        if os.path.basename(f).startswith("_"): continue
        try:
            spec = importlib.util.spec_from_file_location("strat", f)
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            w = m.weights(stocks.copy()).reindex(stocks.index).reindex(columns=stocks.columns).fillna(0)
            w = w.where(stocks.notna(), 0).shift(1).fillna(0)       # trade the day AFTER the signal: no peeking at the future
            turnover = w.diff().fillna(w).abs().sum(axis=1)
            ret = (w * r).sum(axis=1) - COST * turnover
            rows.append(row(m.NAME, curve_from(ret)))
        except Exception as e:
            broken.append({"file": os.path.basename(f), "problem": str(e)[:200]})
    rows.sort(key=lambda x: x["xirr"], reverse=True)
    out = {"updated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "capital": CAPITAL, "start": START,
           "cost": COST, "rows": rows, "broken": broken}
    os.makedirs("docs", exist_ok=True)
    json.dump(out, open("docs/results.json", "w"))
    print("Done:", [(x["name"], round(x["xirr"] * 100, 1)) for x in rows], "broken:", broken)

if __name__ == "__main__":
    main()
