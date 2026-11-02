"""Multi-strategy paper-trading engine. Reads every file in strategies/, simulates each one with the same
rules, capital and dates, and writes docs/results.json for the dashboard (docs/index.html)."""
import glob, os, json, importlib.util, datetime as dt
import numpy as np, pandas as pd

# ---------------- SETTINGS ----------------
# The seven below can be changed from the GitHub "Run workflow" screen. The last values used are remembered,
# so the automatic daily runs keep using them. Defaults apply the very first time.
try: _prev = json.load(open("docs/results.json"))["params"]
except Exception: _prev = {}
def P(k, d):
    v = os.environ.get(k.upper())
    if v in (None, ""): v = _prev.get(k)
    return d if v in (None, "") else v
START = str(P("start", "2019-01-01")); END = str(P("end", ""))
CAPITAL = float(P("capital", 1500000))     # overall capital, rupees
MAXS = int(P("max_stocks", 10))            # max stocks held at the same time (the number of slots)
TR = int(P("tranches", 3))                 # tranches (parts) each stock's money is split into
BEAR = float(P("bear_target", 5)) / 100    # Bearish Target %: a tranche bought after a dip is sold when it is this much in profit
BULL = float(P("bull_min", 2)) / 100       # Bullish Exit Min Return %: a first tranche is sold when its strategy turns off AND it is at least this much in profit
COST = 0.002                               # 0.2% on every buy and sell (brokerage + charges + slippage). Taxes NOT included.
IDLE = 0.05                                # yearly interest on idle cash (parked in a liquid ETF / liquid fund, modelled as a flat rate)
STEP = 0.05                                # a stock must fall this far below your last buy before the next tranche is bought
BENCH = "^NSEI"                            # Nifty 50 index, shown for comparison
STOCKS = """RELIANCE TCS HDFCBANK INFY ICICIBANK HINDUNILVR ITC SBIN BHARTIARTL KOTAKBANK LT AXISBANK
ASIANPAINT MARUTI SUNPHARMA TITAN ULTRACEMCO BAJFINANCE NESTLEIND WIPRO HCLTECH NTPC POWERGRID ONGC
TATASTEEL JSWSTEEL COALINDIA BAJAJFINSV TECHM GRASIM HINDALCO DRREDDY CIPLA EICHERMOT BRITANNIA
DIVISLAB HEROMOTOCO BPCL TATACONSUM""".split()

# ---------------- DATA ----------------
def get_data():
    import yfinance as yf
    begin = (pd.Timestamp(START) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    raw = yf.download([s + ".NS" for s in STOCKS] + [BENCH], start=begin, auto_adjust=False, actions=True, progress=False)
    px = raw["Close"].dropna(axis=1, how="all").ffill(limit=5)   # raw (split-adjusted) closes; dividends are paid separately below
    div = raw["Dividends"].reindex_like(px).fillna(0) if "Dividends" in raw else px * 0
    for t in (px, div): t.columns = [c.replace(".NS", "") for c in t.columns]
    return px, div

def stats(c):
    days = max((c.index[-1] - c.index[0]).days, 1); end = float(c.iloc[-1])
    return dict(xirr=(end / CAPITAL) ** (365 / days) - 1, total=end / CAPITAL - 1, maxdd=float((c / c.cummax() - 1).min()), final=end)

def weekly(c): return [[d.strftime("%Y-%m-%d"), round(float(v))] for d, v in c.resample("W").last().dropna().items()]

# ---------------- SIMULATION ----------------
def simulate(px, sig, div):
    pxf = px.ffill(); days = [d for d in px.index if d >= pd.Timestamp(START)]
    cash, held, log, divs, eq, mon = CAPITAL, {}, [], [], [], {}
    interest = dsum = realized = 0.0; prev = None
    def buy(s, kind, price, amt, d):
        h = held.setdefault(s, dict(lots=[], last=0.0))
        slot = min(set(range(1, TR + 1)) - {l["slot"] for l in h["lots"]})
        lot = dict(symbol=s, type=kind, slot=slot, buy_date=d.strftime("%Y-%m-%d"), buy_price=float(price), shares=amt / (1 + COST) / price,
                   invested=amt, target=float(price) * (1 + (BEAR if kind == "Bearish" else BULL)), sell_date=None)
        h["lots"].append(lot); h["last"] = float(price); log.append(lot)
    for d in days:
        ms = d.strftime("%Y-%m"); m = mon.setdefault(ms, dict(month=ms, closed=0, trade_pnl=0.0, interest=0.0, dividends=0.0, equity=0.0))
        if prev is not None:
            i = cash * IDLE * (d - prev).days / 365; cash += i; interest += i; m["interest"] += i
        prev = d; row = pxf.loc[d]; sg = sig.loc[d]; dv = div.loc[d]
        for s, h in list(held.items()):
            p = row[s]
            if np.isnan(p): continue
            if dv.get(s, 0) > 0:
                q = sum(l["shares"] for l in h["lots"]); a = q * dv[s]; cash += a; dsum += a; m["dividends"] += a
                divs.append(dict(date=d.strftime("%Y-%m-%d"), symbol=s, per_share=round(float(dv[s]), 2), shares=round(q, 2), amount=round(a)))
            for l in list(h["lots"]):
                if p >= l["target"] and (l["type"] == "Bearish" or not sg[s]):
                    out = l["shares"] * p * (1 - COST); l.update(sell_date=d.strftime("%Y-%m-%d"), sell_price=float(p), pnl=out - l["invested"])
                    cash += out; realized += l["pnl"]; m["closed"] += 1; m["trade_pnl"] += l["pnl"]; h["lots"].remove(l)
            if not h["lots"]: del held[s]
        size = (CAPITAL + realized + interest + dsum) / (MAXS * TR)       # compounded: tranche size grows with profits
        for s, h in held.items():
            if sg[s] and len(h["lots"]) < TR and row[s] <= h["last"] * (1 - STEP) and cash >= size:
                buy(s, "Bearish", row[s], size, d); cash -= size
        for s in sig.columns:
            if len(held) >= MAXS: break
            if sg[s] and s not in held and not np.isnan(row[s]) and cash >= size:
                buy(s, "Bullish", row[s], size, d); cash -= size
        val = sum(l["shares"] * (row[s] if not np.isnan(row[s]) else h["last"]) for s, h in held.items() for l in h["lots"])
        eq.append(cash + val); m["equity"] = cash + val
    c = pd.Series(eq, index=days); last = pxf.iloc[-1]; unreal = 0.0; trades = []
    for l in log:
        is_open = l["sell_date"] is None; lp = float(last[l["symbol"]]) if not np.isnan(last[l["symbol"]]) else l["buy_price"]
        pnl = l["shares"] * lp - l["invested"] if is_open else l["pnl"]; unreal += pnl if is_open else 0
        end = days[-1] if is_open else pd.Timestamp(l["sell_date"])
        trades.append(dict(symbol=l["symbol"], type=l["type"], slot=l["slot"], buy_date=l["buy_date"], buy_price=round(l["buy_price"], 2),
                           shares=round(l["shares"], 2), invested=round(l["invested"]), target=round(l["target"], 2),
                           sell_date="Open" if is_open else l["sell_date"], sell_price=None if is_open else round(l["sell_price"], 2),
                           pnl=round(pnl), ret=pnl / l["invested"], days=(end - pd.Timestamp(l["buy_date"])).days, status="Open" if is_open else "Closed"))
    prev_eq = CAPITAL; monthly = []
    for k in sorted(mon):
        x = mon[k]; x["ret"] = x["equity"] / prev_eq - 1; prev_eq = x["equity"]
        monthly.append({a: (round(b, 4) if a == "ret" else round(b) if isinstance(b, float) else b) for a, b in x.items()})
    by, dstock = {}, {}
    for t in trades: by.setdefault(t["symbol"], []).append(t)
    for e in divs: dstock[e["symbol"]] = dstock.get(e["symbol"], 0) + e["amount"]
    stocks = []
    for s, ts in by.items():
        cl = [t for t in ts if t["status"] == "Closed"]
        stocks.append(dict(symbol=s, trades=len(ts), closed=len(cl), wins=sum(t["pnl"] > 0 for t in cl), realized=sum(t["pnl"] for t in cl),
                           unrealized=sum(t["pnl"] for t in ts if t["status"] == "Open"), dividends=dstock.get(s, 0), avg_days=round(float(np.mean([t["days"] for t in ts])))))
    stocks.sort(key=lambda x: x["realized"] + x["unrealized"] + x["dividends"], reverse=True)
    tr = sum(t["pnl"] for t in trades if t["status"] == "Closed"); m = stats(c)
    m.update(trade_realized=round(tr), interest=round(interest), dividends=round(dsum), unrealized=round(unreal), total_realized=round(tr + interest + dsum),
             closed=sum(t["status"] == "Closed" for t in trades), trades_total=len(trades), base=round(CAPITAL + tr + interest + dsum))
    trades.sort(key=lambda t: t["buy_date"], reverse=True)
    return dict(m=m, curve=weekly(c), trades=trades[:1000], monthly=monthly, stocks=stocks, dividends=divs[::-1][:1000])

# ---------------- MAIN ----------------
def main(data=None):
    px, div = get_data() if data is None else data
    if END: px, div = px.loc[:END], div.loc[:END]
    bench = px[BENCH] if BENCH in px else None
    stocks = px.drop(columns=[BENCH], errors="ignore"); dv = div.reindex_like(stocks).fillna(0)
    res, broken = [], []
    for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies", "*.py"))):
        if os.path.basename(f).startswith("_"): continue
        try:
            spec = importlib.util.spec_from_file_location("strat", f); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            sg = mod.signals(stocks.copy()) if hasattr(mod, "signals") else mod.weights(stocks.copy()) > 0
            sg = sg.reindex(stocks.index).reindex(columns=stocks.columns).fillna(False).astype(bool).shift(1, fill_value=False)  # act the day AFTER the signal
            res.append(dict(name=mod.NAME, **simulate(stocks, sg, dv)))
        except Exception as e:
            broken.append(dict(file=os.path.basename(f), problem=str(e)[:200]))
    res.sort(key=lambda x: x["m"]["xirr"], reverse=True)
    board = [dict(rank=i + 1, name=r["name"], **{k: r["m"][k] for k in ("xirr", "total", "maxdd", "final", "total_realized", "closed", "trades_total")}) for i, r in enumerate(res)]
    b = None
    if bench is not None:
        c = CAPITAL * (1 + bench.pct_change().fillna(0).loc[START:]).cumprod(); b = dict(name="Nifty 50 index (for comparison)", m=stats(c), curve=weekly(c))
    os.makedirs("docs", exist_ok=True)
    json.dump(dict(updated=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), params=dict(start=START, end=END, capital=CAPITAL, max_stocks=MAXS, tranches=TR,
              bear_target=BEAR * 100, bull_min=BULL * 100, cost=COST, idle=IDLE, step=STEP), leaderboard=board, benchmark=b, strategies=res, broken=broken),
              open("docs/results.json", "w"))
    print("Done:", [(r["rank"], r["name"], round(r["xirr"] * 100, 1), f'{r["closed"]}/{r["trades_total"]}', round(r["total"] * 100)) for r in board], "broken:", broken)

if __name__ == "__main__":
    main()
        
