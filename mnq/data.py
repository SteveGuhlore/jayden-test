"""Data acquisition for MNQ / NQ (Nasdaq-100 futures).

MNQ (Micro E-mini Nasdaq-100) tracks the exact same index as NQ (E-mini
Nasdaq-100) -- it is simply 1/10th the contract size. Price action and
patterns are identical, so we backtest on the continuous front-month
futures series ``NQ=F`` from Yahoo Finance and apply MNQ contract
economics ($2/point) in the backtester.

Yahoo intraday history is limited:
  * 1m   -> ~7 days
  * 5m   -> ~60 days (but often throttled)
  * 15m  -> ~60 days
  * 1h   -> ~730 days
  * 1d   -> many years

Data is cached to ``data/`` as parquet/csv so we don't re-hit the API.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_SYMBOL = "NQ=F"  # continuous front-month E-mini Nasdaq-100 future


def _cache_path(symbol: str, interval: str) -> Path:
    safe = symbol.replace("=", "").replace("^", "")
    return DATA_DIR / f"{safe}_{interval}.csv"


def _download(symbol: str, interval: str, period: str, retries: int = 5) -> pd.DataFrame:
    """Download with exponential backoff to survive Yahoo's 429 throttling."""
    if yf is None:
        raise RuntimeError("yfinance is not installed; run `pip install -r requirements.txt`")
    last_err = None
    for i in range(retries):
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
            )
            if df is not None and len(df):
                return df
            last_err = ValueError("empty frame returned")
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed to download {symbol} {interval}: {last_err}")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance columns to lowercase open/high/low/close/volume."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    cols = ["open", "high", "low", "close", "volume"]
    df = df[[c for c in cols if c in df.columns]].copy()
    df = df.dropna()
    df = df[~df.index.duplicated(keep="last")]
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def get_data(
    symbol: str = DEFAULT_SYMBOL,
    interval: str = "15m",
    period: str | None = None,
    use_cache: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Return normalized OHLCV. Caches to disk; merges fresh data on refresh."""
    if period is None:
        period = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
                  "1h": "730d", "1d": "max"}.get(interval, "60d")

    path = _cache_path(symbol, interval)
    cached = None
    if use_cache and path.exists() and not refresh:
        cached = pd.read_csv(path, index_col=0, parse_dates=True)
        cached.index = pd.to_datetime(cached.index, utc=True)
        return cached

    df = _normalize(_download(symbol, interval, period))
    if cached is not None:
        df = pd.concat([cached, df])
        df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_csv(path)
    return df


def to_eastern(df: pd.DataFrame) -> pd.DataFrame:
    """Convert UTC index to US/Eastern (the exchange/RTH reference tz)."""
    out = df.copy()
    out.index = out.index.tz_convert("America/New_York")
    return out


def regular_session(df: pd.DataFrame) -> pd.DataFrame:
    """Filter intraday bars to the RTH cash session 09:30-16:00 ET."""
    et = to_eastern(df)
    mask = (et.index.time >= pd.Timestamp("09:30").time()) & (
        et.index.time < pd.Timestamp("16:00").time()
    )
    return et[mask]


if __name__ == "__main__":
    for itv in ("1d", "15m"):
        d = get_data(interval=itv, refresh=True)
        print(f"{itv}: {len(d)} bars  {d.index[0]} -> {d.index[-1]}")
