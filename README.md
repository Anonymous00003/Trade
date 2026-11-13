# Trade-main: Multi-strategy Indian equity backtester

This repository downloads daily market data with `yfinance`, runs every strategy in `strategies/`, writes `docs/results.json`, and displays the results in a GitHub Pages dashboard.

## Important existing portfolio-wide assumptions

These are inherited from `run.py` and are intentionally unchanged:

- Initial capital: **₹15,00,000 (15 lakh)**, not ₹1,50,000.
- Estimated transaction cost: **0.2% on each buy and each sell**. Taxes are not separately modelled.
- Idle cash return: **6.5% per year**, modelled as a flat rate.
- Benchmark: **NIFTY 50 (`^NSEI`)**.
- Backtest start: **2019-01-01** by default.
- Universe: a fixed list of current NIFTY 50 constituents in `run.py`; it is not a historical point-in-time constituent universe.
- Data: Yahoo Finance via `yfinance`; this project currently uses daily close prices and dividends.

The ₹15 lakh is the engine's shared starting capital for comparing strategies. It is not a recommendation to deploy that amount. To simulate a different account size, change `CAPITAL` in `run.py` before running the workflow. Every strategy is compared using the same capital and cost assumptions.

## Added strategy

`strategies/trend_pullback.py` adds **Trend Pullback (20 EMA + 50/200 trend, 2.5R)**.

Rules:
1. Stock close above 50-day SMA, and 50-day SMA above 200-day SMA.
2. 50-day SMA rising versus 10 sessions earlier.
3. Close within ±1.5% of 20-day EMA (close-only pullback approximation).
4. RSI(14) between 40 and 60.
5. Close above previous close as confirmation.
6. NIFTY 50 must close above its 50-day SMA.
7. Initial stop distance is 2 × 14-session mean absolute close-to-close move; this is a **volatility proxy, not true ATR**.
8. Profit target is 2.5 times the initial stop distance.
9. Exit also occurs when the stock closes below its 50-day SMA.
10. One tranche per stock, up to 10 concurrent stocks; no averaging down.

### Execution and limitations

- Signals are acted on the following trading day, using the engine's one-day signal shift.
- Stop and target exits are simulated at the daily closing price after the level is crossed. The engine does not have intraday OHLC execution, so gap risk and exact stop fills are not modelled.
- The stop distance is fixed from data available before the entry day.
- Existing equal-tranche allocation is retained: approximately 10% of the portfolio per first entry when 10 slots are available. This is **not** a 0.5%-of-equity risk-sized position model. Rupee risk varies with each stock's stop distance.
- The engine's shared 0.2% cost is applied per side. Additional statutory taxes, market impact and realistic spread/slippage may be higher.
- The 6.5% idle-cash interest assumption can materially affect results.
- Current constituents used back through 2019 create survivorship bias. Yahoo Finance data can contain missing/adjusted-data issues.
- The strategy is a research candidate, not a proven profitable system or a personal investment recommendation.

## Run locally

```bash
python -m pip install -r requirements.txt
python run.py
```

Then open `docs/index.html` in a browser. The dashboard reads `docs/results.json`.

## Enable GitHub Pages

1. Push this repository to GitHub.
2. Open **Settings → Pages**.
3. Under Build and deployment, choose **Deploy from a branch**.
4. Select branch `main` (or your default branch) and folder `/docs`.
5. Save. GitHub will publish the dashboard URL shown on that page.

The existing `.github/workflows/daily.yml` runs after the Indian market close on weekdays (17:00 IST), updates `docs/results.json`, and commits it. You can also use **Actions → Daily update → Run workflow** to set a start date, end date, and monthly withdrawal.

## How to interpret results

Do not select a strategy solely by the highest XIRR. Check:
- Maximum drawdown and length of drawdown.
- Number of closed trades and trade count.
- Profit factor / average win / average loss (the current dashboard does not calculate all of these).
- Performance by bull, bear and sideways regimes.
- Results after realistic costs.
- Out-of-sample and walk-forward results.

A valid next research step is to split the history chronologically (for example, earlier years for development and later years for out-of-sample testing), then repeat with different market regimes. Avoid repeatedly changing parameters until the historical result looks best; that is curve fitting.
