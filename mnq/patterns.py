"""Candlestick pattern detection (vectorized, no lookahead).

Each function returns an integer Series: +1 bullish signal, -1 bearish,
0 none -- evaluated on the *closed* bar so it can be acted on at the next
bar's open.

NOTE (per the research): the academic evidence that raw candlestick
patterns carry a standalone edge is weak and mixed. We therefore use them
only as *confluence filters* alongside trend / volume context, never as a
sole entry trigger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, ema


def _body(df):  return (df["close"] - df["open"]).abs()
def _range(df): return (df["high"] - df["low"]).replace(0, np.nan)
def _upper_wick(df): return df["high"] - df[["open", "close"]].max(axis=1)
def _lower_wick(df): return df[["open", "close"]].min(axis=1) - df["low"]


def bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    prev_red = df["close"].shift(1) < df["open"].shift(1)
    cur_green = df["close"] > df["open"]
    engulf = (df["close"] >= df["open"].shift(1)) & (df["open"] <= df["close"].shift(1))
    return (prev_red & cur_green & engulf).astype(int)


def bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    prev_green = df["close"].shift(1) > df["open"].shift(1)
    cur_red = df["close"] < df["open"]
    engulf = (df["open"] >= df["close"].shift(1)) & (df["close"] <= df["open"].shift(1))
    return -(prev_green & cur_red & engulf).astype(int)


def hammer(df: pd.DataFrame) -> pd.Series:
    """Long lower wick, small body near the top -> bullish rejection."""
    body, rng = _body(df), _range(df)
    cond = (_lower_wick(df) >= 2 * body) & (_upper_wick(df) <= 0.3 * rng) & (body <= 0.4 * rng)
    return cond.astype(int)


def shooting_star(df: pd.DataFrame) -> pd.Series:
    """Long upper wick, small body near the bottom -> bearish rejection."""
    body, rng = _body(df), _range(df)
    cond = (_upper_wick(df) >= 2 * body) & (_lower_wick(df) <= 0.3 * rng) & (body <= 0.4 * rng)
    return -cond.astype(int)


def doji(df: pd.DataFrame, thresh: float = 0.1) -> pd.Series:
    """Indecision: body is a tiny fraction of the range."""
    return (_body(df) <= thresh * _range(df)).astype(int)


def wide_range_bar(df: pd.DataFrame, period: int = 14, mult: float = 1.5) -> pd.Series:
    """Range >> recent average -> a conviction/expansion bar. Sign = direction."""
    rng = df["high"] - df["low"]
    big = rng > mult * atr(df, period)
    direction = np.sign(df["close"] - df["open"])
    return (big.astype(int) * direction).astype(int)


def pin_bar(df: pd.DataFrame) -> pd.Series:
    """Combine hammer (bull) and shooting star (bear) into one signal."""
    return (hammer(df) + shooting_star(df)).clip(-1, 1)


def all_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Convenience: every pattern as columns for inspection / confluence."""
    return pd.DataFrame(
        {
            "bull_engulf": bullish_engulfing(df),
            "bear_engulf": bearish_engulfing(df),
            "hammer": hammer(df),
            "shooting_star": shooting_star(df),
            "doji": doji(df),
            "wide_range": wide_range_bar(df),
            "pin_bar": pin_bar(df),
        },
        index=df.index,
    )


def trend_context(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    """+1 up-trend / -1 down-trend via EMA stack; used to gate patterns."""
    f, s = ema(df["close"], fast), ema(df["close"], slow)
    return np.sign(f - s).fillna(0).astype(int)
