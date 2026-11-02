"""Multi-strategy paper-trading engine. Simulates every file in strategies/ with the same capital, dates, costs and
interest, but each strategy runs by ITS OWN rules. Writes docs/results.json for the dashboard (docs/index.html).

A strategy file must define NAME and one of two styles:

 1) Tranche style (stocks bought in parts):
      signals(prices)    -> True/False table: "bullish regime on today?"  (required)
      dip_ok(prices)     -> optional True/False table: extra condition needed before buying an averaging (dip) tranche
                            (default: the signal must be on)
      dip_entry(prices)  -> optional True/False table: days a dip tranche may be the FIRST purchase in a stock
      SETTINGS = dict(max_stocks=10, tranches=4, bullish_tranches=1, step=5, bear_target=5, bull_min=None, bearish_exit="target")
        max_stocks        stocks held at the same time
        tranches          parts each stock's money is split into (bullish + dip)
        bullish_tranches  how many of those parts are reserved for the bullish entry (the rest are dip tranches)
        step              % the price must fall below the last purchase (then touch/recover per dip_ok) before the next dip tranche
        bear_target       % profit at which a dip tranche is sold
        bull_min          minimum % profit before a bullish tranche may be sold when its signal turns off (None = sell on signal off, whatever the profit)
        bearish_exit      "target" = dip tranches sell at their own target; "signal" = they also wait for the signal to turn off
        bull_min_annual   optional: a bullish tranche may only be sold if its profit, annualised for the days held, is at least this %
        dip_trigger       "step" (default) = dip tranches follow the price-step rule; "signal" = bought whenever dip_entry() is True (step ignored)
        dip_basis         "touch" (default) = price touched `step` below the last buy since then; "current" = price is `step` below it today
        reserve_pct       optional: % of capital reserved for dip tranches (e.g. 30 = 70% for first buys, 30% for averaging); default is equal parts
 2) Weights style:  weights(prices) -> table of target shares of money (0 to 1) per stock per day. The engine rebalances to it.

Anything missing from SETTINGS falls back to ENGINE_DEFAULTS below. Files starting with _ are ignored."""
import glob, os, json, importlib.util, datetime as dt
import numpy as np, pandas as pd

# ---------------- GLOBAL SETTINGS (identical for every strategy) ----------------
# START / END / WITHDRAW can be changed from the GitHub "Run workflow" screen; the last values used are remembered for the daily runs.
try: _prev = json.load(open("docs/results.json"))["params"]
except Exception: _prev = {}
def P(k, d):
    v = os.environ.get(k.upper())
    if v in (None, ""): v = _prev.get(k)
    return d if v in (None, "") else v
START = str(P("start", "2019-01-01")); END = str(P("end", ""))
WITHDRAW = float(P("withdraw", 0))         # rupees taken out of idle cash on the first trading day of each month (0 = everything is reinvested)
CAPITAL = 1500000.0                        # initial capital for every strategy: Rs 15,00,000 (fixed)
COST = 0.002                               # 0.2% on every buy and sell (brokerage + charges + slippage). Taxes NOT included.
IDLE = 0.065                               # 6.5% a year on idle cash (liquid ETF / liquid fund, modelled as a flat rate)
BENCH = "^NSEI"                            # Nifty 50 index, shown for comparison
ENGINE_DEFAULTS = dict(max_stocks=10, tranches=3, bullish_tranches=1, step=5.0, bear_target=5.0, bull_min=2.0, bearish_exit="target",
                       bull_min_annual=None, dip_trigger="step", dip_basis="touch", reserve_pct=None)
STOCKS = """RELIANCE TCS HDFCBANK INFY ICICIBANK HINDUNILVR ITC SBIN BHARTIARTL KOTAKBANK LT AXISBANK
ASIANPAINT MARUTI SUNPHARMA TITAN ULTRACEMCO BAJFINANCE NESTLEIND WIPRO HCLTECH NTPC POWERGRID ONGC
TATASTEEL JSWSTEEL COALINDIA BAJAJFINSV TECHM GRASIM HINDALCO DRREDDY CIPLA EICHERMOT BRITANNIA
DIVISLAB HEROMOTOCO BPCL TATACONSUM""".split()

# ---------------- DATA ----------------
def get_data():
    import yfinance as yf
    begin = (pd.Timestamp(START) - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    raw = yf.download([s + ".NS" for s in STOCKS] + [BENCH], start=begin, auto_adjust=False, actions=True, progress=False)
    px = raw["Close"].dropna(axis=1, how="all").ffill(limit=5)   # raw (split-adjusted) closes; dividends are added separately
    div = raw["Dividends"].reindex_like(px).fillna(0) if "Dividends" in raw else px * 0
    for t in (px, div): t.columns = [c.replace(".NS", "") for c in t.columns]
    return px, div

# ---------------- METRICS ----------------
def xirr(flows):
    """Annual rate that makes all dated cash flows add up to zero. flows = [(date, amount)], money in is negative."""
    t0 = flows[0][0]; ts = [(d - t0).days / 365 for d, _ in flows]; a = [x for _, x in flows]
    f = lambda r: sum(x / (1 + r) ** t for x, t in zip(a, ts))
    lo, hi = -0.99, 20.0
    if f(lo) * f(hi) > 0: return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0: hi = mid
        else: lo = mid
    return (lo + hi) / 2

def summarize(eq, wd):
    """eq = daily net worth, wd = {date: rupees withdrawn}. Profit = (ending net worth + withdrawals) - initial capital."""
    final = float(eq.iloc[-1]); W = float(sum(wd.values())); profit = final + W - CAPITAL
    months = max((eq.index[-1] - eq.index[0]).days / 30.4375, 1)
    wealth = eq + (pd.Series(wd).reindex(eq.index).fillna(0).cumsum() if wd else 0)
    flows = [(eq.index[0], -CAPITAL)] + [(d, a) for d, a in sorted(wd.items()) if a > 0] + [(eq.index[-1], final)]
    return dict(profit=round(profit), avg_monthly=round(profit / months), xirr=xirr(flows), total=profit / CAPITAL,
                maxdd=float((wealth / wealth.cummax() - 1).min()), final=round(final), withdrawals=round(W), months=round(months, 1))

def weekly(c): return [[d.strftime("%Y-%m-%d"), round(float(v))] for d, v in c.resample("W").last().dropna().items()]

def mk_monthly(mon):
    out, pe = [], CAPITAL
    for k in sorted(mon):
        x = mon[k]; x["ret"] = (x["equity"] + x.pop("wd")) / pe - 1; pe = x["equity"]
        out.append({a: (round(b, 4) if a == "ret" else round(b) if isinstance(b, float) else b) for a, b in x.items()})
    return out

def new_month(mon, d):
    ms = d.strftime("%Y-%m")
    return ms, mon.setdefault(ms, dict(month=ms, closed=0, trade_pnl=0.0, interest=0.0, dividends=0.0, equity=0.0, wd=0.0))

# ---------------- STYLE 1: tranche engine (rules come from the strategy's own SETTINGS) ----------------
def simulate(px, sg_all, dok_all, dent_all, div, cfg):
    MX, TRn, BN, ST, BR, BL, MODE = cfg["max_stocks"], cfg["tranches"], cfg["bullish_tranches"], cfg["step"] / 100, cfg["bear_target"] / 100, cfg["bull_min"], cfg["bearish_exit"]
    DTR, DB, BA, RS = cfg["dip_trigger"], cfg["dip_basis"], cfg["bull_min_annual"], cfg["reserve_pct"]
    BL = None if BL is None else BL / 100; DS = TRn - BN
    pxf = px.ffill(); days = [d for d in px.index if d >= pd.Timestamp(START)]
    cash, held, log, divs, eq, mon, wd = CAPITAL, {}, [], [], [], {}, {}
    interest = dsum = realized = withdrawn = 0.0; prev = pms = None
    def buy(s, kind, price, amt, d):
        h = held.setdefault(s, dict(lots=[], last=0.0, low=0.0))
        pool = range(1, BN + 1) if kind == "Bullish" else range(BN + 1, TRn + 1)
        free = sorted(set(pool) - {l["slot"] for l in h["lots"]})
        if not free: return False
        tgt = (None if BL is None else float(price) * (1 + BL)) if kind == "Bullish" else float(price) * (1 + BR)
        lot = dict(symbol=s, type=kind, slot=free[0], buy_date=d.strftime("%Y-%m-%d"), buy_price=float(price), shares=amt / (1 + COST) / price,
                   invested=amt, target=tgt, sell_date=None)
        h["lots"].append(lot); h["last"] = h["low"] = float(price); log.append(lot); return True
    for d in days:
        ms, m = new_month(mon, d)
        if prev is not None:
            i = cash * IDLE * (d - prev).days / 365; cash += i; interest += i; m["interest"] += i
        if WITHDRAW > 0 and pms is not None and ms != pms:      # monthly withdrawal comes out of idle cash only (no forced selling)
            a = min(WITHDRAW, max(cash, 0.0)); cash -= a; withdrawn += a; wd[d] = a; m["wd"] += a
        pms = ms; prev = d; row = pxf.loc[d]; sg = sg_all.loc[d]; dok = dok_all.loc[d]; dent = dent_all.loc[d]; dv = div.loc[d]
        for s, h in list(held.items()):
            p = row[s]
            if np.isnan(p): continue
            if dv.get(s, 0) > 0:
                q = sum(l["shares"] for l in h["lots"]); a = q * dv[s]; cash += a; dsum += a; m["dividends"] += a
                divs.append(dict(date=d.strftime("%Y-%m-%d"), symbol=s, per_share=round(float(dv[s]), 2), shares=round(q, 2), amount=round(a)))
            for l in list(h["lots"]):
                if l["type"] == "Bullish" and BA is not None:      # annualised minimum return (after costs) for the days held
                    net = l["shares"] * p * (1 - COST) / l["invested"] - 1
                    ready = net >= (1 + BA / 100) ** (max((d - pd.Timestamp(l["buy_date"])).days, 1) / 365) - 1
                else: ready = l["target"] is None or p >= l["target"]
                if ready and ((l["type"] == "Bearish" and MODE == "target") or not sg[s]):
                    out = l["shares"] * p * (1 - COST); l.update(sell_date=d.strftime("%Y-%m-%d"), sell_price=float(p), pnl=out - l["invested"])
                    cash += out; realized += l["pnl"]; m["closed"] += 1; m["trade_pnl"] += l["pnl"]; h["lots"].remove(l)
            if not h["lots"]: del held[s]
            else: h["low"] = min(h["low"], float(p))
        base = CAPITAL + realized + interest + dsum - withdrawn         # everything earned is reinvested: tranche sizes compound
        size_b = size_d = base / (MX * TRn)
        if RS is not None: size_b = base * (1 - RS / 100) / (MX * max(BN, 1)); size_d = base * (RS / 100) / (MX * max(DS, 1))
        for s, h in list(held.items()):                    # averaging (dip) tranches
            if DS == 0 or np.isnan(row[s]) or cash < size_d or sum(l["type"] == "Bearish" for l in h["lots"]) >= DS: continue
            trig = dent[s] if DTR == "signal" else ((h["low"] if DB == "touch" else row[s]) <= h["last"] * (1 - ST) and dok[s])
            if trig and buy(s, "Bearish", row[s], size_d, d): cash -= size_d
        for s in sg_all.columns:                           # fresh entries
            p = row[s]; h = held.get(s)
            if np.isnan(p) or (h is None and len(held) >= MX): continue
            if BN > 0 and sg[s] and sum(l["type"] == "Bullish" for l in (h["lots"] if h else [])) < BN and cash >= size_b:
                if buy(s, "Bullish", p, size_b, d): cash -= size_b
            elif h is None and DS > 0 and dent[s] and cash >= size_d:
                if buy(s, "Bearish", p, size_d, d): cash -= size_d
        val = sum(l["shares"] * (row[s] if not np.isnan(row[s]) else h["last"]) for s, h in held.items() for l in h["lots"])
        eq.append(cash + val); m["equity"] = cash + val
    c = pd.Series(eq, index=days); last = pxf.iloc[-1]; unreal = 0.0; trades = []
    for l in log:
        is_open = l["sell_date"] is None; lp = float(last[l["symbol"]]) if not np.isnan(last[l["symbol"]]) else l["buy_price"]
        pnl = l["shares"] * lp - l["invested"] if is_open else l["pnl"]; unreal += pnl if is_open else 0
        end = days[-1] if is_open else pd.Timestamp(l["sell_date"])
        trades.append(dict(symbol=l["symbol"], type=l["type"], slot=l["slot"], buy_date=l["buy_date"], buy_price=round(l["buy_price"], 2),
                           shares=round(l["shares"], 2), invested=round(l["invested"]), target=None if l["target"] is None else round(l["target"], 2),
                           sell_date="Open" if is_open else l["sell_date"], sell_price=None if is_open else round(l["sell_price"], 2),
                           pnl=round(pnl), ret=pnl / l["invested"], days=(end - pd.Timestamp(l["buy_date"])).days, status="Open" if is_open else "Closed"))
    by, dstock, stocks = {}, {}, []
    for t in trades: by.setdefault(t["symbol"], []).append(t)
    for e in divs: dstock[e["symbol"]] = dstock.get(e["symbol"], 0) + e["amount"]
    for s, ts in by.items():
        cl = [t for t in ts if t["status"] == "Closed"]
        stocks.append(dict(symbol=s, trades=len(ts), closed=len(cl), wins=sum(t["pnl"] > 0 for t in cl), realized=sum(t["pnl"] for t in cl),
                           unrealized=sum(t["pnl"] for t in ts if t["status"] == "Open"), dividends=dstock.get(s, 0), avg_days=round(float(np.mean([t["days"] for t in ts])))))
    stocks.sort(key=lambda x: x["realized"] + x["unrealized"] + x["dividends"], reverse=True)
    tr = sum(t["pnl"] for t in trades if t["status"] == "Closed")
    extra = dict(trade_realized=round(tr), interest=round(interest), dividends=round(dsum), unrealized=round(unreal), total_realized=round(tr + interest + dsum),
                 closed=sum(t["status"] == "Closed" for t in trades), trades_total=len(trades), base=round(CAPITAL + tr + interest + dsum - withdrawn))
    trades.sort(key=lambda t: t["buy_date"], reverse=True)
    bl = "sell on signal off, any profit" if BL is None else f"bullish min profit {BL*100:g}%"
    if BA is not None: bl += f", bullish min {BA:g}% a year"
    dip = "bought on its own signal" if DTR == "signal" else f"step {ST*100:g}% ({'price today' if DB == 'current' else 'low since last buy'})"
    rs_ = "" if RS is None else f", {100-RS:g}% of capital for first buys / {RS:g}% for averaging"
    rules = (f'Own rules: {MX} stocks x {TRn} tranches ({BN} bullish + {DS} dip{rs_}), dip tranches {dip}, dip target {BR*100:g}%, {bl}, '
             f'dip tranches exit by {"their own target" if MODE == "target" else "signal + target"}')
    return dict(mode="tranche", rules=rules, eq=c, wd=wd, extra=extra, trades=trades[:1000], monthly=mk_monthly(mon), stocks=stocks, dividends=divs[::-1][:1000])

# ---------------- STYLE 2: target-weight engine (strategy decides its own allocation) ----------------
def simulate_w(px, w, div):
    pxf = px.ffill(); days = [d for d in px.index if d >= pd.Timestamp(START)]
    r = pxf.pct_change().fillna(0); dy = (div / pxf.shift(1)).replace([np.inf, -np.inf], 0).fillna(0)
    V, eq, wd, mon = CAPITAL, [], {}, {}; interest = dsum = 0.0; prev = pms = None; pw = pd.Series(0.0, index=w.columns)
    for d in days:
        ms, m = new_month(mon, d); wt = w.loc[d]; inv = float(wt.sum()); gap = (d - prev).days if prev is not None else 0
        g = V * float((wt * r.loc[d]).sum()); dv_ = V * float((wt * dy.loc[d]).sum()); i_ = V * (1 - inv) * IDLE * gap / 365
        c = V * COST * float((wt - pw).abs().sum()); V += g + dv_ + i_ - c
        dsum += dv_; interest += i_; m["dividends"] += dv_; m["interest"] += i_; m["trade_pnl"] += g - c
        if WITHDRAW > 0 and pms is not None and ms != pms:
            a = min(WITHDRAW, V * (1 - inv)); V -= a; wd[d] = a; m["wd"] += a
        pms = ms; prev = d; pw = wt; eq.append(V); m["equity"] = V
    extra = dict(trade_realized=None, interest=round(interest), dividends=round(dsum), unrealized=None, total_realized=None, closed=None, trades_total=None, base=round(V))
    return dict(mode="weights", rules="Own rules: target-weight rebalancing (the strategy sets its own allocation)", eq=pd.Series(eq, index=days), wd=wd,
                extra=extra, trades=[], monthly=mk_monthly(mon), stocks=[], dividends=[])

# ---------------- MAIN ----------------
def table(x, like, default):   # align a strategy's True/False table, act the day AFTER the signal (no peeking at the future)
    return x.reindex(like.index).reindex(columns=like.columns).fillna(default).astype(bool).shift(1, fill_value=default)

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
            if hasattr(mod, "signals"):
                cfg = {**ENGINE_DEFAULTS, **getattr(mod, "SETTINGS", {})}
                if not 0 <= cfg["bullish_tranches"] <= cfg["tranches"]: raise ValueError("bullish_tranches must be between 0 and tranches")
                sg = table(mod.signals(stocks.copy()), stocks, False)
                dok = table(mod.dip_ok(stocks.copy()), stocks, False) if hasattr(mod, "dip_ok") else sg
                dent = table(mod.dip_entry(stocks.copy()), stocks, False) if hasattr(mod, "dip_entry") else sg & False
                out = simulate(stocks, sg, dok, dent, dv, cfg)
            else:
                w = mod.weights(stocks.copy()).reindex(stocks.index).reindex(columns=stocks.columns).fillna(0.0).clip(lower=0.0)
                out = simulate_w(stocks, w.div(w.sum(axis=1).clip(lower=1.0), axis=0).shift(1, fill_value=0.0), dv)
            eq, wd, extra = out.pop("eq"), out.pop("wd"), out.pop("extra")
            res.append(dict(name=mod.NAME, m={**summarize(eq, wd), **extra}, curve=weekly(eq), **out))
        except Exception as e:
            broken.append(dict(file=os.path.basename(f), problem=str(e)[:200]))
    res.sort(key=lambda x: x["m"]["xirr"] if x["m"]["xirr"] is not None else -9, reverse=True)   # highest XIRR first
    board = [dict(rank=i + 1, name=r["name"], profit=r["m"]["profit"], avg_monthly=r["m"]["avg_monthly"], xirr=r["m"]["xirr"]) for i, r in enumerate(res)]
    b = None
    if bench is not None:
        c = CAPITAL * (1 + bench.pct_change().fillna(0).loc[START:]).cumprod(); b = dict(name="Nifty 50 index (for comparison)", m=summarize(c, {}), curve=weekly(c))
    os.makedirs("docs", exist_ok=True)
    json.dump(dict(updated=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), params=dict(start=START, end=END, capital=CAPITAL, withdraw=WITHDRAW, benchmark=BENCH,
              cost=COST, idle=IDLE), leaderboard=board, benchmark=b, strategies=res, broken=broken), open("docs/results.json", "w"))
    print("Done:", [(r["rank"], r["name"], r["profit"], r["avg_monthly"], None if r["xirr"] is None else round(r["xirr"] * 100, 1)) for r in board], "broken:", broken)

if __name__ == "__main__":
    main()
  
