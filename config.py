import os
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_PATH)


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
    # kotak = index name for Kotak quotes; ktok = numeric index tokens tried for Kotak candles
    "NIFTY": {"yf": "^NSEI", "kotak": "Nifty 50", "ktok": ["26000"], "step": 50, "lot": 65},
    "BANKNIFTY": {"yf": "^NSEBANK", "kotak": "Nifty Bank", "ktok": ["26009"], "step": 100, "lot": 30},
    "FINNIFTY": {"yf": "NIFTY_FIN_SERVICE.NS", "kotak": "Nifty Fin Service", "ktok": ["26037"], "step": 50, "lot": 60},
}

DEFAULT_SETTINGS = {
    "underlying": "NIFTY",
    "timeframe": "5m",          # 1m, 5m, 15m, 30m, 60m
    "data_source": "KOTAK",     # KOTAK (real-time, needs consumer key) or YAHOO (free, ~1 min delay)
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
    "expiry": "",               # blank = nearest; or DDMMMYYYY e.g. 25NOV2026
    "max_trades_per_day": 3,
    "max_daily_loss": 3000.0,   # rupees; bot stops new entries after this
    "trade_start": "09:30",
    "no_new_entry_after": "14:45",
    "square_off_time": "15:15",
    "poll_seconds": 20,
    # SEBI: market orders are NOT allowed for retail algo trading -> always LIMIT at LTP +/- buffer
    "limit_buffer_pct": 2.0,    # buy at LTP+2%, sell at LTP-2%; exit retries widen to 4% then 8%
    "paper_delta": 0.5,         # paper P&L estimate = underlying move * delta
}


def _q(v: str) -> str:
    """Quote values that dotenv could mis-read (spaces, #, quotes)."""
    return f"'{v}'" if any(ch in v for ch in " #\"'") and "'" not in v else v


def save_env(values: dict) -> None:
    """Update/append KEY=value lines in .env, keeping every other line as-is."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={_q(values[key])}"
            done.add(key)
    lines += [f"{k}={_q(v)}" for k, v in values.items() if k not in done]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for k, v in values.items():
        os.environ[k] = v

APP_VERSION = "2026.11.18-3"
