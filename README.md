# MNQ Pattern Trading Toolkit

A research-grade Python toolkit that **finds patterns in Micro E-mini
Nasdaq-100 (MNQ/NQ) futures, backtests multiple strategies honestly, and emits
a concrete trade plan with take-profit and stop-loss levels.**

> ⚠️ **Read [`RESEARCH.md`](RESEARCH.md) first.** It is the deep-dive that
> drives every design choice here. The honest conclusion: **no strategy is
> guaranteed profitable.** This tool is for research/education, not financial
> advice. Futures can lose more than you put in. Paper-trade for months before
> risking real money.

## The daily workflow (what you asked for)
Read MNQ's data for the day and get a take-profit + stop set for you:
```bash
python -m mnq.cli plan --equity 50000        # auto-pulls the latest bar
```
You get one of two things: **a concrete LONG plan** (entry, stop, take-profit,
size, plus a "ride winners" trailing rule) or **"NO TRADE TODAY"**. The
headline strategy is selective on purpose — about **1 trade per week** — because
you said you'd rather wait for a good setup than force one daily.

## What it does
- **Pulls real data** for `NQ=F` (same index as MNQ, 1/10th size) from Yahoo —
  25 yrs of daily, ~2 yrs hourly, ~60 days of 15-min — with caching + retry.
- **Detects patterns**: ATR, VWAP, RSI, Donchian, relative volume, plus
  candlestick patterns (engulfing, pin bar, doji, wide-range) used as filters.
- **Five strategies.** The default is built for *monthly* profitability:
  | Strategy | Style | Profile | OOS verdict |
  |---|---|---|---|
  | **`trend_pullback`** ⭐ | buy dips in an uptrend, ride with an ATR trail (daily) | **PF 1.92, max DD −5.6%, monthly Sharpe 0.70, ~1 trade/wk** | ✅ best OOS edge (+0.35R) |
  | `rsi_reversion` | mean-reversion (daily) | high win rate, 51% green months | ⚠️ marginal OOS (overfit risk) |
  | `donchian_trend` | breakout trend-following (daily) | greater R:R, lumpy | ✅ survives walk-forward |
  | `orb` | opening-range breakout (intraday) | momentum | ❓ too little free data to validate |
  | `vwap_reversion` | intraday fade | — | ❌ negative in this regime |
- **Backtests** with realistic MNQ economics ($2/pt), commission, slippage,
  pessimistic stop-fills, risk-based sizing, **trailing stops + time stops**.
- **Monthly report** (`% positive months`, best/worst month, monthly Sharpe) so
  you optimize for the thing you actually care about.
- **Walk-forward validates** to expose curve-fitting.

## Other commands
```bash
python -m mnq.cli backtest --equity 50000          # default strategy, 25-yr stats + monthly
python -m mnq.cli compare  --equity 50000          # all five strategies side by side
python -m mnq.cli walkforward                       # out-of-sample validation
python -m mnq.cli plan --strategy rsi_reversion     # try the high-win-rate variant
```
`--risk 0.01` sets risk-per-trade; `--refresh` forces a re-download.

## Example plan output (a real past trigger)
```
[2026-02-16] MNQ — 🟢 LONG
  Entry (ref)  : 24,767.75
  STOP LOSS    : 23,245.00   (1,523 pts  =  $3,046 on 1 ctr)
  TAKE PROFIT  : 29,336.00   (4,568 pts  =  $9,136)   [1 : 3.0 R]
  RIDE WINNERS : optional — instead of the fixed TP, trail the stop 1,523 pts
                 below the highest high since entry (backtests favor this).
  Time stop    : exit after ~40 bars if neither level hit.
  ** WARNING: 1 contract risks $3,046 (6% of $50,000) ... **
```

## Position sizing reality (important)
On the **daily** timeframe, NQ's ATR is large, so a 3×ATR stop is ~1,500 index
points = **~$3,000 risk per single MNQ contract**. That means:
- True 1%-risk sizing needs a big account (~$300k for 1 contract). The tool
  **warns you** whenever a stop is wider than your risk budget.
- Realistically: trade ~1 MNQ contract per ~$50k and accept ~5–6% risk per
  trade, **or** scale the account up, **or** use a tighter intraday setup.
- To chase higher returns, raise `--risk` — but drawdown scales with it. Don't
  oversize; that is how the 90% blow up.

## Layout
```
mnq/
  data.py         # download + cache NQ=F (retry/backoff), RTH session filter
  indicators.py   # ATR, VWAP, RSI, EMA/SMA, Donchian, relative volume, z-score
  patterns.py     # candlestick patterns (confluence filters only)
  strategies.py   # trend_pullback ⭐, rsi_reversion, donchian_trend, orb, vwap_reversion
  backtest.py     # event-driven, no-lookahead, MNQ economics, costs, trailing/time stops
  metrics.py      # win rate, expectancy(R), profit factor, Sharpe, max DD, monthly report
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
