"""Auto-trading engine: candles -> ADX signal -> CE/PE buy -> ATR trailing stop -> exit."""
import csv
import datetime as dt
import logging
import os
import threading
import time
from collections import deque

import config
from broker.kotak_neo import KotakNeo
from broker.paper import PaperBroker
from data.market_data import closed_only, get_candles
from strategy.adx_strategy import evaluate, stop_hit, update_trailing_stop

log = logging.getLogger("engine")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TRADES_CSV = os.path.join("logs", "trades.csv")


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


class Trader:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = dict(config.DEFAULT_SETTINGS)
        self.kotak = KotakNeo(config.KOTAK)
        self.paper = PaperBroker()
        self.live = False
        self.running = False
        self.thread = None
        self.position = None
        self.trades = []
        self.events = deque(maxlen=200)
        self.last_eval = {}
        self.chart = []
        self.last_candle = None
        self.day = now_ist().date()
        self.day_trades = 0
        self.day_pnl = 0.0
        self.halted_reason = ""
        self.last_error = ""
        self.last_tick = None

    # ---------------- helpers ----------------
    def event(self, msg: str, level: str = "info"):
        t = now_ist().strftime("%H:%M:%S")
        self.events.appendleft({"t": t, "level": level, "msg": msg})
        getattr(log, "warning" if level == "warn" else level if level in ("info", "error") else "info")(msg)

    def broker(self):
        return self.kotak if self.live else self.paper

    def market_open(self, t: dt.datetime) -> bool:
        return t.weekday() < 5 and dt.time(9, 15) <= t.time() <= dt.time(15, 30)

    def reset_day_if_needed(self):
        d = now_ist().date()
        if d != self.day:
            self.day, self.day_trades, self.day_pnl, self.halted_reason = d, 0, 0.0, ""
            self.event("New trading day: counters reset")

    # ---------------- controls ----------------
    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            self.event(f"Bot STARTED in {'LIVE' if self.live else 'PAPER'} mode")

    def stop(self):
        with self.lock:
            self.running = False
            self.event("Bot STOPPED (open position, if any, is still held - use Square Off)")

    def set_live(self, on: bool) -> dict:
        with self.lock:
            if on:
                if not config.ALLOW_LIVE:
                    return {"ok": False, "message": "Set ALLOW_LIVE=true in .env and restart to allow live orders"}
                if not self.kotak.logged_in:
                    return {"ok": False, "message": "Login to Kotak Neo first"}
                if self.position:
                    return {"ok": False, "message": "Close the paper position before switching to LIVE"}
            elif self.position and self.live:
                return {"ok": False, "message": "Square off the LIVE position before switching to paper"}
            self.live = on
            self.event(f"Mode switched to {'LIVE - REAL ORDERS' if on else 'PAPER'}", "warn" if on else "info")
            return {"ok": True, "message": "LIVE enabled" if on else "Paper mode"}

    def update_settings(self, new: dict):
        with self.lock:
            for k, v in new.items():
                if k not in self.settings:
                    continue
                cur = self.settings[k]
                if isinstance(cur, bool):
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
                elif isinstance(cur, int):
                    v = int(float(v))
                elif isinstance(cur, float):
                    v = float(v)
                else:
                    v = str(v).strip()
                self.settings[k] = v
            if "underlying" in new and "lot_size" not in new:
                self.settings["lot_size"] = config.UNDERLYINGS[self.settings["underlying"]]["lot"]
            self.last_candle = None
            self.event("Settings updated")

    # ---------------- main loop ----------------
    def _loop(self):
        while self.running:
            try:
                self.tick()
                self.last_error = ""
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
                self.event(f"Loop error: {e}", "error")
            for _ in range(int(self.settings["poll_seconds"])):
                if not self.running:
                    break
                time.sleep(1)

    def refresh_data(self):
        s = self.settings
        und = config.UNDERLYINGS[s["underlying"]]
        df = closed_only(get_candles(und["yf"], s["timeframe"]), s["timeframe"])
        ev = evaluate(df, s)
        ind = ev.pop("ind")
        tail = ind.tail(150)
        self.chart = [
            {"t": str(i), "o": round(r.open, 2), "h": round(r.high, 2), "l": round(r.low, 2), "c": round(r.close, 2),
             "adx": None if r.ADX != r.ADX else round(r.ADX, 2),
             "pdi": None if r.PLUS_DI != r.PLUS_DI else round(r.PLUS_DI, 2),
             "mdi": None if r.MINUS_DI != r.MINUS_DI else round(r.MINUS_DI, 2)}
            for i, r in tail.iterrows()
        ]
        self.last_eval = ev
        return ev

    def tick(self):
        with self.lock:
            self.reset_day_if_needed()
            t = now_ist()
            self.last_tick = t.strftime("%H:%M:%S")
            s = self.settings
            ev = self.refresh_data()
            new_candle = ev.get("time") != self.last_candle
            self.last_candle = ev.get("time")

            if self.position:
                self._mark_to_market(ev)
                if t.time() >= hhmm(s["square_off_time"]):
                    return self.exit_position("Time square-off")
                if new_candle and ev.get("atr"):
                    pos = self.position
                    if stop_hit(pos, ev["high"], ev["low"]):
                        return self.exit_position(f"Stop hit @ {pos['stop']:.2f}")
                    if s["exit_on_di_reverse"] and (
                        (pos["side"] == "CE" and not ev["bull_trend"]) or (pos["side"] == "PE" and ev["bull_trend"])):
                        return self.exit_position("Opposite DI crossover")
                    update_trailing_stop(pos, ev["high"], ev["low"], ev["atr"], s)
                return

            if not new_candle or not ev.get("signal"):
                return
            if not self.market_open(t):
                return self.event(f"{ev['signal']} signal ignored: market closed")
            if not (hhmm(s["trade_start"]) <= t.time() <= hhmm(s["no_new_entry_after"])):
                return self.event(f"{ev['signal']} signal ignored: outside entry window")
            if self.day_trades >= int(s["max_trades_per_day"]):
                self.halted_reason = "Max trades per day reached"
                return self.event(f"{ev['signal']} signal ignored: {self.halted_reason}", "warn")
            if self.day_pnl <= -abs(float(s["max_daily_loss"])):
                self.halted_reason = "Max daily loss reached"
                return self.event(f"{ev['signal']} signal ignored: {self.halted_reason}", "warn")
            self.enter_position(ev)

    # ---------------- orders ----------------
    def _strike(self, spot: float, side: str) -> int:
        s = self.settings
        step = config.UNDERLYINGS[s["underlying"]]["step"]
        atm = int(round(spot / step) * step)
        off = int(s["strike_offset"]) * step
        return atm + off if side == "CE" else atm - off

    def enter_position(self, ev: dict):
        s = self.settings
        side = ev["signal"]
        strike = self._strike(ev["price"], side)
        lot_size = int(s["lot_size"])
        symbol, token = f"{s['underlying']} {strike} {side}", None

        if self.kotak.logged_in:
            try:
                opt = self.kotak.find_option(s["underlying"], strike, side, s["expiry"])
                symbol, token = opt["trading_symbol"], opt["token"]
                if opt["lot_size"] > 0:
                    lot_size = opt["lot_size"]
            except Exception as e:  # noqa: BLE001
                if self.live:
                    return self.event(f"LIVE entry aborted, option lookup failed: {e}", "error")
                self.event(f"Option lookup failed (paper continues): {e}", "warn")
        qty = int(s["lots"]) * lot_size

        b = self.broker()
        try:
            o = b.market_order(symbol, qty, "B", protection=s["market_protection"])
            st = b.order_status(o["order_no"])
        except Exception as e:  # noqa: BLE001
            return self.event(f"ENTRY ORDER FAILED: {e}", "error")
        if self.live and st["status"] in ("rejected", "cancelled"):
            return self.event(f"LIVE entry {st['status']}: {st['reason']}", "error")
        if self.live and st["status"] not in ("complete", "completed", "traded"):
            self.event(f"LIVE entry status '{st['status']}' - tracking as open. Verify in Kotak order book!", "error")

        premium = st.get("avg_price") or (self.kotak.ltp(token) if (token and self.kotak.logged_in) else None)
        stop = ev["low"] if side == "CE" else ev["high"]
        self.position = {
            "side": side, "symbol": symbol, "token": token, "qty": qty, "strike": strike,
            "entry_time": now_ist().strftime("%Y-%m-%d %H:%M:%S"), "entry_underlying": ev["price"],
            "entry_premium": premium, "stop": stop, "initial_stop": stop, "best": ev["price"],
            "tsl_active": False, "order_no": o["order_no"], "mode": "LIVE" if self.live else "PAPER",
            "ltp_underlying": ev["price"], "ltp_premium": premium, "pnl": 0.0,
        }
        self.day_trades += 1
        self.event(f"ENTRY {self.position['mode']}: BUY {symbol} x{qty} | spot {ev['price']} | SL {stop:.2f} | {ev['reason']}",
                   "warn" if self.live else "info")

    def _mark_to_market(self, ev: dict):
        pos = self.position
        pos["ltp_underlying"] = ev["price"]
        if pos.get("token") and self.kotak.logged_in:
            p = self.kotak.ltp(pos["token"])
            if p:
                pos["ltp_premium"] = p
        pos["pnl"] = round(self._pnl(pos, pos.get("ltp_premium"), ev["price"]), 2)

    def _pnl(self, pos, exit_premium, exit_underlying):
        if pos.get("entry_premium") and exit_premium:
            return (exit_premium - pos["entry_premium"]) * pos["qty"]
        direction = 1 if pos["side"] == "CE" else -1
        return (exit_underlying - pos["entry_underlying"]) * direction * float(self.settings["paper_delta"]) * pos["qty"]

    def exit_position(self, reason: str) -> dict:
        with self.lock:
            pos = self.position
            if not pos:
                return {"ok": False, "message": "No open position"}
            live_pos = pos["mode"] == "LIVE"
            b = self.kotak if live_pos else self.paper
            st, filled = {"status": "complete", "avg_price": None}, False
            for attempt in range(3):
                try:
                    o = b.market_order(pos["symbol"], pos["qty"], "S", protection=self.settings["market_protection"])
                except Exception as e:  # noqa: BLE001  (order never accepted -> safe to retry)
                    self.event(f"EXIT ORDER FAILED (attempt {attempt + 1}): {e}", "error")
                    time.sleep(1)
                    continue
                st = b.order_status(o["order_no"], wait_seconds=10)
                if not live_pos or st["status"] in ("complete", "completed", "traded"):
                    filled = True
                    break
                if st["status"] in ("rejected", "cancelled"):
                    self.event(f"Exit attempt {attempt + 1} {st['status']}: {st.get('reason', '')}", "error")
                    time.sleep(1)
                    continue
                break  # pending/unknown: never send a 2nd sell (avoids accidental short)
            if not filled:
                self.running = False
                self.event("!!! LIVE EXIT NOT CONFIRMED - BOT STOPPED. SQUARE OFF MANUALLY IN KOTAK NEO APP !!!", "error")
                return {"ok": False, "message": "Exit not confirmed - check Kotak Neo app"}

            spot = self.last_eval.get("price", pos["ltp_underlying"])
            exit_prem = st.get("avg_price") or pos.get("ltp_premium")
            pnl = round(self._pnl(pos, exit_prem, spot), 2)
            trade = {**{k: pos[k] for k in ("mode", "side", "symbol", "qty", "entry_time", "entry_underlying", "entry_premium")},
                     "exit_time": now_ist().strftime("%Y-%m-%d %H:%M:%S"), "exit_underlying": spot,
                     "exit_premium": exit_prem, "pnl": pnl, "reason": reason}
            self.trades.insert(0, trade)
            self.day_pnl += pnl
            self.position = None
            self._save_trade(trade)
            self.event(f"EXIT {trade['mode']}: SELL {trade['symbol']} | {reason} | P&L {pnl:+.2f}",
                       "warn" if live_pos else "info")
            return {"ok": True, "message": f"Exited: {reason}"}

    def _save_trade(self, trade: dict):
        os.makedirs("logs", exist_ok=True)
        new = not os.path.exists(TRADES_CSV)
        with open(TRADES_CSV, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trade.keys()))
            if new:
                w.writeheader()
            w.writerow(trade)

    # ---------------- status ----------------
    def status(self) -> dict:
        with self.lock:
            return {
                "running": self.running, "live": self.live, "allow_live": config.ALLOW_LIVE,
                "kotak_logged_in": self.kotak.logged_in, "kotak_error": self.kotak.last_error,
                "settings": self.settings, "underlyings": list(config.UNDERLYINGS.keys()),
                "signal": self.last_eval, "position": self.position, "trades": self.trades[:50],
                "events": list(self.events)[:80], "day_trades": self.day_trades,
                "day_pnl": round(self.day_pnl, 2), "halted_reason": self.halted_reason,
                "last_error": self.last_error, "last_tick": self.last_tick,
                "market_open": self.market_open(now_ist()), "server_time": now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
            }
