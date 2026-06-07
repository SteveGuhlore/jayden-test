"""Live signal generator: read MNQ's latest data and produce an actionable
daily trade plan with concrete entry, stop-loss and take-profit levels,
position size, and (for trend strategies) a trailing-stop rule to ride
winners.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import backtest as B
from . import strategies as S


@dataclass
class TradePlan:
    as_of: str
    symbol: str
    side: str            # long / short / flat
    entry_ref: float
    stop: float
    target: float
    risk_points: float
    reward_points: float
    rr: float
    contracts: int
    dollar_risk: float
    dollar_reward: float
    exit_mode: str       # "fixed" or "trailing"
    trail_points: float  # ATR trail distance (points), 0 if fixed
    max_hold_bars: float
    note: str

    def pretty(self) -> str:
        if self.side == "flat":
            return (f"[{self.as_of}] {self.symbol}: ⏸  NO TRADE TODAY — setup not present.\n"
                    f"  {self.note}")
        arrow = "🟢 LONG" if self.side == "long" else "🔴 SHORT"
        lines = [
            f"[{self.as_of}] {self.symbol} — {arrow}",
            f"  Entry (ref)  : {self.entry_ref:,.2f}",
            f"  STOP LOSS    : {self.stop:,.2f}   ({self.risk_points:,.0f} pts  =  ${self.dollar_risk:,.0f} on {self.contracts} ctr)",
            f"  TAKE PROFIT  : {self.target:,.2f}   ({self.reward_points:,.0f} pts  =  ${self.dollar_reward:,.0f})   [1 : {self.rr:.1f} R]",
            f"  Size         : {self.contracts} MNQ contract(s)",
        ]
        if self.exit_mode == "trailing" and self.trail_points > 0:
            lines.append(
                f"  RIDE WINNERS : optional — instead of the fixed TP, trail the stop "
                f"{self.trail_points:,.0f} pts below the highest high since entry "
                f"(backtests favor this: higher profit factor, lower drawdown)."
            )
        if np.isfinite(self.max_hold_bars):
            lines.append(f"  Time stop    : exit after ~{int(self.max_hold_bars)} bars if neither level hit.")
        lines.append(f"  Note         : {self.note}")
        return "\n".join(lines)


def latest_signal(
    price: pd.DataFrame,
    strategy: str = "trend_pullback",
    params: dict | None = None,
    account: float = 50_000.0,
    risk_pct: float = 0.01,
    max_contracts: int = 50,
    display_rr: float = 3.0,
    symbol: str = "MNQ",
) -> TradePlan:
    """Translate the most recent bar into a trade plan. ``display_rr`` is the
    take-profit shown for trend strategies that otherwise trail (so you always
    get a concrete TP number)."""
    params = params or {}
    sig = S.REGISTRY[strategy](price, **params)

    last_ts = price.index[-1]
    row = sig.iloc[-1]
    side = int(row["side"])
    last_close = float(price["close"].iloc[-1])

    if side == 0 or not np.isfinite(row["stop_dist"]):
        return TradePlan(
            as_of=str(last_ts), symbol=symbol, side="flat", entry_ref=last_close,
            stop=0, target=0, risk_points=0, reward_points=0, rr=0, contracts=0,
            dollar_risk=0, dollar_reward=0, exit_mode="none", trail_points=0,
            max_hold_bars=float("nan"),
            note=f"'{strategy}' found no qualifying setup on the most recent bar. Wait.",
        )

    stop_dist = float(row["stop_dist"])
    trail_dist = float(row.get("trail_dist", np.nan))
    rr_col = float(row.get("rr", np.nan))
    rr = rr_col if np.isfinite(rr_col) else display_rr
    exit_mode = "fixed" if np.isfinite(rr_col) else "trailing"

    entry = last_close
    stop = B._round_tick(entry - side * stop_dist)
    target = B._round_tick(entry + side * rr * stop_dist)
    risk_pts = abs(entry - stop)
    reward_pts = abs(target - entry)

    risk_dollars = account * risk_pct
    qty = int(risk_dollars / (risk_pts * B.POINT_VALUE)) if risk_pts > 0 else 0
    qty = max(1, min(qty, max_contracts))
    actual_risk = risk_pts * B.POINT_VALUE * qty

    note = (f"Strategy={strategy}. Entry is a reference (today's close); place a "
            f"market/stop order near it. Levels are index points; MNQ = ${B.POINT_VALUE}/pt. "
            f"Decision uses only closed-bar data (no lookahead).")
    if actual_risk > 1.5 * risk_dollars:
        min_acct = actual_risk / risk_pct
        note += (f"  ** WARNING: 1 contract risks ${actual_risk:,.0f} "
                 f"({actual_risk/account:.0%} of ${account:,.0f}) — above your "
                 f"{risk_pct:.0%} target. Use ~${min_acct:,.0f}+ or a tighter setup. **")

    return TradePlan(
        as_of=str(last_ts), symbol=symbol,
        side="long" if side == 1 else "short",
        entry_ref=entry, stop=stop, target=target,
        risk_points=risk_pts, reward_points=reward_pts, rr=rr, contracts=qty,
        dollar_risk=actual_risk, dollar_reward=reward_pts * B.POINT_VALUE * qty,
        exit_mode=exit_mode,
        trail_points=trail_dist if np.isfinite(trail_dist) else 0.0,
        max_hold_bars=float(row.get("max_hold", np.nan)),
        note=note,
    )
