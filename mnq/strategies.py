"""Strategy library. Each strategy returns a signals DataFrame with columns
``side`` (+1/-1/0), ``stop_dist`` (points to stop), ``rr`` (target multiple),
aligned to the price index. Decisions are made on the bar's close and acted
on at the next bar's open by the backtester (no lookahead).

Strategies implemented:
  * orb              -- Opening Range Breakout (Zarattini & Aziz style)
  * vwap_reversion   -- intraday fade of stretches away from session VWAP
  * donchian_trend   -- N-day breakout momentum (swing, daily bars)
  * rsi_reversion    -- daily mean reversion from RSI extremes
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from . import patterns as pat


def _empty(index) -> pd.DataFrame:
    return pd.DataFrame(
        {"side": 0.0, "stop_dist": np.nan, "rr": np.nan,
         "trail_dist": np.nan, "max_hold": np.nan},
        index=index,
    )


# --------------------------------------------------------------------------
# 1) Opening Range Breakout  (research-backed cornerstone strategy)
# --------------------------------------------------------------------------
def orb(df: pd.DataFrame, or_bars: int = 2, rr: float = 4.0,
        min_relvol: float = 0.0, atr_period: int = 14,
        min_stop_atr: float = 0.0) -> pd.DataFrame:
    """Opening Range Breakout on intraday RTH bars (index must be ET RTH).

    The first ``or_bars`` bars of each session define the range. The first
    bar to CLOSE outside it triggers a trade in the breakout direction;
    stop = opposite side of the range, target = ``rr`` x risk. One entry
    per day. ``min_relvol`` optionally requires elevated volume (the paper's
    'stocks in play' idea).
    """
    out = _empty(df.index)
    relvol = ind.relative_volume(df, lookback=or_bars * 10) if min_relvol > 0 else None
    a = ind.atr(df, atr_period)

    for _, day_df in df.groupby(df.index.normalize()):
        if len(day_df) < or_bars + 2:
            continue
        rows = day_df.index
        or_high = day_df["high"].iloc[:or_bars].max()
        or_low = day_df["low"].iloc[:or_bars].min()
        for j in range(or_bars, len(day_df) - 1):  # need a next bar to enter
            ts = rows[j]
            close = day_df["close"].iloc[j]
            if min_relvol > 0 and relvol is not None:
                rv = relvol.get(ts, np.nan)
                if not (np.isfinite(rv) and rv >= min_relvol):
                    continue
            side = 0
            if close > or_high:
                side, stop_dist = 1, close - or_low
            elif close < or_low:
                side, stop_dist = -1, or_high - close
            if side != 0:
                if min_stop_atr > 0:
                    stop_dist = max(stop_dist, min_stop_atr * (a.get(ts, np.nan) or 0))
                if stop_dist > 0:
                    out.loc[ts, ["side", "stop_dist", "rr"]] = [side, stop_dist, rr]
                break  # one trade per day
    return out


# --------------------------------------------------------------------------
# 2) VWAP mean reversion (intraday fade)
# --------------------------------------------------------------------------
def vwap_reversion(df: pd.DataFrame, z_thresh: float = 2.0, atr_period: int = 14,
                   atr_mult: float = 1.5, rr: float = 1.0) -> pd.DataFrame:
    """Fade stretches away from session VWAP, targeting reversion.

    Long when price is ``z_thresh`` std below VWAP AND the bar closes up
    (rejection); short symmetrically. Stop = ``atr_mult`` x ATR.
    """
    out = _empty(df.index)
    vwap = ind.session_vwap(df)
    dist = df["close"] - vwap
    z = ind.rolling_zscore(dist, period=20)
    a = ind.atr(df, atr_period)
    bull_bar = df["close"] > df["open"]
    bear_bar = df["close"] < df["open"]

    long_sig = (z <= -z_thresh) & bull_bar
    short_sig = (z >= z_thresh) & bear_bar
    out.loc[long_sig, "side"] = 1
    out.loc[short_sig, "side"] = -1
    sd = atr_mult * a
    out.loc[out["side"] != 0, "stop_dist"] = sd
    out.loc[out["side"] != 0, "rr"] = rr
    return out


# --------------------------------------------------------------------------
# 3) Donchian breakout trend-following (swing, daily bars)
# --------------------------------------------------------------------------
def donchian_trend(df: pd.DataFrame, period: int = 20, atr_period: int = 14,
                   atr_mult: float = 2.0, rr: float = 3.0,
                   trend_filter: int = 100) -> pd.DataFrame:
    """Buy N-day highs / sell N-day lows in the direction of a long trend
    filter. ATR stop, ``rr`` x target. Designed for daily bars (swing).
    """
    out = _empty(df.index)
    upper, lower = ind.donchian(df, period)
    a = ind.atr(df, atr_period)
    sma = ind.sma(df["close"], trend_filter) if trend_filter else None

    long_sig = df["close"] > upper
    short_sig = df["close"] < lower
    if sma is not None:
        long_sig &= df["close"] > sma
        short_sig &= df["close"] < sma
    out.loc[long_sig, "side"] = 1
    out.loc[short_sig, "side"] = -1
    out.loc[out["side"] != 0, "stop_dist"] = atr_mult * a
    out.loc[out["side"] != 0, "rr"] = rr
    return out


# --------------------------------------------------------------------------
# 4) RSI mean reversion (swing, daily bars)
# --------------------------------------------------------------------------
def rsi_reversion(df: pd.DataFrame, period: int = 2, low: float = 10.0,
                  high: float = 90.0, atr_period: int = 14, atr_mult: float = 2.5,
                  rr: float = 1.5, long_only: bool = True,
                  trend_filter: int = 200) -> pd.DataFrame:
    """Connors-style short-period RSI reversion on daily bars.

    With ``trend_filter`` set (default 200-day SMA), longs are only taken
    while price is above the long-term average and shorts only below it.
    This 'buy the dip in an uptrend' regime gate is what turns RSI2 from a
    high-drawdown contrarian system into a robust one -- it stops you
    catching falling knives through bear markets.
    """
    out = _empty(df.index)
    r = ind.rsi(df["close"], period)
    a = ind.atr(df, atr_period)
    sma = ind.sma(df["close"], trend_filter) if trend_filter else None

    long_sig = r <= low
    short_sig = r >= high
    if sma is not None:
        long_sig = long_sig & (df["close"] > sma)
        short_sig = short_sig & (df["close"] < sma)
    out.loc[long_sig, "side"] = 1
    if not long_only:
        out.loc[short_sig, "side"] = -1
    out.loc[out["side"] != 0, "stop_dist"] = atr_mult * a
    out.loc[out["side"] != 0, "rr"] = rr
    return out


# --------------------------------------------------------------------------
# 5) Trend pullback (THE monthly-consistency workhorse, daily bars, long-biased)
# --------------------------------------------------------------------------
def trend_pullback(df: pd.DataFrame, sma_trend: int = 200, rsi_p: int = 4,
                   rsi_buy: float = 30.0, atr_period: int = 14,
                   stop_atr: float = 2.5, trail_atr: float = 4.0,
                   rr: float = float("nan"), max_hold: int = 40,
                   pattern_filter: bool = True,
                   allow_short: bool = False) -> pd.DataFrame:
    """Buy dips inside an established up-trend, then ride the trend out with a
    chandelier-style ATR trailing stop. This is the strategy aimed at your
    goal: few, high-quality trades (~weekly) that try to make MONTHS green by
    cutting losers fast and letting winners run.

    Logic (long):
      * Regime  : close > ``sma_trend``  (only trade with the primary trend).
      * Trigger : short-period RSI dips below ``rsi_buy`` (a pullback).
      * Confirm : optional bullish candle / not-falling-knife filter.
      * Stop    : ``stop_atr`` x ATR below entry (initial risk).
      * Exit    : ``trail_atr`` x ATR chandelier trail (no fixed target) plus a
                  ``max_hold`` time stop. Letting the trail run is what captures
                  the Nasdaq's upward drift.
    """
    out = _empty(df.index)
    sma = ind.sma(df["close"], sma_trend)
    r = ind.rsi(df["close"], rsi_p)
    a = ind.atr(df, atr_period)

    uptrend = df["close"] > sma
    dip = r <= rsi_buy
    long_sig = uptrend & dip
    if pattern_filter:
        # avoid the worst falling knives: require the bar not to be a big down bar
        not_knife = df["close"] >= df["open"] * 0.997
        long_sig = long_sig & not_knife
    out.loc[long_sig, "side"] = 1

    if allow_short:
        downtrend = df["close"] < sma
        rally = r >= (100 - rsi_buy)
        short_sig = downtrend & rally
        out.loc[short_sig, "side"] = -1

    sel = out["side"] != 0
    out.loc[sel, "stop_dist"] = stop_atr * a
    out.loc[sel, "max_hold"] = max_hold
    if np.isfinite(rr):
        out.loc[sel, "rr"] = rr           # fixed-target variant
    else:
        out.loc[sel, "trail_dist"] = trail_atr * a   # ride the ATR trail
        out.loc[sel, "rr"] = np.nan
    return out


REGISTRY = {
    "orb": orb,
    "vwap_reversion": vwap_reversion,
    "donchian_trend": donchian_trend,
    "rsi_reversion": rsi_reversion,
    "trend_pullback": trend_pullback,
}
