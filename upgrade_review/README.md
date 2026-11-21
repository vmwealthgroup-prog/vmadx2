# VM ADX2 upgrade bundle — NOT an integrated release

This bundle is based only on the pasted README. The existing application source was not available.
Do not replace your repository with this bundle. Copy it into a separate `upgrade_review/` directory.
No credentials, broker implementation, live trading, deployment activation, or profitability claims are included.

## Included
- Standalone Python safety helpers: fail-closed preflight checks, timezone-aware freshness,
  tick-rounded limit prices, position quantity comparison, conservative retry decisions.
- Unit tests for these helpers only.
- Integration and acceptance checklist covering the six proposed upgrades.

## Test (Python 3.10+)
Run from this directory: `python -m unittest -v test_safety`
Windows may require: `pip install tzdata`

## Not implemented
Kotak login/data/orders, protective stop placement, automatic reconciliation scheduler,
alerts transport, dashboard integration, options backtesting and production VPS setup.
The helper tests do not validate the existing trading application or live broker behavior.

## Required to finish
Upload the current repository ZIP excluding `.env`, logs, credentials and venv.
Preserve your working app until an integrated patch is reviewed and tested.
