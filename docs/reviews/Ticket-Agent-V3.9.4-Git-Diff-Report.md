# Ticket Agent V3.9.4 — Git Difference Report

HEAD: `4340b6640025be95e8300a3d625a32cfb431e35d`  
Branch: `feat/ticket-agent-v36-stabilization`  
Staged: 0  
Commit/Push/Merge/Tag: **none**

## This-round functional changes

- `web/railway_defaults.py` (new): stable GTFS defaults, station preference, inventory, six-state classification.
- `web/user_features.py`: default high-speed ticket query uses V3.9 GTFS; panels have stable defaults; side-panel error isolation; Feature Flag-off compatibility fallback.
- `web/demo.py`: four-step demo uses local GTFS + V3.9 service; confirmations; no model.
- `web/demo_legacy.py` (new): legacy demo compatibility when V3.9 feature is off.
- `web/railway_queries.py`: default route/date/train; six-state cards; no session-level chat error.
- `web/conversation.py`: current request error lifetime; suppress stale success cards while showing current error.
- `target/v39/store.py`: allow only new `v394-` namespace.
- `scripts/run_v39_tests.py`: allow `v394-implementation-` test output.
- `tests/v39/test_v394_defaults.py` (new): T077–T100.

## Existing worktree

V3.9.3 already had 74 modified/untracked entries before this round. They are not attributed to V3.9.4 and were not cleaned/reset. `git status` remains a large historical worktree.

```text
 PROJECT_STATUS.md                                  | 363 ++++++++++++++++++++-
 scripts/launch_app.py                              |   5 +-
 target/agent.py                                    |   8 +-
 target/bailian_runtime.py                          |   6 +-
 target/deepseek_runtime.py                         |   5 +-
 target/langchain_agent.py                          |  36 +-
 target/live_providers.py                           |   3 +-
 target/reply_consistency.py                        |  22 ++
 target/train_source.py                             |  18 +-
 web/conversation.py                                |  46 ++-
 web/demo.py                                        | 217 ++++++++----
 web/design.css                                     | 129 +++++++-
 web/design.py                                      |  18 +-
 web/presentation.py                                |   2 +
 web/runtime.py                                     |  21 +-
 web/train_data.py                                  |  18 +-
 web/user_features.py                               |  89 ++++-
 web/user_layout.css                                |  40 +++
 web/user_layout.py                                 |   3 +-
 ...34\250\347\272\277\346\250\241\345\274\217.cmd" |   1 +
 ...46\273\347\272\277\346\250\241\345\274\217.cmd" |   1 +
 21 files changed, 938 insertions(+), 113 deletions(-)
```

`git diff --check` exit: 0  
Output: warning: in the working copy of 'scripts/launch_app.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'target/reply_consistency.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'target/train_source.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/design.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/train_data.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'web/user_layout.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '启动_在线模式.cmd', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '启动_离线模式.cmd', LF will be replaced by CRLF the next time Git touches it


## Untracked/new this round

- web/railway_defaults.py
- web/demo_legacy.py
- tests/v39/test_v394_defaults.py
- docs/reviews/Ticket-Agent-V3.9.4-*.md
- artifacts/runtime/v394-* evidence

No commit/push/merge/tag; no reset of other worktree changes.
