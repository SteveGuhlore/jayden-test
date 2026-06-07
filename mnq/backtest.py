"""Event-driven, single-position backtester with realistic MNQ economics.

Design choices that keep results honest (no lookahead, no survivorship of
intrabar luck):

* A strategy decides on the *close* of bar i. The trade is entered at the
  *open* of bar i+1, plus slippage. You can never act on information you
  didn't have.
* Stop and target are bracket orders checked intrabar via each bar's
  high/low. If a single bar trades through BOTH levels, we assume the
  STOP filled first (pessimistic / conservative).
* Position size is risk-based: each trade risks ``risk_pct`` of current
  equity to its stop. Contracts are integer (>=1) and capped.
* Costs: commission per contract per side + slippage in ticks on both
  entry and exit.

Signals schema (DataFrame aligned to price index):
    side       : +1 long / -1 short / 0 flat  (entry decision on this bar)
    stop_dist  : distance in index points from entry to stop (>0)
    rr         : target reward-to-risk multiple
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---- MNQ (Micro E-mini Nasdaq-100) contract economics --------------------
POINT_VALUE = 2.0      # $ per 1.00 index point per contract
TICK = 0.25            # minimum price increment (index points)
TICK_VALUE = 0.50      # $ per tick per contract


@dataclass
class CostModel:
    commission_per_side: float = 0.74   # typical retail all-in per contract per side
    slippage_ticks: float = 1.0         # ticks of slippage applied per fill


@dataclass
class BacktestConfig:
    start_equity: float = 10_000.0
    risk_pct: float = 0.01              # risk 1% of equity to stop per trade
    max_contracts: int = 50
    intraday: bool = True              # force flat at session end (EOD exit)
    costs: CostModel = field(default_factory=CostModel)
    allow_short: bool = True


def _round_tick(p: float) -> float:
    return round(p / TICK) * TICK


def run(price: pd.DataFrame, signals: pd.DataFrame, cfg: BacktestConfig | None = None):
    """Return (trades_df, equity_series)."""
    cfg = cfg or BacktestConfig()
    px = price
    sig = signals.reindex(px.index).fillna({"side": 0, "stop_dist": np.nan, "rr": np.nan})

    o = px["open"].to_numpy(float)
    h = px["high"].to_numpy(float)
    l = px["low"].to_numpy(float)
    c = px["close"].to_numpy(float)
    idx = px.index
    day = idx.normalize()

    side_arr = sig["side"].to_numpy(float)
    stopd_arr = sig["stop_dist"].to_numpy(float)
    rr_arr = sig["rr"].to_numpy(float)
    # Optional columns: trailing-stop distance (points) and max holding bars.
    trail_arr = (sig["trail_dist"].to_numpy(float) if "trail_dist" in sig
                 else np.full(len(sig), np.nan))
    hold_arr = (sig["max_hold"].to_numpy(float) if "max_hold" in sig
                else np.full(len(sig), np.nan))

    slip = cfg.costs.slippage_ticks * TICK
    equity = cfg.start_equity
    n = len(px)

    in_pos = False
    pos = {}
    trades = []
    eq_points = [(idx[0], equity)]

    for i in range(n - 1):
        # ---- manage an open position on bar i ----
        if in_pos:
            side, entry, qty, risk_pts = pos["side"], pos["entry"], pos["qty"], pos["risk_pts"]
            target, trail_dist = pos["target"], pos["trail_dist"]
            pos["bars_held"] += 1

            # update the trailing stop from the most favourable excursion
            if np.isfinite(trail_dist):
                if side == 1:
                    pos["extreme"] = max(pos["extreme"], h[i])
                    pos["stop"] = max(pos["stop"], _round_tick(pos["extreme"] - trail_dist))
                else:
                    pos["extreme"] = min(pos["extreme"], l[i])
                    pos["stop"] = min(pos["stop"], _round_tick(pos["extreme"] + trail_dist))
            stop = pos["stop"]

            exit_price, reason = None, None
            if side == 1:
                hit_stop, hit_tgt = l[i] <= stop, h[i] >= target
            else:
                hit_stop, hit_tgt = h[i] >= stop, l[i] <= target
            if hit_stop:                      # pessimistic: stop wins ties
                exit_price, reason = stop, "stop"
            elif hit_tgt:
                exit_price, reason = target, "target"

            max_hold = pos["max_hold"]
            if exit_price is None and np.isfinite(max_hold) and pos["bars_held"] >= max_hold:
                exit_price, reason = c[i], "time"

            eod = cfg.intraday and (i == n - 1 or day[i + 1] != day[i])
            if exit_price is None and eod:
                exit_price, reason = c[i], "eod"

            if exit_price is not None:
                fill = exit_price - side * slip          # slippage against us
                gross = side * (fill - entry) * POINT_VALUE * qty
                comm = cfg.costs.commission_per_side * qty * 2  # both sides
                pnl = gross - comm
                equity += pnl
                R = pnl / (risk_pts * POINT_VALUE * qty) if risk_pts > 0 and qty > 0 else 0.0
                trades.append({
                    "entry_time": pos["entry_time"], "exit_time": idx[i],
                    "side": "long" if side == 1 else "short",
                    "entry": entry, "exit": fill, "qty": qty,
                    "pnl": pnl, "R": R, "reason": reason,
                })
                eq_points.append((idx[i], equity))
                in_pos = False

        # ---- look for a new entry decided on bar i, filled at i+1 open ----
        if not in_pos:
            side = side_arr[i]
            stop_dist = stopd_arr[i]
            rr = rr_arr[i]
            if side != 0 and np.isfinite(stop_dist) and stop_dist > 0:
                if side < 0 and not cfg.allow_short:
                    continue
                # don't open a brand-new intraday trade on the last bar of a day
                if cfg.intraday and (i + 1 >= n or day[i + 1] != day[i]):
                    continue
                entry = o[i + 1] + np.sign(side) * slip
                stop = _round_tick(entry - side * stop_dist)
                risk_pts = abs(entry - stop)
                if risk_pts <= 0:
                    continue
                # target: fixed R-multiple, or "infinite" when riding a trail
                target = (_round_tick(entry + side * rr * stop_dist)
                          if np.isfinite(rr) else (np.inf if side == 1 else -np.inf))
                risk_dollars = equity * cfg.risk_pct
                qty = int(risk_dollars / (risk_pts * POINT_VALUE))
                qty = max(1, min(qty, cfg.max_contracts))
                pos = {
                    "side": int(side), "entry": entry, "stop": stop, "target": target,
                    "qty": qty, "risk_pts": risk_pts, "entry_time": idx[i + 1],
                    "trail_dist": trail_arr[i], "max_hold": hold_arr[i],
                    "extreme": entry, "bars_held": 0,
                }
                in_pos = True

    trades_df = pd.DataFrame(trades)
    equity_series = pd.Series(
        [e for _, e in eq_points], index=pd.DatetimeIndex([t for t, _ in eq_points])
    )
    return trades_df, equity_series
