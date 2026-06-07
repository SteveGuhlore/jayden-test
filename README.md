# MNQ Pattern Trading Toolkit

A research-grade Python toolkit that **finds patterns in Micro E-mini
Nasdaq-100 (MNQ/NQ) futures, backtests multiple strategies honestly, and emits
a concrete trade plan with take-profit and stop-loss levels.**

> ⚠️ **Read [`RESEARCH.md`](RESEARCH.md) first.** It is the deep-dive that
> drives every design choice here. The honest conclusion: **no strategy is
> guaranteed profitable.** This tool is for research/education, not financial
> advice. Futures can lose more than you put in. Paper-trade for months before
> risking real money.

## What it does
- **Pulls real data** for `NQ=F` (same index as MNQ, 1/10th size) from Yahoo —
  25 yrs of daily, ~2 yrs hourly, ~60 days of 15-min — with caching + retry.
- **Detects patterns**: ATR, VWAP, RSI, Donchian, relative volume, plus
  candlestick patterns (engulfing, pin bar, doji, wide-range) used as filters.
- **Four strategies**, covering both roads to a positive edge:
  | Strategy | Style | Edge road | OOS verdict |
  |---|---|---|---|
  | `donchian_trend` | trend-following (daily) | **greater R:R** (~42% win, +0.26R) | ✅ survives walk-forward |
  | `rsi_reversion` | mean-reversion (daily) | **positive win rate** (~60% win) | ⚠️ marginal OOS (overfit risk) |
  | `orb` | opening-range breakout (intraday) | momentum | ❓ too little free data to validate |
  | `vwap_reversion` | intraday fade | mean-reversion | ❌ negative in this regime |
- **Backtests** with realistic MNQ economics ($2/pt), commission, slippage,
  pessimistic stop-fills, risk-based sizing, and EOD exits for intraday.
- **Walk-forward validates** to expose curve-fitting (this is what flagged
  RSI-2 as overfit).
- **Generates a live trade plan**: side, entry, **stop-loss, take-profit**, R:R,
  contracts, and $ risk/reward — with a warning when a stop is too wide for your
  account.

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Today's trade plan with TP & SL (trend system, robust OOS):
python -m mnq.cli signal --strategy donchian_trend --equity 50000

# High-win-rate mean-reversion plan:
python -m mnq.cli signal --strategy rsi_reversion --equity 50000

# Backtest one strategy / compare all / validate out-of-sample:
python -m mnq.cli backtest --strategy donchian_trend
python -m mnq.cli compare
python -m mnq.cli walkforward --strategy donchian_trend
```
Add `--refresh` to re-download data, `--risk 0.01` to set risk-per-trade.

## Example output
```
[2026-06-04] MNQ — LONG SIGNAL
  Entry (ref) : 29,026.50
  Stop loss   : 27,350.25   (1,676 pts risk)
  Take profit : 31,029.00   (2,002 pts target)
  Risk:Reward : 1 : 2.00
  Size        : 1 MNQ contract(s)  (risk $3,352 / reward $4,004)
  Note        : ** WARNING: 1 contract risks 34% of a $10,000 account ... **
```
That warning is a feature: daily NQ stops are wide, so daily swing trading MNQ
realistically needs ~$50k+ — otherwise use a tighter intraday strategy.

## Layout
```
mnq/
  data.py         # download + cache NQ=F (retry/backoff), RTH session filter
  indicators.py   # ATR, VWAP, RSI, EMA/SMA, Donchian, relative volume, z-score
  patterns.py     # candlestick patterns (confluence filters only)
  strategies.py   # orb, vwap_reversion, donchian_trend, rsi_reversion
  backtest.py     # event-driven, no-lookahead, MNQ economics, costs, sizing
  metrics.py      # win rate, expectancy(R), profit factor, Sharpe, max DD
  walkforward.py  # out-of-sample validation (anti-overfitting)
  signal.py       # live trade plan: entry / stop / target / size
  cli.py          # command-line entry point
RESEARCH.md       # the deep-dive research report (start here)
```

## Honest limitations
- Free Yahoo data limits intraday history (no real 5-min ORB validation; daily
  futures are continuous front-month with roll artifacts).
- Backtested edges are **small and can decay**; past performance ≠ future.
- This is a decision-support and research tool, **not** an autotrader and **not**
  financial advice.
