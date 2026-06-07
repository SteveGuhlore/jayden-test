# MNQ Pattern Trading — Deep-Dive Research & Honest Findings

*Compiled June 2026. Sources are linked inline. This is a research/education
tool, not financial advice. Trading futures involves substantial risk of loss.*

This document answers the question: **what actually works for building a
profitable, consistent trading strategy on Micro E-mini Nasdaq-100 futures
(MNQ)?** It combines (a) a literature review across academic and practitioner
sources, and (b) my own backtests on real NQ data using the code in this repo.
The headline conclusion is delivered up front, because it matters:

> **There is no strategy that is reliably, guaranteed profitable. The honest,
> evidence-based finding is that most apparent edges shrink dramatically once
> you test them out-of-sample and subtract realistic costs. The edges that do
> survive are small, lumpy, and require discipline + adequate capital. The
> "secret" is not a magic pattern — it is positive expectancy, strict risk
> control, and not blowing up.** Anyone promising consistent guaranteed profit
> is selling something.

---

## 0. The math that governs everything: expectancy

Every strategy lives or dies by **expectancy** — the average $ (or "R", risk
units) you make per trade:

```
Expectancy (R) = WinRate × AvgWin/Risk  −  LossRate × AvgLoss/Risk
```

Two independent levers make this positive, and they map exactly onto what you
asked for:

1. **A positive win rate** (win more often than you lose) — the *mean-reversion*
   path. You can be profitable at a 1:1 reward:risk if you win >50% of the time.
2. **A greater reward:risk ratio** (win big, lose small) — the *trend-following*
   path. A trend system can win only ~35% of the time and still be very
   profitable if winners are 3× the size of losers.

A take-profit (TP) target that is 2× the stop distance keeps expectancy
positive even at a **50% win rate**; a 1:1 system needs a win rate above 50%
([Alchemy Markets on R:R](https://alchemymarkets.com/education/guides/risk-reward-ratio/)).
This is why this project implements **both** a high-RR trend system and a
high-win-rate mean-reversion system — they are the two mathematically valid
roads to a positive edge.

---

## 1. The instrument: MNQ contract economics

MNQ tracks the **exact same Nasdaq-100 index as the full-size NQ** — it is
1/10th the size, so patterns and price action are identical and we can backtest
on the longer/cleaner `NQ=F` series.

| Spec | Value |
|---|---|
| Multiplier | **$2 × index** |
| Tick size | 0.25 index points |
| Tick value | **$0.50** |
| 1 point | **$2.00** per contract |
| Size vs NQ | 1/10th (10-pt move = $20 vs $200) |
| Intraday margin | as low as ~$50–$1,825/contract depending on broker |

Sources: [CME Group MNQ](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.html),
[QuantVPS MNQ tick value](https://www.quantvps.com/blog/mnq-tick-value),
[Ironbeam contract specs](https://www.ironbeam.com/knowledge-base/micro-e-mini-nasdaq-100-futures-mnq-contract-specifications/).

**Practical capital reality (a finding from my own backtests):** daily-bar swing
strategies on the Nasdaq-100 need wide stops (an ATR-based stop is often
1,000–1,700 index points = **$2,000–$3,400 risk per single contract**). On a
$10k account you *cannot* risk only 1% on one MNQ contract — the minimum
position already risks 20–34%. **Daily swing trading MNQ realistically needs a
~$50k+ account, or you must trade intraday with much tighter stops.** The
signal tool in this repo prints a hard warning when a stop is too wide for your
account.

---

## 2. The U-shaped day & market microstructure

Index-futures intraday behaviour has a robust, repeatedly-documented structure:

- **U-shaped volatility/volume**: both are high at the open, sag at midday
  ("lunch"), and rise into the close. This is one of the most stable empirical
  regularities across markets and decades
  ([Admati & Pfleiderer-style U-effect, arXiv survey](https://arxiv.org/pdf/1009.4785)).
- **Intraday momentum**: the first half-hour return and the second-to-last
  half-hour return have predictive power over the last half-hour return — a
  genuinely peer-reviewed effect ([Gao, Han, Li & Zhou, *Market Intraday
  Momentum*, JFE](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351)).

**Implication:** the open (09:30–10:30 ET) and the close are where edge and
risk concentrate. The opening range is therefore a sensible place to hunt for
breakouts, and midday chop is to be avoided.

---

## 3. The strategies, ranked by evidence

### 3a. Opening Range Breakout (ORB) — strong literature, data-limited for me
The best-documented intraday edge. The cornerstone study, **Zarattini & Aziz,
*Can Day Trading Really Be Profitable?* (SSRN 4416622)**, defines a crisp,
reproducible rule set:

- Opening range = the **first 5 minutes** of the RTH session.
- Enter at the start of the 2nd 5-min bar in the direction of the first bar.
- **Stop** = the opposite extreme of the 5-min range.
- **Target** = **10× risk** (10R), otherwise exit at the close (EOD).
- **Size each trade so the stop = 1% of capital.**
- Reported: QQQ ~675% (2016–2023), Sharpe ~1.12, alpha ~33%/yr net of
  commissions; the 3× ETF (TQQQ) version ~1,484%.

Sources: [SSRN abstract](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622),
[CXO Advisory review](https://www.cxoadvisory.com/technical-trading/day-trading-with-an-opening-range-breakout-strategy/),
[The Robust Trader breakdown](https://therobusttrader.com/can-day-trading-really-be-profitable-rules-backtest-statistics-performance-analysis/).

**Critical caveats from the literature and my tests:**
- The paper trades **single stocks "in play"** (elevated relative volume on
  news), not the index. The edge concentrates in high-momentum names; applying
  raw ORB to the index is materially weaker.
- It assumes **no slippage / no spread** — explicitly unrealistic.
- Practitioner consensus is that index ORB has **degraded**: high-volatility
  opens produce wide ranges and more false breakouts
  ([QuantifiedStrategies](https://www.quantifiedstrategies.com/opening-range-breakout-strategy/)).
- **My result:** a 30-min ORB on 15-min NQ data looked great (52% win, PF 1.33,
  Sharpe 1.86) — but only over **60 days (46 trades)**, which is statistically
  meaningless. On 2 years of hourly data the edge collapsed to **PF ~1.05**, and
  walk-forward gave only 4 out-of-sample trades. **Verdict: promising in theory,
  but I cannot validate it because Yahoo only provides ~60 days of 5–15 min
  data. It needs a proper 5-min tick feed and forward testing.**

### 3b. Trend-following / Donchian breakout — best out-of-sample edge (the "greater RR" road)
Time-series momentum is one of the most robust anomalies in all of finance,
documented across 75+ years and every asset class
([Moskowitz, Ooi & Pedersen, *Time Series Momentum*](https://www.sciencedirect.com/science/article/abs/pii/S0304405X11002613)).

**My backtest (NQ daily, ~25 years, 6,493 bars):** a 55-day Donchian breakout,
ATR(14)×2.5 stop, 2R target, traded only with the 100-day trend:
- Win rate ~42%, **expectancy +0.26R**, profit factor **1.39**, max DD ~22%.
- **Walk-forward (out-of-sample, params re-chosen each fold): expectancy +0.21R,
  PF 1.37.** This is the *only* strategy whose edge largely survived honest
  out-of-sample testing. Returns are **lumpy** — a few big winners carry it,
  which is the nature of trend following.

### 3c. RSI-2 mean reversion + 200-day filter — best win rate (the "positive win rate" road)
"Buy the dip in an uptrend." Short-period RSI reversion (Connors-style),
restricted to longs above the 200-day SMA.

**My backtest (NQ daily, ~25 years):** RSI(2)<10, long only above 200-SMA,
ATR×3 stop, 2R target:
- **Win rate ~60%** (at 1:1) up to 47% (at 2:1), expectancy **+0.42R**, profit
  factor **1.93**, max DD ~13% — *the best-looking full-sample numbers in the
  whole project.*
- **BUT walk-forward deflated it to PF ~1.01 (essentially breakeven)**, with
  wildly inconsistent folds (−1.0R, +0.7R, +0.1R…). **This is the single most
  important lesson in this repo:** a strategy can look spectacular on the full
  sample and be nearly worthless out-of-sample. The full-sample result was
  substantially **curve-fit**.

### 3c′. Trend pullback ("buy the dip in an uptrend, ride the trend") — the monthly workhorse ⭐
This is the strategy built specifically for the goal of *monthly* profitability
with ~weekly trade frequency. It fuses the two robust ideas above: the
**long-bias / trend regime** of trend-following with the **high-hit-rate entry**
of mean reversion, then exits with a **chandelier ATR trailing stop** so winners
run (capturing the Nasdaq's upward drift) while losers are cut at a fixed ATR
stop.

- Regime: only long when close > 200-day SMA. Trigger: RSI(4) dips < 35 (a
  pullback, not a crash). Stop: 3×ATR. Exit: 3×ATR trailing stop + 40-bar time
  stop. No fixed target by default.
- **My backtest (NQ daily, ~25 years):** win rate ~45%, expectancy **+0.24R**,
  **profit factor 1.92**, **max drawdown −5.6%** (at 1% risk sizing), **monthly
  Sharpe 0.70**, ~1.1 trades/month, **47% of months green** with the average
  month positive and a strongly right-skewed distribution (best month dwarfs the
  worst).
- **Walk-forward (out-of-sample): expectancy +0.35R, profit factor 1.44** — the
  best out-of-sample result of any strategy in this repo. Folds are lumpy
  (a strong fold carries it), which is inherent to ~weekly trading on one
  instrument.
- **Robustness:** the entire parameter neighborhood (RSI 30–35, stop 2–3×ATR,
  trail 3–5×ATR) stays profitable — the hallmark of a real edge rather than a
  curve-fit.
- **Fixed-target variant:** taking a fixed **3R** target instead of trailing
  yields a **52% win rate, PF 1.69, 51% green months** — so the daily plan can
  hand you a concrete take-profit number *and* offer the trailing option for
  bigger runners. Both are backtest-validated.

- **Partial scale-out variant (`--partial`):** take 50% off at 2R, move the stop
  to breakeven, trail the rest. Backtested effect over 25 years: **green months
  47% → 52%, win rate 45% → 53%, median month −$28 → +$2,076**, higher monthly
  Sharpe. Crucially, per-trade expectancy is essentially **unchanged (~+0.24R)** —
  partials do **not** add edge or total profit; they *redistribute* it, banking
  gains in more calendar months and smoothing the curve. That is a pure
  **consistency** trade-off, and it requires ≥2 contracts to split.

**Why this is the default.** It is the best compromise between the two edge
roads, has the lowest drawdown, the best monthly Sharpe, the best out-of-sample
expectancy, and a trade cadence (~1/week) that matches trading only the best
setups. Caveat unchanged: the edge is real but modest, and OOS folds are lumpy —
forward-test it.

### 3d. VWAP mean reversion — failed in this regime
Fading stretches from session VWAP. Theory: price reverts to VWAP intraday
([MetroTrade](https://www.metrotrade.com/understanding-vwap-for-futures-trading/)).
**My result: negative (PF 0.35).** Fading a strongly trending instrument like
the Nasdaq is how you get run over — VWAP reversion only works in balanced/range
days, which a naive version cannot distinguish in advance.

---

## 4. Candlestick patterns: mostly folklore, used only as a filter
The academic evidence is **weak and mixed**:
- **Marshall, Young & Rose (2006)**: 28 candlestick patterns had **no edge** on
  Dow 30 stocks over a decade.
- **Orquín et al. (2020)**: no significant advantage on EUR/USD once costs were
  included. **Ho et al. (2021)**: most of 68 patterns did **worse than random**
  on crypto.
- Some positive results exist in **less-efficient markets** (Taiwan, Thailand)
  and for specific 3-day patterns (Caginalp & Laurent 1998), but they are
  market- and period-dependent and erode after costs.

Sources: [ScienceDirect review](https://www.sciencedirect.com/science/article/abs/pii/S1058330012000092),
[Taiwan study](https://www.sciencedirect.com/science/article/abs/pii/S0927538X13000735),
[Thailand study](https://journals.sagepub.com/doi/10.1177/2158244017736799).

**Decision:** this repo implements engulfing, hammer/pin-bar, doji, and
wide-range bars — but treats them **only as confluence filters** alongside
trend/volume context, never as standalone triggers. That is the only use the
evidence supports.

---

## 5. Stops, targets & position sizing

- **ATR-based stops** adapt to volatility; 1.5–3× ATR is the common, sensible
  range ([LuxAlgo](https://www.luxalgo.com/blog/5-atr-stop-loss-strategies-for-risk-control/),
  [QuantVPS](https://www.quantvps.com/blog/atr-stop-loss)). This repo uses ATR(14)
  for stop distance and a configurable R-multiple for the target.
- **Position sizing** = risk-based: each trade risks a fixed fraction (default
  1%) of equity to its stop. Formula: `contracts = (equity × risk%) ÷ (stop_pts ×
  $2)`.
- **Kelly criterion** gives the growth-optimal fraction `f = W − (1−W)/R`, but
  **full Kelly is far too volatile**; professionals use **½-Kelly or less**,
  capturing ~75% of the growth at much lower drawdown
  ([Kelly references](https://traderscalc.com/en/calculators/kelly-criterion/)).
  Our fixed-fractional 1% default is intentionally well below Kelly to control
  risk-of-ruin.

---

## 6. Why this is hard, and why most retail traders lose
This is the context for the humility throughout this document:

- **~72% of retail day traders lose money in a given year; 89–95% lose within a
  year; only ~1–4% are consistently profitable; ~1% survive 5 years.**
  ([Vetted Prop Firms summary of the literature](https://vettedpropfirms.com/what-percentage-of-day-traders-lose-money/),
  Barber & Odean / Brazilian day-trader studies.)
- Top causes: undercapitalization, no consistent process, emotional override of
  rules, and — critically — **costs**. For someone doing 8 round-trips/day,
  commissions + spread + slippage can consume a huge share of returns.

## 7. The methodology that keeps us honest
- **Walk-forward analysis**: optimize on in-sample, trade frozen params on the
  next unseen block, repeat. The stitched out-of-sample curve is the real test.
  This is what exposed RSI-2 as overfit
  ([Interactive Brokers](https://www.interactivebrokers.com/campus/ibkr-quant-news/the-future-of-backtesting-a-deep-dive-into-walk-forward-analysis/),
  [QuantInsti](https://blog.quantinsti.com/walk-forward-optimization-introduction/)).
- **Parameter robustness**: a real edge survives a ±perturbation of its
  parameters. Donchian stayed positive across the whole grid; that is a good
  sign. A result that only works at one exact parameter set is noise.
- **Realistic costs**: every backtest here charges commission per side **and**
  slippage in ticks, and assumes the **stop fills first** on ambiguous bars.

---

## 8. Bottom line & what I actually recommend
1. **`trend_pullback` is the default and my top pick for monthly profitability**
   — best out-of-sample expectancy (+0.35R), highest profit factor (1.92),
   lowest drawdown (−5.6%), best monthly Sharpe (0.70), and a ~1-trade/week
   cadence that matches taking only the best setups. Use the fixed 3R target for
   a clean TP, or trail to ride winners.
2. **Trend-following (Donchian)** — also positive out-of-sample with the
   strongest academic backing; lumpier and higher drawdown.
3. **Mean-reversion (RSI-2) gives the highest win rate** and is psychologically
   comfortable, but treat its full-sample numbers skeptically — forward-test small.
4. **ORB is theoretically the best intraday edge** but I could not validate it on
   free data; it deserves a proper 5-min feed and paper-trading.
5. **No guarantees exist.** Run everything on a **simulator/paper account for
   months** first. Mind the position-sizing reality (one daily MNQ contract risks
   ~$3k); don't oversize. The genuine edges are small but real — the framework is
   built so you keep testing honestly rather than fooling yourself.

*Full source list is linked inline above.*
