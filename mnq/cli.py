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
    "donchian_trend": dict(interval="1d", intraday=False,
                           params=dict(period=55, atr_mult=2.5, rr=2.0, trend_filter=100)),
    "rsi_reversion":  dict(interval="1d", intraday=False,
                           params=dict(period=2, low=10.0, atr_mult=3.0, rr=2.0, trend_filter=200)),
    "orb":            dict(interval="15m", intraday=True,
                           params=dict(or_bars=2, rr=4.0)),
    "vwap_reversion": dict(interval="15m", intraday=True,
                           params=dict(z_thresh=2.0, atr_mult=1.5, rr=1.0)),
}


def _load(interval, refresh):
    df = D.get_data(interval=interval, refresh=refresh)
    if interval in ("1d",):
        return D.to_eastern(df)
    return D.regular_session(df)


def cmd_backtest(a):
    d = DEFAULTS[a.strategy]
    price = _load(a.interval or d["interval"], a.refresh)
    sig = S.REGISTRY[a.strategy](price, **d["params"])
    cfg = B.BacktestConfig(start_equity=a.equity, risk_pct=a.risk,
                           intraday=d["intraday"])
    tr, eq = B.run(price, sig, cfg)
    st = M.compute(tr, eq, cfg.start_equity)
    print(f"\n{a.strategy} | {d['interval']} | {len(price)} bars "
          f"({price.index[0].date()} -> {price.index[-1].date()})")
    print(st.pretty())
    if a.trades and len(tr):
        print("\nlast 5 trades:\n", tr.tail().to_string(index=False))


def cmd_compare(a):
    for name, d in DEFAULTS.items():
        price = _load(d["interval"], a.refresh)
        sig = S.REGISTRY[name](price, **d["params"])
        cfg = B.BacktestConfig(start_equity=a.equity, risk_pct=a.risk,
                               intraday=d["intraday"])
        tr, eq = B.run(price, sig, cfg)
        st = M.compute(tr, eq, cfg.start_equity)
        print(f"\n### {name}  ({d['interval']}, {len(price)} bars)")
        print(st.pretty())


def cmd_walkforward(a):
    grids = {
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
    price = _load(a.interval or d["interval"], a.refresh)
    plan = SG.latest_signal(price, strategy=a.strategy, params=d["params"],
                            account=a.equity, risk_pct=a.risk)
    print("\n" + plan.pretty())


def main(argv=None):
    # Common flags shared by every subcommand (work before OR after the verb).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--equity", type=float, default=10_000.0)
    common.add_argument("--risk", type=float, default=0.01, help="fraction of equity risked per trade")
    common.add_argument("--refresh", action="store_true", help="re-download data")

    p = argparse.ArgumentParser(description="MNQ pattern trading toolkit", parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", parents=[common]); b.add_argument("--strategy", default="donchian_trend")
    b.add_argument("--interval"); b.add_argument("--trades", action="store_true"); b.set_defaults(func=cmd_backtest)

    c = sub.add_parser("compare", parents=[common]); c.set_defaults(func=cmd_compare)

    w = sub.add_parser("walkforward", parents=[common]); w.add_argument("--strategy", default="donchian_trend")
    w.add_argument("--interval"); w.add_argument("--folds", type=int, default=6); w.set_defaults(func=cmd_walkforward)

    s = sub.add_parser("signal", parents=[common]); s.add_argument("--strategy", default="donchian_trend")
    s.add_argument("--interval"); s.set_defaults(func=cmd_signal)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
