# T046：GTFS跨日到达预期修订依据

本次修订只改新增版本化测试矩阵的预期，不修改生产时间转换、原始GTFS、原V1.2.2矩阵或历史失败日志。

- 原始包：`artifacts/runtime/railway-dataset-preparation-20261102-gtfs/output_gtfs.zip`。
- ZIP SHA256：`3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030`。
- trip_id：`01000K516502`，车次K5165，service_id=S1；calendar_dates中20261102为exception_type=1。
- 原始终点HJB，stop_sequence=5，arrival_time和departure_time均为`30:51:00`。
- GTFS时间从服务日零时累计：2026-11-02 + 30小时51分 = `2026-11-03T06:51:00+08:00`。30小时不能被理解为同一自然日的非法时刻，也不能忽略超过24小时的部分。
- 独立整数秒换算与现有静态Adapter返回一致。原预期`2026-11-03T23:53:00+08:00`与上述原件不符；未发现能支持23:53的该班次数据依据。

原件探针和结果：`artifacts/runtime/v391-d9-lifecycle-20261103-150639/gtfs-original-probe.json`。

新矩阵：`tests/v39/matrices/v391.json`，版本V3.9.1-r1，保留原T001–T056 ID及原矩阵SHA，并记录T046前后预期。历史V3.9失败仍是失败，不能改写为当时通过。修订版结果见本批batch-05的JUnit和pytest日志；这是Codex开发验证，不是B方正式103计分或Harness独立审查。
