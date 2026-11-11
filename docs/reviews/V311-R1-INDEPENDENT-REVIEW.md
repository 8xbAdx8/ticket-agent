# V3.11-R1 Independent Read-Only Review

Reviewer: independent read-only sub-agent `5eb01187-fd6b-42a4-adc9-9679430b966a`. It did not modify files, databases, budgets, or evidence.

## Verdict

**CONDITIONAL_PASS** — core Live business evidence is real and independently reproducible from SQLite/JSON; final report/package had material inconsistencies and one reproducibility bug. Not a user acceptance and not a COMPLETE sign-off.

## Confirmed

- All 60 supplement request IDs and all 94 old-R1 request IDs match their budget ledgers; no orphan/duplicate.
- DeepSeek main order `V39-993...`: CANCELLED, paid 6000, refunded 5800, fee 200, net 200, active 0; P01 and transaction allocations independently checked.
- Qwen main order `V39-cfe...`: same verified state/amounts.
- DeepSeek cancel `V39-2bce...`: CANCELLED, hold RELEASED, paid 0.
- Qwen cancel `V39-3ac...` real, but from old R1 8-request run; supplement Qwen cancel `1abcb00c...` failed at 60/60 with no order. These are not the same result.
- Oracle is independent of Service, read-only, computes P01 itself. 49/49 full-chain checks, 27/27 cancel checks, 11/11 empty failed DB.
- Budget enforcement, per-execution idempotent finalize, and current full regression 2176/11/1 are supported.

## Findings accepted

1. Old R1 is 94/96, not 86/96; Qwen 46/48. Corrected in final report.
2. Current lifecycle CLI main must pass the initialized batch to run_chain/cancel_chain; fixed and byte-compiled. Supplement invocation needed explicit batch.
3. Final-delivery zip was stale; rebuilt from current evidence.
4. 5587 protection is **5586 unchanged + 1 approved exception + 1 API ledger append**, not 5587/0.
5. Browser full E2E not complete; it passed approval then stopped at consent/agent-session (one run also had an unconfigured batch). Layout is 8/8 only.
6. Oracle gap: CANCELLED cancel orders retain `active_item_count=1` and ACTIVE item rows; Oracle has no terminal-order rule. Documented, not hidden.
7. Finalize has a residual crash window between checkpoint and summary; normal double-finalize is idempotent. Documented.
8. Historical 8-request Qwen cancel is a separate old-batch pass; not counted as supplement.

## Not verified

- Full browser candidate review → approval → execution → Trace.
- User refusal/duplicate pay/duplicate refund/timeout/DB-failure total matrix.
- External human independent acceptance.
- Real cost (UNKNOWN).

## Recommendation

Keep **PARTIAL / CONDITIONAL_PASS** until browser E2E and an independent human/third-party sign-off are complete. Do not claim 86/96, 5587/0, or supplement Qwen cancel PASS.
