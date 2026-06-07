"""Performance metrics computed from a list of closed trades + equity curve."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Stats:
    n_trades: int
    win_rate: float
    avg_R: float            # average reward-to-risk multiple per trade
    expectancy_R: float     # expected R per trade (the edge, in R units)
    profit_factor: float
    total_pnl: float        # dollars
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float           # annualized, on per-trade returns
    avg_win: float
    avg_loss: float
    best: float
    worst: float

    def as_dict(self):
        return self.__dict__.copy()

    def pretty(self) -> str:
        d = self.as_dict()
        order = [
            ("n_trades", "Trades", "{:d}"),
            ("win_rate", "Win rate", "{:.1%}"),
            ("avg_R", "Avg R / trade", "{:+.2f}R"),
            ("expectancy_R", "Expectancy", "{:+.3f}R"),
            ("profit_factor", "Profit factor", "{:.2f}"),
            ("total_pnl", "Total P&L", "${:,.0f}"),
            ("total_return_pct", "Total return", "{:+.1f}%"),
            ("cagr_pct", "CAGR", "{:+.1f}%"),
            ("max_drawdown_pct", "Max drawdown", "{:.1f}%"),
            ("sharpe", "Sharpe (ann.)", "{:.2f}"),
            ("avg_win", "Avg win", "${:,.0f}"),
            ("avg_loss", "Avg loss", "${:,.0f}"),
        ]
        return "\n".join(f"  {label:<16}{fmt.format(d[key])}" for key, label, fmt in order)


def monthly_report(trades: pd.DataFrame, start_equity: float):
    """Aggregate realized P&L by calendar month -> (table, summary, pretty).

    This is the lens that matters for 'profitable on the monthly': it shows
    how many months were green, the worst month, and month-to-month
    consistency rather than just per-trade stats.
    """
    if trades is None or len(trades) == 0:
        return pd.DataFrame(), {}, "  (no trades)"
    t = trades.copy()
    t["month"] = pd.to_datetime(t["exit_time"]).dt.tz_localize(None).dt.to_period("M")
    t["win"] = (t["pnl"] > 0).astype(int)
    table = t.groupby("month").agg(
        pnl=("pnl", "sum"), trades=("pnl", "size"), wins=("win", "sum")
    )
    table["ret_pct"] = 100 * table["pnl"] / start_equity
    pnl = table["pnl"].to_numpy(float)
    pos = pnl > 0
    summary = {
        "months_traded": int(len(table)),
        "pct_positive_months": float(100 * pos.mean()),
        "avg_month": float(pnl.mean()),
        "median_month": float(np.median(pnl)),
        "best_month": float(pnl.max()),
        "worst_month": float(pnl.min()),
        "std_month": float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0,
        "monthly_sharpe": float(pnl.mean() / pnl.std(ddof=1) * np.sqrt(12))
        if len(pnl) > 1 and pnl.std(ddof=1) > 0 else 0.0,
        "avg_trades_per_month": float(table["trades"].mean()),
    }
    pretty = "\n".join([
        f"  Months traded     {summary['months_traded']}",
        f"  Positive months   {summary['pct_positive_months']:.0f}%",
        f"  Avg month         ${summary['avg_month']:,.0f}",
        f"  Median month      ${summary['median_month']:,.0f}",
        f"  Best / Worst      ${summary['best_month']:,.0f} / ${summary['worst_month']:,.0f}",
        f"  Monthly Sharpe    {summary['monthly_sharpe']:.2f}",
        f"  Trades / month    {summary['avg_trades_per_month']:.1f}",
    ])
    return table, summary, pretty


def compute(trades: pd.DataFrame, equity: pd.Series, start_equity: float,
            periods_per_year: int = 252) -> Stats:
    """trades: DataFrame with columns pnl (dollars) and R (reward multiple)."""
    if trades is None or len(trades) == 0:
        return Stats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    pnl = trades["pnl"].to_numpy(dtype=float)
    R = trades["R"].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    win_rate = len(wins) / len(pnl)
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")

    total_pnl = pnl.sum()
    total_return_pct = 100 * total_pnl / start_equity

    # CAGR from equity curve timestamps
    if len(equity) > 1:
        days = (equity.index[-1] - equity.index[0]).days or 1
        years = days / 365.25
        end_eq = equity.iloc[-1]
        cagr = 100 * ((end_eq / start_equity) ** (1 / years) - 1) if end_eq > 0 and years > 0 else -100.0
    else:
        cagr = 0.0

    # Max drawdown on equity curve
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    max_dd = 100 * dd.min() if len(dd) else 0.0

    # Sharpe on per-trade returns scaled to ~annual via trade frequency
    trade_ret = pnl / start_equity
    if trade_ret.std(ddof=1) > 0 and len(equity) > 1:
        trades_per_year = len(pnl) / max(years, 1e-9)
        sharpe = (trade_ret.mean() / trade_ret.std(ddof=1)) * np.sqrt(trades_per_year)
    else:
        sharpe = 0.0

    return Stats(
        n_trades=len(pnl),
        win_rate=win_rate,
        avg_R=float(np.mean(R)),
        expectancy_R=float(np.mean(R)),
        profit_factor=float(profit_factor),
        total_pnl=float(total_pnl),
        total_return_pct=float(total_return_pct),
        cagr_pct=float(cagr),
        max_drawdown_pct=float(max_dd),
        sharpe=float(sharpe),
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        best=float(pnl.max()),
        worst=float(pnl.min()),
    )
