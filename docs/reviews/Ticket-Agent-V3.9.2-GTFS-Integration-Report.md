# V3.9.2 GTFS Integration Report

## Source of truth

- Adapter: `target/v39/static.py` (unchanged identity check)
- DB: `artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite`
- DB SHA256: `e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69`
- GTFS ZIP SHA256: `3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`
- Scale: 3169 stations / 11588 effective trips / 107669 stop times / 187 quarantined trips.

## Binding

Original Agent → `target.v39.registry` → `target/v39/static.py` → phase-eight SQLite. No second timetable, no UI SQLite access.

- Station/city search: real.
- Trip query: real.
- Stop times and cross-day: real planned schedule.
- Segment/sequence: Adapter `position`; no raw `sequence_index-1` assumption.
- Ambiguity: explicit station selection.
- Invalid trip: explicit rejection.
- `real_time=false`, `availability_available=false`, `fare_available=false`, `booking_available=false`.

## Read-only verification

The original GTFS ZIP and static SQLite hashes are unchanged from the protected start manifest. V3.9 tests pass against the Adapter; live Qwen/DeepSeek calls used actual `railway_query_trips`/`railway_search_stations` results.

## Caveat

The route query tool returned **40** trips for 2026-11-06 VNP→AOH; the live models' prose said 41 (Qwen) and 38 (DeepSeek). The tool table is authoritative; the model summary discrepancy is a residual not an Adapter data change.

## Status

`GTFS_IMPLEMENTED = YES`; `GTFS_IDENTITY_VERIFIED = YES`; `LIVE_MODEL_SUMMARY_CONSISTENCY = PARTIAL`.
