# Strategy card: Trend Pullback

## Signal checklist
- [ ] Stock close > 50 SMA > 200 SMA.
- [ ] 50 SMA is higher than it was 10 sessions ago.
- [ ] Close is within ±1.5% of 20 EMA.
- [ ] RSI(14) is between 40 and 60.
- [ ] Close is above the previous close.
- [ ] NIFTY 50 is above its 50 SMA.

## Trade management
- Entry: next trading day's close after the signal (as implemented by this engine).
- Initial stop: entry price minus 2 × the prior 14-session average absolute close-to-close move.
- Target: 2.5R.
- Trend exit: close below the 50 SMA.
- Max positions: 10.
- Tranches: 1; no averaging down.

## Important interpretation
The stop input is a close-to-close volatility proxy, **not ATR**. This repository does not currently download High and Low prices. Stop/target execution is approximated at the close after a breach. The strategy's equal allocation is inherited from the engine and is not position-sized to a fixed fraction of account risk.
