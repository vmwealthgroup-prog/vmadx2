"""Paper broker: simulates fills. Option premium P&L is estimated from the underlying move x delta,
unless a real option LTP is available from a logged-in Kotak session."""
import itertools

_ids = itertools.count(1)


class PaperBroker:
    def place(self, trading_symbol: str, qty: int, side: str, price=None, **_):
        return {"order_no": f"PAPER-{next(_ids)}", "raw": {"paper": True}}

    def market_order(self, trading_symbol: str, qty: int, side: str, **_):
        return self.place(trading_symbol, qty, side)

    def cancel(self, order_no: str):
        return {"paper": True}

    def order_status(self, order_no: str, **_):
        return {"status": "complete", "avg_price": None, "reason": ""}
