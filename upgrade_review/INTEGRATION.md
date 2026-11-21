# Integration and acceptance plan

## 1. Preflight and risk
Wire helpers into live arming AND immediately before every new entry. Fail closed on stale data,
unknown broker state, missing metadata, quote failure, calendar closure or daily loss breach.
Use exchange calendar, timezone-aware IST timestamps, verified option lot size, margin and executable spread.
IP equality is not proof that Kotak has whitelisted the IP. Do not use hard-coded lot sizes live.
Include unrealized P&L and fees in daily loss accounting; persist counters across restarts.

## 2. Protective orders
The README has contradictory exit policies: an earlier section retries MARKET and a later section
requires LIMIT only. Resolve against current official broker/exchange rules before implementing.
NEVER send a spot-index stop value as an option-premium trigger. They are different instruments.
A broker-held premium stop is not an exact substitute for a spot-based strategy stop.
Verify supported stop-limit order type, trigger/limit relationship, tick size, freeze quantity,
expiry and product. SL-M support must not be assumed.
Record entry acknowledgement durably; reconcile partial fills before protecting filled quantity.
For discretionary exit, cancel protective order and confirm terminal state/fills before computing
remaining sell quantity. A cancel/fill race must not create a short position.
A stop-limit can remain unfilled through a gap; do not claim guaranteed protection.

## 3. Reconciliation
Implement durable order intents and broker IDs in SQLite with transactions before/after submission.
A timeout is UNKNOWN, not REJECTED. Never blindly resubmit a timed-out order.
Reconcile at startup, after every order event, and periodically with bounded polling.
Match exact exchange/instrument/product identifiers, signed units, partial fills and working orders.
Quantity equality alone does not prove a position has a valid protective order.
Mismatch pauses entries and alerts; do not automatically liquidate unrelated manual positions.
Test restart after entry acceptance but before local persistence and protective-stop fill races.

## 4. Options backtest
Use timestamped historical option bid/ask, expiry, strike, lot-size and underlying data.
Use only information available at signal time; enter no earlier than the next executable quote.
Model spreads, partial fills, costs/taxes using dated configuration, gaps and expiry changes.
Do not present spot points or fixed-delta proxy P&L as a realistic options backtest.
Share strategy signal/exit logic with live/paper engines, including delayed ADX confirmation window.
Add out-of-sample results and sensitivity analyses; do not infer profitability from a short sample.

## 5. Alerts
Implement bounded async queue with timeouts, retries, deduplication and delivery status.
No alert-network failure may block risk management or the main trading loop.
Redact credentials, TOTP secrets, tokens and personal data in logs/notifications.
Test loss of feed, reconciliation mismatch, rejection, unknown order and daily-loss events.
Do not send test messages without explicit user approval.

## 6. Deployment
Keep dashboard on loopback; access via SSH tunnel. Never expose an unauthenticated trading UI.
Add CSRF/origin validation and authenticated state-changing endpoints.
Use an unprivileged service account, protected EnvironmentFile, restricted logs and backups.
Service restart must start disarmed, reconcile broker state and require explicit live re-arming.
Static outbound IP, clock synchronization, heartbeat, log rotation and graceful shutdown are required.
Stopping a process does not close a position; clearly distinguish STOP and SQUARE OFF.

## Release gates
Paper integration tests, mocked broker tests, unknown-status/partial-fill/crash scenarios,
confirmed closed-candle handling and once-per-cross semantics must pass before any live consideration.
Keep live mode disabled until broker API contracts and applicable order rules are verified.
