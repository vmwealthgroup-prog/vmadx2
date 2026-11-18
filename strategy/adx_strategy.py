"""
ADX / DMI strategy (Wilder smoothing) -> CE / PE signals on the underlying.

IMPORTANT:
- Use only completed candles.
- The caller must remove the currently forming candle before calling evaluate().
- This module generates signals on the underlying instrument.
- CE means bullish underlying signal.
- PE means bearish underlying signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """
    Apply Wilder smoothing.

    Formula:
        current = previous + (value - previous) / period

    This is equivalent to an EMA with alpha = 1 / period.
    """
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)

    start = 0
    while start < len(values) and np.isnan(values[start]):
        start += 1

    if start >= len(values):
        return pd.Series(result, index=series.index)

    result[start] = values[start]

    for i in range(start + 1, len(values)):
        if np.isnan(values[i]):
            result[i] = result[i - 1]
        else:
            result[i] = result[i - 1] + (values[i] - result[i - 1]) / period

    return pd.Series(result, index=series.index)


def compute_indicators(
    df: pd.DataFrame,
    di_length: int = 14,
    adx_length: int = 14,
    atr_length: int = 14,
) -> pd.DataFrame:
    """
    Calculate Wilder +DI, -DI, DX, ADX and ATR.

    Required DataFrame columns:
        high, low, close
    """
    if df.empty:
        raise ValueError("Candle DataFrame is empty")

    required_columns = {"high", "low", "close"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing candle columns: {sorted(missing_columns)}")

    out = df.copy()

    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)

    previous_high = high.shift(1)
    previous_low = low.shift(1)
    previous_close = close.shift(1)

    # Directional Movement
    up_move = high - previous_high
    down_move = previous_low - low

    plus_dm = np.where(
        (up_move > down_move) & (up_move > 0),
        up_move,
        0.0,
    )

    minus_dm = np.where(
        (down_move > up_move) & (down_move > 0),
        down_move,
        0.0,
    )

    # True Range
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder smoothing
    smoothed_tr = wilder_smooth(true_range, di_length)
    smoothed_plus_dm = wilder_smooth(
        pd.Series(plus_dm, index=out.index),
        di_length,
    )
    smoothed_minus_dm = wilder_smooth(
        pd.Series(minus_dm, index=out.index),
        di_length,
    )

    # Directional Indicators
    plus_di = 100 * smoothed_plus_dm / smoothed_tr.replace(0, np.nan)
    minus_di = 100 * smoothed_minus_dm / smoothed_tr.replace(0, np.nan)

    # DX
    di_sum = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / di_sum.replace(0, np.nan)

    # ADX with proper Wilder seeding
    dx_values = dx.to_numpy(dtype=float)
    adx_values = np.full(len(dx_values), np.nan)

    valid_dx_indices = [
        index
        for index, value in enumerate(dx_values)
        if not np.isnan(value)
    ]

    if len(valid_dx_indices) >= adx_length:
        first_valid_index = valid_dx_indices[0]

        first_adx_window = dx_values[
            first_valid_index : first_valid_index + adx_length
        ]

        first_adx = float(np.nanmean(first_adx_window))
        first_adx_index = first_valid_index + adx_length - 1

        adx_values[first_adx_index] = first_adx

        for index in range(first_adx_index + 1, len(dx_values)):
            if np.isnan(dx_values[index]):
                adx_values[index] = adx_values[index - 1]
            else:
                adx_values[index] = (
                    (adx_values[index - 1] * (adx_length - 1))
                    + dx_values[index]
                ) / adx_length

    # ATR
    atr = wilder_smooth(true_range, atr_length)

    out["PLUS_DM"] = plus_dm
    out["MINUS_DM"] = minus_dm
    out["TRUE_RANGE"] = true_range
    out["ATR"] = atr
    out["PLUS_DI"] = plus_di
    out["MINUS_DI"] = minus_di
    out["DX"] = dx
    out["ADX"] = pd.Series(adx_values, index=out.index)

    return out


def evaluate(df: pd.DataFrame, settings: dict) -> dict:
    """
    Evaluate the last CLOSED candle and return a CE / PE signal.

    The caller must pass only completed candles.
    """
    di_length = int(settings.get("di_length", 14))
    adx_length = int(settings.get("adx_length", 14))
    atr_length = int(settings.get("atr_length", 14))
    rise_bars = int(settings.get("adx_rise_bars", 2))
    cross_window = int(settings.get("cross_window", 3))

    adx_threshold = float(settings.get("adx_threshold", 20))
    adx_exit_zone = float(settings.get("adx_exit_zone", 35))

    indicators = compute_indicators(
        df,
        di_length=di_length,
        adx_length=adx_length,
        atr_length=atr_length,
    )

    minimum_candles = max(
        30,
        rise_bars + 3,
        cross_window + 2,
    )

    if len(indicators) < minimum_candles:
        return {
            "signal": None,
            "reason": "Not enough candles",
            "cross_id": None,
            "cross_time": None,
            "time": str(indicators.index[-1]) if len(indicators) else None,
            "price": None,
            "high": None,
            "low": None,
            "adx": None,
            "plus_di": None,
            "minus_di": None,
            "atr": None,
            "adx_rising": False,
            "bull_trend": False,
            "bars_since_cross": None,
            "indicators": indicators,
        }

    current_candle = indicators.iloc[-1]

    plus_di = indicators["PLUS_DI"].to_numpy(dtype=float)
    minus_di = indicators["MINUS_DI"].to_numpy(dtype=float)
    adx = indicators["ADX"].to_numpy(dtype=float)

    latest_index = len(indicators) - 1

    latest_adx = float(adx[latest_index])
    latest_plus_di = float(plus_di[latest_index])
    latest_minus_di = float(minus_di[latest_index])
    latest_atr = float(current_candle["ATR"])
    latest_close = float(current_candle["close"])

    bull_trend = latest_plus_di > latest_minus_di
    side = "CE" if bull_trend else "PE"

    # Find bars since the most recent DI alignment change.
    bars_since_cross = 0

    while (
        bars_since_cross < latest_index
        and (
            plus_di[latest_index - bars_since_cross]
            > minus_di[latest_index - bars_since_cross]
        ) == bull_trend
        and (
            plus_di[latest_index - bars_since_cross - 1]
            > minus_di[latest_index - bars_since_cross - 1]
        ) == bull_trend
    ):
        bars_since_cross += 1

    crossed_recently = (
        bars_since_cross < cross_window
        and (
            plus_di[latest_index - bars_since_cross - 1]
            > minus_di[latest_index - bars_since_cross - 1]
        ) != bull_trend
    )

    cross_index = (
        latest_index - bars_since_cross - 1
        if crossed_recently
        else None
    )

    cross_time = (
        indicators.index[cross_index]
        if cross_index is not None
        else None
    )

    cross_id = str(cross_time) if cross_time is not None else None

    def adx_qualified(index: int) -> bool:
        if index < rise_bars:
            return False

        rising = all(
            adx[index - i] > adx[index - i - 1]
            for i in range(1, rise_bars + 1)
        )

        return (
            adx[index] >= adx_threshold
            and adx[index] < adx_exit_zone
            and rising
        )

    signal = None
    reason = "No fresh DI crossover"

    if crossed_recently:
        already_signalled = any(
            adx_qualified(latest_index - offset)
            for offset in range(1, bars_since_cross + 1)
        )

        if already_signalled:
            reason = f"{side} already signalled for this crossover"

        elif latest_adx < adx_threshold:
            reason = (
                f"{side} cross waiting: ADX {latest_adx:.2f} "
                f"is below {adx_threshold:g}"
            )

        elif latest_adx >= adx_exit_zone:
            reason = (
                f"{side} cross rejected: ADX {latest_adx:.2f} "
                f"is at or above {adx_exit_zone:g}"
            )

        elif not adx_qualified(latest_index):
            reason = (
                f"{side} cross waiting: ADX {latest_adx:.2f} "
                f"is not rising for {rise_bars} bars"
            )

        else:
            signal = side
            reason = (
                ("+DI above -DI" if bull_trend else "-DI above +DI")
                + f"; crossover {bars_since_cross} bars ago; "
                + f"ADX {latest_adx:.2f} rising"
            )

    return {
        "signal": signal,
        "reason": reason,
        "cross_id": cross_id,
        "cross_time": str(cross_time) if cross_time is not None else None,
        "time": str(indicators.index[-1]),
        "price": round(latest_close, 2),
        "high": float(current_candle["high"]),
        "low": float(current_candle["low"]),
        "adx": round(latest_adx, 2),
        "plus_di": round(latest_plus_di, 2),
        "minus_di": round(latest_minus_di, 2),
        "atr": round(latest_atr, 2),
        "adx_rising": bool(
            all(
                adx[latest_index - i] > adx[latest_index - i - 1]
                for i in range(1, rise_bars + 1)
            )
        ),
        "bull_trend": bool(bull_trend),
        "bars_since_cross": int(bars_since_cross),
        "indicators": indicators,
    }


def update_trailing_stop(
    position: dict,
    high: float,
    low: float,
    atr: float,
    settings: dict,
) -> dict:
    """
    Update trailing stop using a COMPLETED candle.

    CE is treated as a long underlying position.
    PE is treated as a short underlying position.

    The caller should update the stop using the previous completed candle,
    then check the current candle for a stop hit.
    """
    activation_distance = float(settings["tsl_activation_atr"]) * atr
    trailing_distance = float(settings["tsl_distance_atr"]) * atr

    if position["side"] == "CE":
        position["best_price"] = max(
            position["best_price"],
            high,
        )

        favourable_move = (
            position["best_price"] - position["entry_underlying"]
        )

        if favourable_move >= activation_distance:
            position["tsl_active"] = True

            new_stop = position["best_price"] - trailing_distance
            position["stop"] = max(position["stop"], new_stop)

    else:
        position["best_price"] = min(
            position["best_price"],
            low,
        )

        favourable_move = (
            position["entry_underlying"] - position["best_price"]
        )

        if favourable_move >= activation_distance:
            position["tsl_active"] = True

            new_stop = position["best_price"] + trailing_distance
            position["stop"] = min(position["stop"], new_stop)

    return position


def stop_hit(position: dict, high: float, low: float) -> bool:
    """Check whether the current candle hit the trailing stop."""
    if position["side"] == "CE":
        return low <= position["stop"]

    return high >= position["stop"]


def get_gap_aware_exit_price(
    position: dict,
    open_price: float,
    high: float,
    low: float,
) -> float | None:
    """
    Return a realistic exit price if the trailing stop was hit.

    If price gaps beyond the stop, use the open price instead of assuming
    that the stop price was filled.
    """
    stop = position["stop"]

    if position["side"] == "CE":
        if low <= stop:
            if open_price < stop:
                return open_price
            return stop

    else:
        if high >= stop:
            if open_price > stop:
                return open_price
            return stop

    return None
