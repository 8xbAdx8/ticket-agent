# Independent Review Task — Ticket Agent V3.9.2

## Status to verify

- Implementation: **IMPLEMENTED**
- Development tests: **TESTED** (V39 164/0/0; original UI 38/38; old regression same 11 failures/1 skip)
- Live API: **PARTIAL** (Qwen/DeepSeek A/C pass; B tool call but prose count mismatch; D no mutation but error)
- Independent review: **NOT_RUN**
- User acceptance: **PENDING_USER_ACCEPTANCE**
- Protection: **BLOCKED** on unexplained `data/v39/simulation-v391.sqlite` change

## Required checks

1. **Original UI**: Confirm `web/app.py` routes to `web.conversation.user_page`; no independent railway page or business-mode radio. Check original hero, four quick entries, right rail, model settings, developer/test workspaces. Compare against Phase5 evidence if available.
2. **V3.9 bridge**: `web/v39_bridge.py` binds Context/Service/EffectiveConfig in original `Conversation._send`; V3.9 tools use same Registry/service; model cannot confirm.
3. **GTFS**: static only from `target/v39/static.py`/phase-eight DB; no second data source; real stations/trips/stops/cross-day; ambiguity rejected.
4. **Providers**: Qwen/DeepSeek real HTTP and tool calls; keys not in source/logs; no silent Mock fallback; model selection works; live UI DeepSeek ordinary chat works; investigate Qwen UI error.
5. **Tool/permissions**: old 8 unchanged; V39 11; Baseline old 8 only; Feature Flag/whitelist/write auth intact.
6. **D9/P01**: approved CHANGED_REFUND_P01; 3→1→change→1→1; failed refund retained; accounting/inventory invariants.
7. **B prose consistency**: actual route result 40; Qwen says 41, DeepSeek 38. Decide if UI exact table is sufficient or this is a blocking correctness issue.
8. **DB isolation**: launcher paths `v392-launcher/...`; session `v392-user/...`; product DBs not written; verify v391 conflict hash/contents.
9. **Old regression**: 1640/11/1, failure/skip IDs identical.
10. **T057–T076**: 20/20, db-probes.
11. **Protection**: 2100 fixture, GTFS, static DB, 103/B, old tickets, V1 docs, ledger prefix; no commit/push.
12. **API ledger**: prefix 274579 hash `87cfd3ed...` preserved; current append? record actual; never truncate.

## Evidence

- `docs/reviews/Ticket-Agent-V3.9.2-Implementation-Report.md`
- `Ticket-Agent-V3.9.2-UI-Restoration-Report.md`
- `Ticket-Agent-V3.9.2-Provider-Integration-Report.md`
- `Ticket-Agent-V3.9.2-GTFS-Integration-Report.md`
- `Ticket-Agent-V3.9.2-Database-Isolation-Report.md`
- `Ticket-Agent-V3.9.2-Qwen-Live-API-Test-Report.md`
- `Ticket-Agent-V3.9.2-DeepSeek-Live-API-Test-Report.md`
- `Ticket-Agent-V3.9.2-Browser-Visual-Regression-Report.md`
- `Ticket-Agent-V3.9.2-Git-Diff-Report.md`
- `artifacts/runtime/v392-original-ui-browser3/`
- `artifacts/runtime/v391-d9-lifecycle-20261103-234500-v392b/`
- `artifacts/runtime/v391-d9-lifecycle-20261103-150639/old-regression-v392-final/`

## Commands

```powershell
.\.venv-v35\Scripts\python.exe -B scripts/run_v39_tests.py --out artifacts/runtime/v391-d9-lifecycle-20261103-234500-v392b
.\.venv-v35\Scripts\python.exe -B artifacts/runtime/v391-d9-lifecycle-20261103-150639/run_old_regression.py old-regression-v392-final
powershell.exe -File scripts/Start-TicketAgent.ps1 -Mode offline -CheckOnly -NoBrowser
powershell.exe -File scripts/Start-TicketAgent.ps1 -Mode live -CheckOnly -NoBrowser
```

Use isolated `RAILWAY_SIM_DB_PATH` for any manual browser; never use product `data/v39/*.sqlite`. Do not send extra model requests without user approval.

## Forbidden

- Do not use Bridge, Commit/Push/Merge/Tag, or delete/rollback product DBs.
- Do not approve D9/D1–D8 or policy subdecisions.
- Do not claim B full pass while prose count differs from tool result.
- Do not treat DeepSeek development tests as independent review.
- Do not expose API keys.

## Verdict format

```text
VERDICT: GO_FOR_USER_ACCEPTANCE | BLOCKED
UI: PASS/FAIL
AGENT_GTFS: PASS/FAIL
PROVIDERS: PASS/PARTIAL/FAIL
D9_ACCOUNTING: PASS/FAIL
DB_ISOLATION: PASS/FAIL/BLOCKED
B_FACT_CONSISTENCY: PASS/FAIL
PROTECTION: ...
P0/P1/P2: ...
```
