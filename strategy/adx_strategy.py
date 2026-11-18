"""ADX / DMI strategy (Wilder smoothing) -> CE / PE signals on the underlying."""
import numpy as np
import pandas as pd


def wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_indicators(df: pd.DataFrame, di_length=14, adx_length=14, atr_length=14) -> pd.DataFrame:
    out = df.copy()
    high, low, close = out["high"], out["low"], out["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=out.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=out.index)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)

    atr_di = wilder(tr, di_length)
    plus_di = 100 * wilder(plus_dm, di_length) / atr_di.replace(0, np.nan)
    minus_di = 100 * wilder(minus_dm, di_length) / atr_di.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)

    out["ATR"] = wilder(tr, atr_length)
    out["PLUS_DI"] = plus_di
    out["MINUS_DI"] = minus_di
    out["ADX"] = wilder(dx.fillna(0), adx_length)
    return out


def evaluate(df: pd.DataFrame, s: dict) -> dict:
    """Evaluate the LAST CLOSED candle of df (caller must drop the forming candle)."""
    ind = compute_indicators(df, int(s["di_length"]), int(s["adx_length"]), int(s["atr_length"]))
    rise = int(s["adx_rise_bars"])
    if len(ind) < max(30, rise + 3):
        return {"signal": None, "reason": "Not enough candles", "ind": ind}

    cur = ind.iloc[-1]
    lo, hi = float(s["adx_threshold"]), float(s["adx_exit_zone"])
    window = max(1, int(s.get("cross_window", 3)))
    p, m, a = ind["PLUS_DI"].values, ind["MINUS_DI"].values, ind["ADX"].values

    def qualifies(j):  # ADX inside band and rising `rise` bars at index j
        return lo < a[j] < hi and all(a[j - i] > a[j - i - 1] for i in range(rise))

    n = len(ind) - 1
    bull = p[n] > m[n]
    # bars since the most recent DI crossover (alignment flip)
    k = 0
    while k < n - 1 and (p[n - k] > m[n - k]) == bull and (p[n - k - 1] > m[n - k - 1]) == bull:
        k += 1
    crossed_recently = (p[n - k - 1] > m[n - k - 1]) != bull and k < window
    adx = float(a[n])
    adx_rising = all(a[n - i] > a[n - i - 1] for i in range(rise))
    side = "CE" if bull else "PE"

    signal, reason = None, f"No fresh DI crossover (last cross {k} bars ago)" if not crossed_recently else ""
    if crossed_recently:
        already = any(qualifies(n - j) for j in range(1, k + 1))  # fired earlier in this window
        if already:
            reason = f"{side} already signalled for this crossover"
        elif not (lo < adx < hi):
            reason = f"{side} cross: waiting, ADX {adx:.1f} outside {lo:g}-{hi:g}"
        elif not adx_rising:
            reason = f"{side} cross: waiting for ADX rising {rise} bars"
        else:
            signal = side
            reason = ("+DI above -DI" if bull else "-DI above +DI") + f" (cross {k} bars ago), ADX {adx:.1f} rising"

    return {
        "signal": signal,
        "reason": reason,
        "time": str(ind.index[-1]),
        "price": round(float(cur["close"]), 2),
        "high": float(cur["high"]),
        "low": float(cur["low"]),
        "adx": round(adx, 2),
        "plus_di": round(float(cur["PLUS_DI"]), 2),
        "minus_di": round(float(cur["MINUS_DI"]), 2),
        "atr": round(float(cur["ATR"]), 2),
        "adx_rising": bool(adx_rising),
        "bull_trend": bool(bull),
        "bars_since_cross": int(k),
        "ind": ind,
    }


def update_trailing_stop(pos: dict, high: float, low: float, atr: float, s: dict) -> dict:
    """Update stop for a long-CE (direction=+1) or long-PE (direction=-1) position, tracked on the underlying."""
    act = float(s["tsl_activation_atr"]) * atr
    dist = float(s["tsl_distance_atr"]) * atr
    if pos["side"] == "CE":
        pos["best"] = max(pos["best"], high)
        if pos["best"] - pos["entry_underlying"] >= act:
            pos["tsl_active"] = True
            pos["stop"] = max(pos["stop"], pos["best"] - dist)
    else:
        pos["best"] = min(pos["best"], low)
        if pos["entry_underlying"] - pos["best"] >= act:
            pos["tsl_active"] = True
            pos["stop"] = min(pos["stop"], pos["best"] + dist)
    return pos


def stop_hit(pos: dict, high: float, low: float) -> bool:
    return low <= pos["stop"] if pos["side"] == "CE" else high >= pos["stop"]
