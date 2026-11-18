"""Candle feed for the underlying index (Yahoo Finance, free; may lag ~1 min)."""
import pandas as pd
import yfinance as yf

PERIOD_FOR = {"1m": "5d", "2m": "5d", "5m": "30d", "15m": "30d", "30m": "30d", "60m": "60d", "1d": "1y"}
MINUTES = {"1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1d": 1440}


def get_candles(yf_symbol: str, interval: str) -> pd.DataFrame:
    df = yf.download(yf_symbol, period=PERIOD_FOR.get(interval, "30d"), interval=interval,
                     progress=False, auto_adjust=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError(f"No candles returned for {yf_symbol} {interval}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("Asia/Kolkata")
    return df


def closed_only(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Drop the still-forming last candle so signals never repaint."""
    if df.empty or interval == "1d":
        return df
    now = pd.Timestamp.now(tz="Asia/Kolkata")
    if df.index[-1] + pd.Timedelta(minutes=MINUTES.get(interval, 5)) > now:
        return df.iloc[:-1]
    return df
