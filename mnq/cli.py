"""Command-line interface for the MNQ toolkit.

Examples:
    python -m mnq.cli signal                  # today's trade plan (TP/SL)
    python -m mnq.cli compare                 # backtest all strategies
    python -m mnq.cli walkforward             # out-of-sample validation
    python -m mnq.cli backtest --strategy orb --interval 15m
"""
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore")

from . import data as D
from . import strategies as S
from . import backtest as B
from . import metrics as M
from . import walkforward as W
from . import signal as SG

# Default, walk-forward-vetted configs per strategy.
DEFAULTS = {
    # Headline strategy: buy dips in an uptrend, ride with an ATR trail.
    # Best monthly profile + best out-of-sample edge in this repo.
    "trend_pullback": dict(interval="1d", intraday=False,
                           params=dict(rsi_p=4, rsi_buy=35.0, stop_atr=3.0,
                                       trail_atr=3.0, max_hold=40)),
    "donchian_trend": dict(interval="1d", intraday=False,
                           params=dict(period=55, atr_mult=2.5, rr=2.0, trend_filter=100)),
    "rsi_reversion":  dict(interval="1d", intraday=False,
                           params=dict(period=2, low=10.0, atr_mult=3.0, rr=2.0, trend_filter=200)),
    "orb":            dict(interval="15m", intraday=True,
                           params=dict(or_bars=2, rr=4.0)),
    "vwap_reversion": dict(interval="15m", intraday=True,
                           params=dict(z_thresh=2.0, atr_mult=1.5, rr=1.0)),
}
DEFAULT_STRATEGY = "trend_pullback"


def _load(interval, refresh):
    df = D.get_data(interval=interval, refresh=refresh)
    if interval in ("1d",):
        return D.to_eastern(df)
    return D.regular_session(df)


def _params(strategy, a):
    """Strategy params, optionally enabling the partial scale-out."""
    p = dict(DEFAULTS[strategy]["params"])
    if getattr(a, "partial", False) and strategy == "trend_pullback":
        p.update(partial_rr=2.0, partial_frac=0.5)
    return p


def cmd_backtest(a):
    d = DEFAULTS[a.strategy]
    price = _load(a.interval or d["interval"], a.refresh)
    sig = S.REGISTRY[a.strategy](price, **_params(a.strategy, a))
    cfg = B.BacktestConfig(start_equity=a.equity, risk_pct=a.risk,
                           intraday=d["intraday"])
    tr, eq = B.run(price, sig, cfg)
    st = M.compute(tr, eq, cfg.start_equity)
    print(f"\n{a.strategy} | {d['interval']} | {len(price)} bars "
          f"({price.index[0].date()} -> {price.index[-1].date()})")
    print(st.pretty())
    _, _, mp = M.monthly_report(tr, cfg.start_equity)
    print("\n  -- monthly --\n" + mp)
    if a.trades and len(tr):
        print("\nlast 5 trades:\n", tr.tail().to_string(index=False))


def cmd_compare(a):
    for name, d in DEFAULTS.items():
        price = _load(d["interval"], a.refresh)
        sig = S.REGISTRY[name](price, **_params(name, a))
        cfg = B.BacktestConfig(start_equity=a.equity, risk_pct=a.risk,
                               intraday=d["intraday"])
        tr, eq = B.run(price, sig, cfg)
        st = M.compute(tr, eq, cfg.start_equity)
        _, ms, _ = M.monthly_report(tr, cfg.start_equity)
        print(f"\n### {name}  ({d['interval']}, {len(price)} bars)")
        print(st.pretty())
        if ms:
            print(f"  {'Positive months':<16}{ms['pct_positive_months']:.0f}%   "
                  f"(monthly Sharpe {ms['monthly_sharpe']:.2f}, "
                  f"{ms['avg_trades_per_month']:.1f} trades/mo)")


def cmd_walkforward(a):
    grids = {
        "trend_pullback": {"rsi_buy":[30,35],"stop_atr":[2.0,3.0],"trail_atr":[3.0,4.0,5.0]},
        "donchian_trend": {"period":[20,40,55],"atr_mult":[2.0,3.0],"rr":[2.0,3.0],"trend_filter":[100]},
        "rsi_reversion":  {"atr_mult":[2.0,3.0],"rr":[1.0,1.5,2.0],"low":[5.0,10.0],"trend_filter":[200]},
        "orb":            {"or_bars":[1,2],"rr":[1.0,2.0,3.0]},
    }
    d = DEFAULTS[a.strategy]
    price = _load(a.interval or d["interval"], a.refresh)
    cfg = B.BacktestConfig(start_equity=a.equity, risk_pct=a.risk, intraday=d["intraday"])
    tr, eq, st, log = W.walk_forward(price, S.REGISTRY[a.strategy], grids[a.strategy],
                                     cfg, n_folds=a.folds, train_frac=0.6, min_trades=8)
    print(f"\n{a.strategy} WALK-FORWARD (out-of-sample, stitched)")
    print(st.pretty())
    print("\nper-fold OOS expectancy:",
          [r["oos_expectancy_R"] for r in log if r["oos_expectancy_R"] is not None])


def cmd_signal(a):
    d = DEFAULTS[a.strategy]
    interval = a.interval or d["interval"]
    # For a daily read we want the freshest bar; try to refresh, fall back to cache.
    try:
        price = _load(interval, refresh=True)
    except Exception as e:  # noqa: BLE001
        print(f"(could not refresh data: {e}; using cache)")
        price = _load(interval, refresh=False)
    plan = SG.latest_signal(price, strategy=a.strategy, params=_params(a.strategy, a),
                            account=a.equity, risk_pct=a.risk)
    print("\n" + plan.pretty())


def main(argv=None):
    # Common flags shared by every subcommand (work before OR after the verb).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--equity", type=float, default=10_000.0)
    common.add_argument("--risk", type=float, default=0.01, help="fraction of equity risked per trade")
    common.add_argument("--refresh", action="store_true", help="re-download data")
    common.add_argument("--partial", action="store_true",
                        help="trend_pullback: scale out 50%% at 2R, move stop to "
                             "breakeven, trail the rest (more green months, needs >=2 contracts)")

    p = argparse.ArgumentParser(description="MNQ pattern trading toolkit", parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", parents=[common]); b.add_argument("--strategy", default=DEFAULT_STRATEGY)
    b.add_argument("--interval"); b.add_argument("--trades", action="store_true"); b.set_defaults(func=cmd_backtest)

    c = sub.add_parser("compare", parents=[common]); c.set_defaults(func=cmd_compare)

    w = sub.add_parser("walkforward", parents=[common]); w.add_argument("--strategy", default=DEFAULT_STRATEGY)
    w.add_argument("--interval"); w.add_argument("--folds", type=int, default=6); w.set_defaults(func=cmd_walkforward)

    # `signal` and its alias `plan`: read today's data -> TP/SL plan.
    for verb in ("signal", "plan"):
        s = sub.add_parser(verb, parents=[common]); s.add_argument("--strategy", default=DEFAULT_STRATEGY)
        s.add_argument("--interval"); s.set_defaults(func=cmd_signal)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
