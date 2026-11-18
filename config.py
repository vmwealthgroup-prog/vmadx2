import os
from dotenv import load_dotenv

load_dotenv()


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


KOTAK = {
    "environment": env("KOTAK_ENVIRONMENT", "prod"),
    "consumer_key": env("KOTAK_CONSUMER_KEY"),
    "mobile_number": env("KOTAK_MOBILE_NUMBER"),
    "ucc": env("KOTAK_UCC"),
    "mpin": env("KOTAK_MPIN"),
    "totp_secret": env("KOTAK_TOTP_SECRET"),
}

ALLOW_LIVE = env("ALLOW_LIVE", "false").lower() == "true"
HOST = env("HOST", "127.0.0.1")
PORT = int(env("PORT", "8000"))

# Underlyings supported. yf = Yahoo symbol used for candles, step = strike gap.
UNDERLYINGS = {
    "NIFTY": {"yf": "^NSEI", "step": 50, "lot": 65},
    "BANKNIFTY": {"yf": "^NSEBANK", "step": 100, "lot": 30},
    "FINNIFTY": {"yf": "NIFTY_FIN_SERVICE.NS", "step": 50, "lot": 60},
}

DEFAULT_SETTINGS = {
    "underlying": "NIFTY",
    "timeframe": "5m",          # 1m, 5m, 15m, 30m, 60m
    "di_length": 14,
    "adx_length": 14,
    "atr_length": 14,
    "adx_threshold": 20.0,
    "adx_exit_zone": 35.0,
    "adx_rise_bars": 2,
    "cross_window": 3,          # signal allowed up to N candles after the DI cross
    "tsl_activation_atr": 1.0,
    "tsl_distance_atr": 2.0,
    "exit_on_di_reverse": True,
    "lots": 1,
    "lot_size": 65,             # verified against Kotak scrip data when live
    "strike_offset": 0,         # 0 = ATM, -1 = 1 strike ITM, +1 = 1 strike OTM
    "expiry": "",               # blank = nearest returned by Kotak search
    "max_trades_per_day": 3,
    "max_daily_loss": 3000.0,   # rupees; bot stops new entries after this
    "trade_start": "09:30",
    "no_new_entry_after": "14:45",
    "square_off_time": "15:15",
    "poll_seconds": 20,
    "market_protection": "10",
    "paper_delta": 0.5,         # paper P&L estimate = underlying move * delta
}
