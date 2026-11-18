"""VM ADX2 - Kotak Neo ADX auto-trading dashboard.  Run:  python app.py"""
import logging
import os

import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import FileResponse

import config
from engine.trader import Trader

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler("logs/bot.log", encoding="utf-8"), logging.StreamHandler()],
)

app = FastAPI(title="VM ADX2")
trader = Trader()
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status")
def status():
    trader.update_spot()
    return trader.status()


@app.get("/api/chart")
def chart():
    return trader.chart


@app.post("/api/refresh")
def refresh():
    try:
        trader.refresh_data()
        return {"ok": True, "message": "Data refreshed"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)}


@app.post("/api/start")
def start():
    trader.start()
    return {"ok": True, "message": "Bot started"}


@app.post("/api/stop")
def stop():
    trader.stop()
    return {"ok": True, "message": "Bot stopped"}


@app.post("/api/settings")
def settings(body: dict = Body(...)):
    try:
        trader.update_settings(body)
        return {"ok": True, "message": "Settings saved"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Invalid setting: {e}"}


@app.post("/api/login")
def login(body: dict = Body(default={})):
    return trader.kotak.login(str(body.get("totp", "")).strip())


@app.post("/api/logout")
def logout():
    if trader.live:
        trader.set_live(False)
    trader.kotak.logout()
    return {"ok": True, "message": "Logged out"}


@app.post("/api/live")
def live(body: dict = Body(...)):
    if body.get("enable") and body.get("confirm") != "LIVE":
        return {"ok": False, "message": "Type LIVE to confirm"}
    return trader.set_live(bool(body.get("enable")))


@app.post("/api/squareoff")
def squareoff():
    return trader.exit_position("Manual square-off")


CRED_KEYS = {"consumer_key": "KOTAK_CONSUMER_KEY", "mobile_number": "KOTAK_MOBILE_NUMBER",
             "ucc": "KOTAK_UCC", "mpin": "KOTAK_MPIN"}


def _mask(v: str, keep: int = 4) -> str:
    return "" if not v else ("*" * max(len(v) - keep, 0)) + v[-keep:]


@app.get("/api/credentials")
def get_credentials():
    k = config.KOTAK
    return {"consumer_key": _mask(k["consumer_key"]), "mobile_number": "" if "X" in k["mobile_number"] else k["mobile_number"],
            "ucc": k["ucc"], "mpin_set": bool(k["mpin"]), "consumer_key_set": bool(k["consumer_key"])}


@app.post("/api/credentials")
def save_credentials(body: dict = Body(...)):
    new = {}
    for field, env_key in CRED_KEYS.items():
        v = str(body.get(field, "")).strip()
        if not v or "*" in v:  # blank or masked value = keep existing
            continue
        if any(ch in v for ch in "\r\n"):
            return {"ok": False, "message": f"Invalid {field}"}
        if field == "mobile_number" and not v.startswith("+"):
            v = "+91" + v.lstrip("0")
        if field == "mpin" and not (v.isdigit() and len(v) in (4, 6)):
            return {"ok": False, "message": "MPIN must be 4 or 6 digits"}
        new[env_key] = v
        config.KOTAK[field] = v
    if not new:
        return {"ok": False, "message": "Nothing new to save (fields unchanged)"}
    try:
        config.save_env(new)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Could not write .env: {e}"}
    trader.kotak.cfg = config.KOTAK
    saved = ", ".join(k.replace("KOTAK_", "") for k in new)
    return {"ok": True, "message": f"Saved to .env: {saved}. Click 'Test Kotak data', then TOTP + Login"}


@app.post("/api/test_kotak")
def test_kotak():
    und = config.UNDERLYINGS[trader.settings["underlying"]]
    try:
        spot = trader.kotak.index_ltp(und["kotak"])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Kotak live quote failed (check consumer key): {e}"}
    try:
        df = trader.kotak.candles(und, trader.settings["timeframe"])
        c = f"{len(df)} candles, last {str(df.index[-1])[:16]}"
    except Exception as e:  # noqa: BLE001
        c = f"candles failed: {str(e)[:150]}"
    return {"ok": True, "message": f"Kotak OK: {und['kotak']} LTP {spot:,.2f} | {c}"}


@app.get("/api/kotak/positions")
def kotak_positions():
    try:
        return {"ok": True, "data": trader.kotak.positions()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e), "data": []}


@app.get("/api/kotak/orders")
def kotak_orders():
    try:
        return {"ok": True, "data": trader.kotak.orders()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e), "data": []}


if __name__ == "__main__":
    print(f"\n  VM ADX2 dashboard -> http://{config.HOST}:{config.PORT}\n")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
