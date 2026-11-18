# VM ADX2 — Kotak Neo ADX/DI Auto-Trader (Python)

One-page dashboard and auto-trading bot. It reads NIFTY / BANKNIFTY / FINNIFTY candles, computes ADX(14), +DI, -DI and ATR(14), and **buys a CE or PE through Kotak Neo**, then manages the trade with an ATR trailing stop.

> Paper mode is the default. Real orders need **3 explicit steps**: `ALLOW_LIVE=true` in `.env` → Kotak TOTP login → click **Enable LIVE** and type `LIVE`.

## Strategy rules
| | CE (bullish) | PE (bearish) |
|---|---|---|
| Trigger | +DI crosses above −DI | −DI crosses above +DI |
| Filter | ADX between 20 and 35 **and** rising 2 candles, within 3 candles of the cross | same |
| Order | BUY ATM CE (MIS, market) | BUY ATM PE (MIS, market) |
| Initial SL | signal candle low (on spot) | signal candle high (on spot) |
| Trailing SL | after +1×ATR move, trail 2×ATR from best price | same, mirrored |
| Other exits | opposite DI cross, 15:15 square-off, manual Square off | same |
| Risk | max 3 trades/day, max daily loss ₹3000, no entry after 14:45 | same |

Everything above is editable from the dashboard. Signals use **closed candles only** (no repainting). One signal per crossover.

Why the "cross window": at the exact candle where DI lines cross, ADX is almost never rising (in testing: 0 of 155 crosses on NIFTY 5m). Allowing the ADX confirmation up to 3 candles after the cross makes the rule tradable.

## Setup (Windows)
1. Install Python 3.10–3.12 and Git.
2. Double-click `run_windows.bat` (creates venv, installs packages, copies `.env`).
3. Edit `.env` with your Kotak Neo details, restart, open http://127.0.0.1:8000

Git Bash / Linux / Mac: `./run.sh`

Manual:
```bash
python -m venv venv
venv\Scripts\activate          # Git Bash: source venv/Scripts/activate
pip install -r requirements.txt
copy .env.example .env         # Git Bash: cp .env.example .env
python app.py
```

## Kotak Neo credentials (`.env`)
| Key | Where to get it |
|---|---|
| `KOTAK_CONSUMER_KEY` | Kotak Neo app/web → Trade API → create application → token |
| `KOTAK_MOBILE_NUMBER` | Registered mobile, format `+91XXXXXXXXXX` |
| `KOTAK_UCC` | Your client code (profile page) |
| `KOTAK_MPIN` | Your 6-digit MPIN |
| `KOTAK_TOTP_SECRET` | Optional. Base32 secret shown when registering TOTP; lets the bot generate the TOTP. Otherwise type the TOTP in the dashboard. |

SDK: official [Kotak-Neo/Kotak-neo-api-v2](https://github.com/Kotak-Neo/Kotak-neo-api-v2) (`neo_api_client`), installed automatically from `requirements.txt`.

## Dashboard
- Status pills: Paper/LIVE, bot on/off, Kotak connected, market open
- Start / Stop / Refresh / **Square off** (kill switch)
- Kotak TOTP login, Enable LIVE (typed confirmation), Kotak positions & order book
- Live signal card: ADX, +DI, −DI, ATR, reason a signal fired or was rejected
- Price chart + ADX/DI chart, open position with stop & TSL status, P&L
- All strategy & risk settings, trade history, event log
- Trades are saved to `logs/trades.csv`, full log in `logs/bot.log`

## Backtest
```bash
python backtest.py --underlying NIFTY --tf 15m
python backtest.py --underlying BANKNIFTY --tf 5m --adx 25 --atr-mult 2.5
```
Underlying points only, before costs, on Yahoo's limited intraday history (~30–60 days). Treat it as a sanity check, not proof.

## Tests
```bash
pip install pytest && python -m pytest -q
```

## Safety design
- Live exits retry only if the sell order was **rejected or never accepted**. If status is pending/unknown it never sends a second sell (prevents an accidental short); the bot stops and tells you to square off in the Kotak app.
- Live entry is aborted if the Kotak option lookup fails.
- Can't switch modes while a position is open.
- Dashboard binds to `127.0.0.1` only. Don't expose it to the internet.
- `.env` is git-ignored. Never commit it.

## Known limitations — read before going live
- **Candle feed is Yahoo Finance** (free, may lag ~1 minute). The stop is checked on closed candles, so a fast move can go past your stop before exit. Use 5m+ timeframes.
- Kotak response field names (`pTrdSymbol`, `lLotSize`, `nOrdNo`, `ordSt`, `avgPrc`) are parsed defensively. **Do one 1-lot live test** and watch `logs/bot.log`; if the format differs, adjust `broker/kotak_neo.py`.
- Lot sizes in `config.py` (NIFTY 65, BANKNIFTY 30, FINNIFTY 60) are overridden by Kotak's scrip data when logged in. Check them with the exchange.
- Paper P&L without Kotak login is an estimate (spot move × 0.5 delta).
- The PC must stay on and awake during market hours.

Options can lose 100% of premium. This is a tool, not financial advice. Paper-trade first.
