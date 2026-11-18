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
