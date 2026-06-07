"""Live signal generator: turn the latest bar into an actionable MNQ plan
with concrete entry, stop-loss and take-profit levels plus position size.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from . import backtest as B
from . import strategies as S


@dataclass
class TradePlan:
    as_of: str
    symbol: str
    side: str            # long / short / flat
    entry_ref: float     # reference entry (last close); use a stop/market order
    stop: float
    target: float
    risk_points: float
    reward_points: float
    rr: float
    contracts: int
    dollar_risk: float
    dollar_reward: float
    note: str

    def pretty(self) -> str:
        if self.side == "flat":
            return (f"[{self.as_of}] {self.symbol}: NO TRADE — conditions not met.\n"
                    f"  {self.note}")
        return (
            f"[{self.as_of}] {self.symbol} — {self.side.upper()} SIGNAL\n"
            f"  Entry (ref) : {self.entry_ref:,.2f}\n"
            f"  Stop loss   : {self.stop:,.2f}   ({self.risk_points:,.1f} pts risk)\n"
            f"  Take profit : {self.target:,.2f}   ({self.reward_points:,.1f} pts target)\n"
            f"  Risk:Reward : 1 : {self.rr:.2f}\n"
            f"  Size        : {self.contracts} MNQ contract(s)  "
            f"(risk ${self.dollar_risk:,.0f} / reward ${self.dollar_reward:,.0f})\n"
            f"  Note        : {self.note}"
        )


def latest_signal(
    price: pd.DataFrame,
    strategy: str = "donchian_trend",
    params: dict | None = None,
    account: float = 10_000.0,
    risk_pct: float = 0.01,
    max_contracts: int = 50,
    symbol: str = "MNQ",
) -> TradePlan:
    params = params or {}
    fn = S.REGISTRY[strategy]
    sig = fn(price, **params)

    last_ts = price.index[-1]
    row = sig.iloc[-1]
    side = int(row["side"])
    last_close = float(price["close"].iloc[-1])

    if side == 0 or not np.isfinite(row["stop_dist"]):
        return TradePlan(
            as_of=str(last_ts), symbol=symbol, side="flat",
            entry_ref=last_close, stop=0, target=0, risk_points=0,
            reward_points=0, rr=0, contracts=0, dollar_risk=0, dollar_reward=0,
            note=f"{strategy} produced no entry on the most recent bar.",
        )

    stop_dist = float(row["stop_dist"])
    rr = float(row["rr"])
    entry = last_close
    stop = B._round_tick(entry - side * stop_dist)
    target = B._round_tick(entry + side * rr * stop_dist)
    risk_pts = abs(entry - stop)
    reward_pts = abs(target - entry)

    risk_dollars = account * risk_pct
    qty = int(risk_dollars / (risk_pts * B.POINT_VALUE)) if risk_pts > 0 else 0
    qty = max(1, min(qty, max_contracts))

    actual_risk = risk_pts * B.POINT_VALUE * qty
    note = (f"Strategy={strategy}. Entry is a reference (last close); place a "
            f"stop/market order at the breakout. Levels in index points; "
            f"MNQ = ${B.POINT_VALUE}/pt.")
    if actual_risk > 1.5 * risk_dollars:
        min_acct = actual_risk / risk_pct
        note += (f"  ** WARNING: 1 contract risks ${actual_risk:,.0f} "
                 f"({actual_risk/account:.0%} of a ${account:,.0f} account) — far "
                 f"above your {risk_pct:.0%} target. This stop is too wide for this "
                 f"account; you need ~${min_acct:,.0f}+ to size it correctly, or use "
                 f"a tighter intraday strategy. DO NOT oversize. **")

    return TradePlan(
        as_of=str(last_ts), symbol=symbol,
        side="long" if side == 1 else "short",
        entry_ref=entry, stop=stop, target=target,
        risk_points=risk_pts, reward_points=reward_pts, rr=rr,
        contracts=qty,
        dollar_risk=actual_risk,
        dollar_reward=reward_pts * B.POINT_VALUE * qty,
        note=note,
    )
