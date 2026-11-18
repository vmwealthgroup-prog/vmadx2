"""Thin, defensive wrapper around the official Kotak Neo SDK v2 (neo_api_client).

SDK: pip install kotakneoapi  (https://github.com/Kotak-Neo/kotak-neo-python)
Kotak response field names can change between SDK versions, so every parser below
tries several keys and logs the raw response when it cannot understand it.
"""
import datetime as dt
import logging
import time

log = logging.getLogger("kotak")


def _first(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def _rows(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("data", "message", "result"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


class KotakNeo:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.client = None
        self.logged_in = False
        self.last_error = ""

    # ---------- auth ----------
    def login(self, totp: str = "") -> dict:
        try:
            from neo_api_client import NeoAPI
        except ImportError:
            return self._fail("Kotak SDK not installed. Run: pip install kotakneoapi")
        c = self.cfg
        if not (c["consumer_key"] and c["mobile_number"] and c["ucc"] and c["mpin"]):
            return self._fail("Fill KOTAK_CONSUMER_KEY, KOTAK_MOBILE_NUMBER, KOTAK_UCC, KOTAK_MPIN in .env")
        if not totp and c.get("totp_secret"):
            import pyotp
            totp = pyotp.TOTP(c["totp_secret"]).now()
        if not totp:
            return self._fail("Enter the 6-digit TOTP from your authenticator app")
        try:
            self.client = NeoAPI(environment=c["environment"], access_token=None,
                                 neo_fin_key=None, consumer_key=c["consumer_key"])
            r1 = self.client.totp_login(mobile_number=c["mobile_number"], ucc=c["ucc"], totp=totp)
            if isinstance(r1, dict) and r1.get("error"):
                return self._fail(f"TOTP login failed: {r1['error']}")
            r2 = self.client.totp_validate(mpin=c["mpin"])
            if isinstance(r2, dict) and r2.get("error"):
                return self._fail(f"MPIN validate failed: {r2['error']}")
            self.logged_in = True
            self.last_error = ""
            log.info("Kotak Neo login OK")
            return {"ok": True, "message": "Kotak Neo session active"}
        except Exception as e:  # noqa: BLE001
            return self._fail(f"Login error: {e}")

    def logout(self):
        try:
            if self.client:
                self.client.logout()
        except Exception:  # noqa: BLE001
            pass
        self.logged_in = False

    def _fail(self, msg):
        self.logged_in = False if "login" in msg.lower() or "fill" in msg.lower() else self.logged_in
        self.last_error = msg
        log.error(msg)
        return {"ok": False, "message": msg}

    def _need(self):
        if not (self.client and self.logged_in):
            raise RuntimeError("Kotak Neo not logged in")

    # ---------- instruments ----------
    def find_option(self, underlying: str, strike: int, opt_type: str, expiry: str = "") -> dict:
        """Return {trading_symbol, token, lot_size, expiry} for the nearest-expiry option."""
        self._need()
        resp = self.client.search_scrip(exchange_segment="nse_fo", symbol=underlying,
                                        expiry=expiry or "", option_type=opt_type,
                                        strike_price=str(strike))
        rows = _rows(resp)
        if not rows:
            raise RuntimeError(f"No option found for {underlying} {strike} {opt_type} {expiry}: {str(resp)[:300]}")

        today = dt.date.today()

        def exp_date(r):
            v = str(_first(r, "pExpiryDate", "expiry", default=""))
            for fmt in ("%d%b%Y", "%d%B%Y", "%Y-%m-%d"):
                try:
                    return dt.datetime.strptime(v.title(), fmt).date()
                except ValueError:
                    pass
            return dt.date.max

        # keep only exact underlying (search may also return e.g. NIFTYNXT50) and non-expired contracts
        exact = [r for r in rows if str(_first(r, "pSymbolName", "pSymbol_name", "symbol", default=underlying)).upper() == underlying.upper()]
        live = [r for r in (exact or rows) if exp_date(r) >= today]
        r = sorted(live or exact or rows, key=exp_date)[0]
        return {
            "trading_symbol": _first(r, "pTrdSymbol", "trading_symbol", "pTrdSymbolName"),
            "token": str(_first(r, "pSymbol", "instrument_token", "tok", default="")),
            "lot_size": int(float(_first(r, "lLotSize", "iLotSize", "lot_size", default=0) or 0)),
            "expiry": _first(r, "pExpiryDate", "expiry", default=""),
        }

    def ltp(self, token: str, segment: str = "nse_fo") -> float | None:
        self._need()
        try:
            resp = self.client.quotes(instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}],
                                      quote_type="ltp")
            rows = _rows(resp) or ([resp] if isinstance(resp, dict) else [])
            for r in rows:
                v = _first(r, "ltp", "ltP", "last_traded_price", "lp")
                if v is not None:
                    return float(v)
        except Exception as e:  # noqa: BLE001
            log.warning("LTP error: %s", e)
        return None

    # ---------- orders ----------
    def place(self, trading_symbol: str, qty: int, side: str, price: float | None = None, tag="vmadx2") -> dict:
        """side = 'B' or 'S'. MIS intraday on nse_fo. price=None -> market order, else limit order."""
        self._need()
        is_limit = bool(price and price > 0)
        resp = self.client.place_order(
            exchange_segment="nse_fo", product="MIS",
            price=f"{price:.2f}" if is_limit else "0",
            order_type="L" if is_limit else "MKT",
            quantity=str(int(qty)), validity="DAY", trading_symbol=trading_symbol,
            transaction_type=side, amo="NO", disclosed_quantity="0", trigger_price="0", tag=tag,
        )
        log.info("place_order %s %s x%s @ %s -> %s", side, trading_symbol, qty, price or "MKT", resp)
        order_no = _first(resp if isinstance(resp, dict) else {}, "nOrdNo", "order_id", "orderId")
        if not order_no:
            raise RuntimeError(f"Order rejected/unknown response: {str(resp)[:300]}")
        return {"order_no": str(order_no), "raw": resp}

    def market_order(self, trading_symbol: str, qty: int, side: str, **_):
        return self.place(trading_symbol, qty, side, None)

    def cancel(self, order_no: str) -> dict:
        self._need()
        resp = self.client.cancel_order(order_id=str(order_no))
        log.info("cancel_order %s -> %s", order_no, resp)
        return resp if isinstance(resp, dict) else {"raw": resp}

    def order_status(self, order_no: str, wait_seconds: float = 6.0) -> dict:
        """Poll order book until the order is complete/rejected or timeout."""
        self._need()
        deadline = time.time() + wait_seconds
        last = {"status": "unknown", "avg_price": None, "reason": ""}
        while time.time() < deadline:
            try:
                for r in _rows(self.client.order_report()):
                    if str(_first(r, "nOrdNo", "order_id", default="")) == str(order_no):
                        st = str(_first(r, "ordSt", "status", default="")).lower()
                        avg = _first(r, "avgPrc", "avg_price")
                        last = {"status": st, "avg_price": float(avg) if avg not in (None, "") else None,
                                "reason": _first(r, "rejRsn", "rejection_reason", default="")}
                        if st in ("complete", "completed", "traded", "rejected", "cancelled"):
                            return last
            except Exception as e:  # noqa: BLE001
                log.warning("order_report error: %s", e)
            time.sleep(1.0)
        return last

    def positions(self):
        self._need()
        return _rows(self.client.positions())

    def orders(self):
        self._need()
        return _rows(self.client.order_report())
