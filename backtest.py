"""Quick backtest of the ADX/DI rules on the underlying (points, before costs).

Usage:  python backtest.py --underlying NIFTY --tf 15m
Entry at signal-candle close, stop checked on following candles, same TSL logic as the live engine.
"""
import argparse

import config
from data.market_data import get_candles
from strategy.adx_strategy import evaluate, stop_hit, update_trailing_stop


def run(df, s):
    trades, pos = [], None
    for i in range(40, len(df)):
        ev = evaluate(df.iloc[: i + 1], s)
        if pos:
            hit = stop_hit(pos, ev["high"], ev["low"])
            rev = s["exit_on_di_reverse"] and ((pos["side"] == "CE") != ev["bull_trend"])
            last_of_day = i + 1 < len(df) and df.index[i + 1].date() != df.index[i].date()
            if hit or rev or last_of_day or i == len(df) - 1:
                px = pos["stop"] if hit else ev["price"]
                pts = (px - pos["entry_underlying"]) * (1 if pos["side"] == "CE" else -1)
                trades.append({"side": pos["side"], "entry": str(pos["t"]), "exit": ev["time"], "points": round(pts, 2),
                               "why": "stop" if hit else "DI reverse" if rev else "EOD"})
                pos = None
                continue
            update_trailing_stop(pos, ev["high"], ev["low"], ev["atr"], s)
        elif ev["signal"]:
            pos = {"side": ev["signal"], "entry_underlying": ev["price"], "best": ev["price"], "t": ev["time"],
                   "stop": ev["low"] if ev["signal"] == "CE" else ev["high"], "tsl_active": False}
    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", default="NIFTY", choices=list(config.UNDERLYINGS))
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--adx", type=float, default=20)
    ap.add_argument("--atr-mult", type=float, default=2.0)
    a = ap.parse_args()
    s = dict(config.DEFAULT_SETTINGS, adx_threshold=a.adx, tsl_distance_atr=a.atr_mult)
    df = get_candles(config.UNDERLYINGS[a.underlying]["yf"], a.tf)
    t = run(df, s)
    wins = [x["points"] for x in t if x["points"] > 0]
    loss = [x["points"] for x in t if x["points"] <= 0]
    for x in t:
        print(f"{x['side']}  {x['entry'][:16]} -> {x['exit'][:16]}  {x['points']:+8.2f}  {x['why']}")
    print(f"\n{a.underlying} {a.tf}  candles={len(df)}  trades={len(t)}")
    if t:
        pf = sum(wins) / abs(sum(loss)) if loss and sum(loss) else float("inf")
        print(f"win rate={len(wins) / len(t):.0%}  net points={sum(wins) + sum(loss):+.2f}  profit factor={pf:.2f}")
    print("Note: underlying points only. Option P&L also depends on delta, theta, IV, spreads and charges.")


if __name__ == "__main__":
    main()
