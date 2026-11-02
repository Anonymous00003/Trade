import glob, os, json, importlib.util, datetime as dt
import numpy as np, pandas as pd

# ---- SETTINGS. The five below can be changed from the GitHub "Run workflow" screen; the last ones used are remembered ----
try: _prev = json.load(open("docs/results.json"))["params"]
except Exception: _prev = {}
def P(k, d): return os.environ.get(k.upper()) or _prev.get(k) or d
START = str(P("start", "2019-01-01")); END = str(P("end", ""))
CAPITAL = float(P("capital", 1500000)); MAXS = int(P("max_stocks", 10)); TR = int(P("tranches", 3))
COST = 0.002      # 0.2% on every buy and sell (brokerage + charges + slippage). Taxes NOT included.
IDLE = 0.065      # yearly interest earned on cash that is not invested (liquid-fund style)
STEP = 0.05       # a stock must fall 5% below your last buy before the next tranche is bought
BENCH = "^NSEI"
STOCKS = """RELIANCE TCS HDFCBANK INFY ICICIBANK HINDUNILVR ITC SBIN BHARTIARTL KOTAKBANK LT AXISBANK
ASIANPAINT MARUTI SUNPHARMA TITAN ULTRACEMCO BAJFINANCE NESTLEIND WIPRO HCLTECH NTPC POWERGRID ONGC
TATASTEEL JSWSTEEL COALINDIA BAJAJFINSV TECHM GRASIM HINDALCO DRREDDY CIPLA EICHERMOT BRITANNIA
DIVISLAB HEROMOTOCO BPCL TATACONSUM""".split()

def get_data():
    import yfinance as yf
    begin = (pd.Timestamp(START) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    raw = yf.download([s + ".NS" for s in STOCKS] + [BENCH], start=begin, auto_adjust=False, actions=True, progress=False)
    px = raw["Close"].dropna(axis=1, how="all").ffill(limit=5)
    div = raw["Dividends"].reindex_like(px).fillna(0) if "Dividends" in raw else px * 0
    for t in (px, div): t.columns = [c.replace(".NS", "") for c in t.columns]
    return px, div

def stats(c):
    days = max((c.index[-1] - c.index[0]).days, 1); end = float(c.iloc[-1])
    return dict(xirr=(end / CAPITAL) ** (365 / days) - 1, total=end / CAPITAL - 1, maxdd=float((c / c.cummax() - 1).min()), final=end)

def weekly(c): return [[d.strftime("%Y-%m-%d"), round(float(v))] for d, v in c.resample("W").last().dropna().items()]

def simulate(px, sig, div):
    pxf = px.ffill(); days = [d for d in px.index if d >= pd.Timestamp(START)]
    cash, pos, trades, divs, eq, mon = CAPITAL, {}, [], [], [], {}
    interest = dsum = realized = 0.0; prev = None
    def buy(p, price, amt):
        p["qty"] += amt / (1 + COST) / price; p["cost"] += amt; p["n"] += 1; p["last"] = price
    for d in days:
        ms = d.strftime("%Y-%m"); m = mon.setdefault(ms, dict(month=ms, closed=0, trade_pnl=0.0, interest=0.0, dividends=0.0, equity=0.0))
        if prev is not None:
            i = cash * IDLE * (d - prev).days / 365; cash += i; interest += i; m["interest"] += i
        prev = d; row = pxf.loc[d]; sg = sig.loc[d]; dv = div.loc[d]
        for s, p in list(pos.items()):
            if dv.get(s, 0) > 0:
                a = p["qty"] * dv[s]; cash += a; dsum += a; m["dividends"] += a
                divs.append(dict(date=d.strftime("%Y-%m-%d"), stock=s, per_share=round(float(dv[s]), 2), shares=round(p["qty"], 2), amount=round(a)))
            if not sg[s] and not np.isnan(row[s]):
                out = p["qty"] * row[s] * (1 - COST); pnl = out - p["cost"]; realized += pnl; cash += out
                m["closed"] += 1; m["trade_pnl"] += pnl
                trades.append(dict(stock=s, entry=p["entry"], exit=d.strftime("%Y-%m-%d"), tranches=p["n"], avg=round(p["cost"] / p["qty"], 2),
                                   price=round(float(row[s]), 2), pnl=round(pnl), pct=pnl / p["cost"], days=(d - pd.Timestamp(p["entry"])).days, status="Closed"))
                del pos[s]
        size = (CAPITAL + realized + interest + dsum) / (MAXS * TR)
        for s, p in pos.items():
            if sg[s] and p["n"] < TR and row[s] <= p["last"] * (1 - STEP) and cash >= size: buy(p, row[s], size); cash -= size
        for s in sig.columns:
            if len(pos) >= MAXS: break
            if sg[s] and s not in pos and not np.isnan(row[s]) and cash >= size:
                pos[s] = dict(qty=0.0, cost=0.0, n=0, last=0.0, entry=d.strftime("%Y-%m-%d")); buy(pos[s], row[s], size); cash -= size
        val = sum(p["qty"] * (row[s] if not np.isnan(row[s]) else p["last"]) for s, p in pos.items())
        eq.append(cash + val); m["equity"] = cash + val
    c = pd.Series(eq, index=days); unreal = 0.0; last = pxf.iloc[-1]
    for s, p in pos.items():
        pnl = p["qty"] * last[s] - p["cost"]; unreal += pnl
        trades.append(dict(stock=s, entry=p["entry"], exit="", tranches=p["n"], avg=round(p["cost"] / p["qty"], 2), price=round(float(last[s]), 2),
                           pnl=round(pnl), pct=pnl / p["cost"], days=(days[-1] - pd.Timestamp(p["entry"])).days, status="Open"))
    prev_eq = CAPITAL; monthly = []
    for k in sorted(mon):
        x = mon[k]; x["ret"] = x["equity"] / prev_eq - 1; prev_eq = x["equity"]
        monthly.append({a: (round(b, 4) if a == "ret" else round(b) if isinstance(b, float) else b) for a, b in x.items()})
    by = {}
    for t in trades: by.setdefault(t["stock"], []).append(t)
    dstock = {}
    for e in divs: dstock[e["stock"]] = dstock.get(e["stock"], 0) + e["amount"]
    stocks = []
    for s, ts in by.items():
        cl = [t for t in ts if t["status"] == "Closed"]
        stocks.append(dict(stock=s, trades=len(ts), wins=sum(t["pnl"] > 0 for t in cl), closed=len(cl), realized=sum(t["pnl"] for t in cl),
                           unrealized=sum(t["pnl"] for t in ts if t["status"] == "Open"), dividends=dstock.get(s, 0),
                           avg_days=round(float(np.mean([t["days"] for t in ts])))))
    stocks.sort(key=lambda x: x["realized"] + x["unrealized"] + x["dividends"], reverse=True)
    tr = sum(t["pnl"] for t in trades if t["status"] == "Closed")
    m = stats(c); m.update(trade_realized=round(tr), interest=round(interest), dividends=round(dsum), unrealized=round(unreal),
                           total_realized=round(tr + interest + dsum), trades=len(trades), open=len(pos), base=round(CAPITAL + tr + interest + dsum))
    trades.sort(key=lambda t: t["entry"], reverse=True)
    return dict(m=m, curve=weekly(c), trades=trades[:600], monthly=monthly, stocks=stocks, dividends=divs[::-1][:600])

def main(data=None):
    px, div = get_data() if data is None else data
    if END: px, div = px.loc[:END], div.loc[:END]
    bench = px[BENCH] if BENCH in px else None
    stocks = px.drop(columns=[BENCH], errors="ignore"); dv = div.reindex_like(stocks).fillna(0)
    out, broken = [], []
    for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies", "*.py"))):
        if os.path.basename(f).startswith("_"): continue
        try:
            spec = importlib.util.spec_from_file_location("strat", f); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            sg = m.signals(stocks.copy()) if hasattr(m, "signals") else m.weights(stocks.copy()) > 0
            sg = sg.reindex(stocks.index).reindex(columns=stocks.columns).fillna(False).astype(bool).shift(1, fill_value=False)  # act the day AFTER the signal
            out.append(dict(name=m.NAME, **simulate(stocks, sg, dv)))
        except Exception as e:
            broken.append(dict(file=os.path.basename(f), problem=str(e)[:200]))
    out.sort(key=lambda x: x["m"]["xirr"], reverse=True)
    b = None
    if bench is not None:
        c = CAPITAL * (1 + bench.pct_change().fillna(0).loc[START:]).cumprod(); b = dict(name="Nifty 50 index (for comparison)", m=stats(c), curve=weekly(c))
    os.makedirs("docs", exist_ok=True)
    json.dump(dict(updated=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), benchmark=b, strategies=out, broken=broken,
                   params=dict(start=START, end=END, capital=CAPITAL, max_stocks=MAXS, tranches=TR, cost=COST, idle=IDLE, step=STEP)), open("docs/results.json", "w"))
    print("Done:", [(x["name"], round(x["m"]["xirr"] * 100, 1), x["m"]["trades"]) for x in out], "broken:", broken)

if __name__ == "__main__":
    main()
                
