"""Offline safety helpers. No broker calls or live execution."""
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")

@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

def freshness(timestamp, now, max_age_seconds=90):
    if timestamp.tzinfo is None or now.tzinfo is None:
        return Check("feed_fresh", False, "Timezone-aware timestamps required")
    age = (now - timestamp).total_seconds()
    return Check("feed_fresh", 0 <= age <= max_age_seconds, f"Age: {age:.1f}s")

def preflight(*, now, last_quote_at, broker_connected, expected_ip, observed_ip,
              exchange_session_open, realized_pnl, unrealized_pnl, max_daily_loss,
              trades_today, max_trades, has_pending_orders, state_reconciled,
              instrument_verified, allow_live, typed_confirmation):
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(IST)
    return [
        Check("allow_live", allow_live is True, "Environment permission"),
        Check("confirmation", typed_confirmation == "LIVE", "Explicit confirmation"),
        Check("broker", broker_connected is True, "Authenticated session"),
        Check("ip", bool(expected_ip) and expected_ip == observed_ip, "Configured IP match; not proof of broker whitelisting"),
        Check("session", exchange_session_open is True and local.weekday() < 5 and time(9,15) <= local.time() < time(14,45), "Exchange calendar plus IST entry window"),
        freshness(last_quote_at, now),
        Check("loss", max_daily_loss > 0 and realized_pnl + unrealized_pnl > -max_daily_loss, "Realized plus unrealized P&L"),
        Check("trade_count", 0 <= trades_today < max_trades, "Entry count"),
        Check("pending", has_pending_orders is False, "No ambiguous or pending orders"),
        Check("reconciled", state_reconciled is True, "Broker snapshot reconciled"),
        Check("instrument", instrument_verified is True, "Expiry, lot size, spread, margin verified externally"),
    ]

def may_arm(checks):
    return bool(checks) and all(c.passed for c in checks)

# Unknown/pending states must never authorize a second order.
def retry_decision(status):
    status = str(status or "").strip().upper()
    if status in {"REJECTED"}:
        return "RECONCILE_BEFORE_RETRY"
    if status in {"FILLED", "COMPLETE", "COMPLETED"}:
        return "NO_RETRY_FILLED"
    if status in {"CANCELLED", "CANCELED"}:
        return "RECONCILE_PARTIAL_FILLS_BEFORE_RETRY"
    return "BLOCK_AND_RECONCILE"

def reconcile_quantities(local, broker):
    """Mappings keyed by exact exchange+instrument identifier, signed units."""
    keys = set(local) | set(broker)
    return {k: {"local": local.get(k, 0), "broker": broker.get(k, 0)}
            for k in keys if local.get(k, 0) != broker.get(k, 0)}

def limit_price(ltp, buffer_pct, tick_size, side):
    p, b, t = map(lambda v: Decimal(str(v)), (ltp, buffer_pct, tick_size))
    if p <= 0 or t <= 0 or not 0 <= b <= 20 or side not in {"BUY", "SELL"}:
        raise ValueError("Invalid limit order inputs")
    raw = p * (1 + b / 100 if side == "BUY" else 1 - b / 100)
    units = (raw / t).to_integral_value(rounding=ROUND_FLOOR)
    if side == "BUY" and units * t < raw:
        units += 1
    result = units * t
    if result <= 0:
        raise ValueError("Non-positive price")
    return float(result)
