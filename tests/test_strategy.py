import numpy as np
import pandas as pd

import config
from strategy.adx_strategy import compute_indicators, evaluate, stop_hit, update_trailing_stop


def make_df(n=200, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    close = 20000 + np.cumsum(rng.normal(drift, 10, n))
    idx = pd.date_range("2026-01-01 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    return pd.DataFrame({"open": close, "high": close + 8, "low": close - 8, "close": close}, index=idx)


def test_indicators_ranges():
    ind = compute_indicators(make_df())
    tail = ind.iloc[30:]
    assert tail["ADX"].between(0, 100).all()
    assert tail["PLUS_DI"].between(0, 100).all() and tail["MINUS_DI"].between(0, 100).all()
    assert (tail["ATR"] > 0).all()


def test_uptrend_bullish():
    ind = compute_indicators(make_df(drift=6))
    assert ind["PLUS_DI"].iloc[-1] > ind["MINUS_DI"].iloc[-1]


def test_evaluate_keys():
    ev = evaluate(make_df(), config.DEFAULT_SETTINGS)
    for k in ("signal", "reason", "adx", "plus_di", "minus_di", "atr"):
        assert k in ev


def test_trailing_stop_ce_only_tightens():
    s = config.DEFAULT_SETTINGS
    pos = {"side": "CE", "entry_underlying": 100.0, "best": 100.0, "stop": 95.0, "tsl_active": False}
    update_trailing_stop(pos, high=103, low=101, atr=2, s=s)   # +3 >= 1*ATR -> stop = 103 - 4 = 99
    assert pos["tsl_active"] and pos["stop"] == 99
    update_trailing_stop(pos, high=101, low=98, atr=2, s=s)    # no loosening
    assert pos["stop"] == 99
    assert stop_hit(pos, high=100, low=98.5)


def test_trailing_stop_pe():
    s = config.DEFAULT_SETTINGS
    pos = {"side": "PE", "entry_underlying": 100.0, "best": 100.0, "stop": 105.0, "tsl_active": False}
    update_trailing_stop(pos, high=99, low=96, atr=2, s=s)     # best 96 -> stop 100
    assert pos["stop"] == 100 and stop_hit(pos, high=100.5, low=97)
