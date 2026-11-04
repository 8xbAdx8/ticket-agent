# V3.9.2 Database Isolation Report

## Implemented

- `scripts/launch_app.py` now always sets:
  - offline: `artifacts/runtime/v392-launcher/offline/<date>/simulation.sqlite`
  - live: `artifacts/runtime/v392-launcher/live/<date>/simulation.sqlite`
  - printed in launcher state/log as `railway_database`.
- `target/v39/store.py` allows only `v392-*` in addition to the existing V3.9 namespaces; old `tickets.db`/static DB/protected paths remain forbidden.
- `web/v39_bridge.py` default session DB: `artifacts/runtime/v392-user/<date>/simulation.sqlite`.
- `web/railway_simulation.py` default changed away from `data/v39/simulation-v391.sqlite` to the v392 isolated namespace.
- Tests continue to use `artifacts/runtime/v391-*` isolated DBs.

## Launcher evidence

`Start-TicketAgent.ps1 -Mode offline -CheckOnly -NoBrowser`:

```text
railway_database: artifacts/runtime/v392-launcher/offline/2026-11-03/simulation.sqlite
status: passed
```

`Start-TicketAgent.ps1 -Mode live -CheckOnly -NoBrowser`:

```text
railway_database: artifacts/runtime/v392-launcher/live/2026-11-03/simulation.sqlite
status: passed
```

No `setx`; no system environment mutation; no deletion.

## Protection finding (must be reported)

Start manifest recorded `data/v39/simulation-v391.sqlite` before V3.9.2. Current file:

- start: 430080 bytes / `0f887d224268b65b74f2436a8dd2665d9ddb5cce6f8e22c75459f6ceea35666a`\n- current: 462848 bytes / `9ebf39ecd8fd4caa277d6fa993ef0bbbeeb99355ab997d23a37678d0c44af939`\n- mtime: `2026-11-03 22:57:53`
- 462848 bytes
- contains 1 worker lease, 1 scenario, 12 inventory rows, 1 quote, 1 proposal, 0 orders/transactions/refunds, 11 audit events.

It no longer matches the start hash. This write occurred during the V3.9.2 window but **before the isolated V3.9.2 browser/probe runs**; no order or transaction exists. It is recorded as an unresolved protection conflict. The file was **not deleted, reset, truncated or overwritten** by this report. No further product DB write was performed after discovery; all subsequent work uses `v392-*`.

`data/v39/simulation.sqlite` remains unchanged (380928 bytes, SHA from start manifest).

## Status

`ISOLATED_DB_PATH = IMPLEMENTED`  
`LAUNCHER_PATH_LOGGING = VERIFIED`  
`PRODUCT_DB_PROTECTION = BLOCKED` (unexplained v391 quote/proposal/audit; no orders)  
`OLD_DB_DELETE = NO`.

