"""M8确定性并发探针。正常走原业务；缺陷只存在于临时影子库的新schema。"""
import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import config
from data.seed import build_db
from target import mock_core
from target.diagnostics import assertion, authority_snapshot, digest, mutation_events, sanitize, save_audit
from target.fault_injection import FaultRun

SCENARIOS=("same_lock_two","same_lock_many","same_request_retry","different_locks","expired_lock","worker_failure","query_after_retry")


def _shadow(source,target):
    """只在新临时库的DDL中移除锁座唯一性；绝不ALTER源库。"""
    import re
    with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(target)) as dest:
        for table in ("inventory","locks","orders","users"):
            ddl=src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
            if table=="orders":
                changed=re.sub(r"\block_id\s+TEXT\s+UNIQUE\b","lock_id TEXT",ddl,flags=re.I)
                if changed==ddl:raise RuntimeError("test mutation schema not recognized")
                ddl=changed
            dest.execute(ddl)
            rows=src.execute("SELECT * FROM "+table).fetchall()
            if rows:dest.executemany("INSERT INTO "+table+" VALUES ("+",".join("?" for _ in rows[0])+")",rows)
        dest.commit()


def _mutant_create(path,lock_id,passengers,contact,read_gate):
    """受控错误：所有线程先完成去重读，屏障后不重新检查，分别提交。"""
    with closing(sqlite3.connect(path,timeout=5)) as c:
        c.row_factory=sqlite3.Row
        previous=c.execute("SELECT * FROM orders WHERE lock_id=?",(lock_id,)).fetchone()
        lock=c.execute("SELECT * FROM locks WHERE lock_id=?",(lock_id,)).fetchone()
        inv=c.execute("SELECT price FROM inventory WHERE train_no=? AND date=? AND seat_type=?",
                      (lock["train_no"],lock["date"],lock["seat_type"])).fetchone() if lock else None
    read_gate.wait(timeout=10)
    if previous:return {**dict(previous),"idempotent_hit":True}
    if contact!=config.CURRENT_USER_PHONE:return {"error":"仅可为当前模拟用户创建订单"}
    if not lock:return {"error":"lock_id不存在"}
    if lock["used"]==2 or lock["expire_at"]<=config.now().isoformat():return {"error":"锁座已过期"}
    if passengers!=json.loads(lock["passengers"]):return {"error":"乘客不一致"}
    order_id="OD_MUT_"+uuid.uuid4().hex[:12]
    with closing(sqlite3.connect(path,timeout=5)) as c:
        c.row_factory=sqlite3.Row;c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",(order_id,contact,lock["train_no"],lock["date"],lock["seat_type"],
            json.dumps(passengers,ensure_ascii=False),inv[0]*len(passengers),"pending",config.now().isoformat(),lock_id))
        c.execute("UPDATE locks SET used=1 WHERE lock_id=?",(lock_id,));c.commit()
        return dict(c.execute("SELECT * FROM orders WHERE order_id=?",(order_id,)).fetchone())


def probe(scenario="same_lock_two", *, mutant=False, workers=None, save=False, trace_dir=None):
    if scenario not in SCENARIOS:raise ValueError("unknown concurrency scenario")
    if mutant and scenario in ("expired_lock","worker_failure"):
        raise ValueError("M8缺陷演示使用正常有效锁座；过期/失败场景验证原实现")
    workers=workers if workers is not None else (4 if scenario in ("same_lock_many","different_locks") else 2)
    if type(workers) is not int or not 2<=workers<=8:raise ValueError("workers must be 2..8")
    base=config.BASE_DIR/"artifacts/runtime";base.mkdir(parents=True,exist_ok=True)
    trace_id=uuid.uuid4().hex
    fault=FaultRun({"concurrent_duplicate_order":True} if mutant else {},"concurrency-"+scenario,"backend_concurrency",trace_id)
    with tempfile.TemporaryDirectory(prefix="v32-probe-",dir=base) as temp:
        root=Path(temp);source=root/"normal.db";store=root/"mutant.db" if mutant else source
        with contextlib.redirect_stdout(io.StringIO()):build_db(source)
        locks=[]
        with mock_core.database_scope(source):
            for _ in range(workers if scenario=="different_locks" else 1):
                lock=mock_core.lock_seat("G7301",config.today().isoformat(),"二等座",["张三"])
                if "error" in lock:raise RuntimeError("probe lock setup failed")
                locks.append(lock)
        if scenario=="expired_lock":
            with closing(sqlite3.connect(source)) as c:
                c.execute("UPDATE locks SET expire_at='2000-01-01T00:00:00'");c.commit()
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        before=authority_snapshot(source)
        if mutant:_shadow(source,store)
        arrival=threading.Barrier(workers);read_gate=threading.Barrier(workers) if mutant else None
        request_ids=["same-request" if scenario=="same_request_retry" else "req-"+str(i) for i in range(workers)]
        def worker(index):
            started=time.perf_counter_ns();thread_id=threading.get_ident()
            lock=locks[index] if scenario=="different_locks" else locks[0]
            arrival.wait(timeout=10)
            try:
                if scenario=="worker_failure" and index==0:raise RuntimeError("declared worker failure before write")
                if mutant:
                    result=_mutant_create(store,lock["lock_id"],["张三"],config.CURRENT_USER_PHONE,read_gate)
                else:
                    with mock_core.database_scope(source):
                        result=mock_core.create_order(lock["lock_id"],["张三"],config.CURRENT_USER_PHONE)
                return {"request_id":request_ids[index],"worker":index,"thread_id":thread_id,"lock_id":lock["lock_id"],
                        "result":result,"exception":None,"started_ns":started,"finished_ns":time.perf_counter_ns()}
            except Exception as exc:
                return {"request_id":request_ids[index],"worker":index,"thread_id":thread_id,"lock_id":lock["lock_id"],
                        "result":None,"exception":type(exc).__name__,"declared_failure":scenario=="worker_failure" and index==0,
                        "started_ns":started,"finished_ns":time.perf_counter_ns()}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            requests=list(executor.map(worker,range(workers)))
        with mock_core.database_scope(store):followup=mock_core.query_order()
        after=authority_snapshot(store)
        counts=Counter(row["lock_id"] for row in after["orders"])
        returned={r["result"]["order_id"] for r in requests if r.get("result") and "order_id" in r["result"]}
        stored={o["order_id"] for o in after["orders"]}
        used={l["lock_id"]:l["used"] for l in after["locks"]}
        unexpected=[r for r in requests if r.get("exception") and not r.get("declared_failure") or
                    isinstance(r.get("result"),dict) and "error" in r["result"] and scenario!="expired_lock"]
        expected_count=0 if scenario=="expired_lock" else workers if scenario=="different_locks" else 1
        checks=[assertion("one_order_per_lock",all(n<=1 for n in counts.values()),"same lock has independent duplicate orders",["authority/orders"]),
                assertion("expected_order_count",len(stored)==expected_count,"order count violates scenario expectation",["authority/orders"]),
                assertion("returned_orders_match_database",returned==stored,"returned IDs differ from persisted orders",["requests","authority/orders"]),
                assertion("order_ids_unique",len(stored)==len(after["orders"]),"duplicate order IDs",["authority/orders"]),
                assertion("lock_order_status_consistent",all(o["status"]=="pending" and used[o["lock_id"]]==1 for o in after["orders"]),"illegal order/lock state",["authority"]),
                assertion("no_unexpected_worker_errors",not unexpected,"unexpected error or partial operation",["requests"]),
                assertion("independent_locks_do_not_collide",scenario!="different_locks" or len(counts)==workers,"different valid locks contaminated each other",["authority/orders"]),
                assertion("followup_query_matches_persisted_orders",followup["count"]==len(stored),"follow-up query misses persisted orders",["followup_query"]),
                assertion("all_requests_reached_barrier",len({r["thread_id"] for r in requests})==workers,"workers did not overlap at start barrier",["requests"])]
        defect=any(c["passed"] is False for c in checks)
        for check in checks:
            check["evidence_refs"]=[f"audit:{trace_id}#/"+ref for ref in check["evidence_refs"]]
        if mutant:
            fault.emit("concurrent_duplicate_order",{"orders_per_lock":1,"original_schema_unique_lock_id":True},
                {"orders_per_lock":dict(counts),"source_database_unchanged":hashlib.sha256(source.read_bytes()).hexdigest()==source_hash},
                status="not_applicable" if scenario=="different_locks" else "applied",
                reason="不同lock没有竞争同一幂等键" if scenario=="different_locks" else None,
                target="temporary shadow orders schema and check-before-barrier scheduling",test_only=True)
        audit={"schema_version":"ticket-agent-audit/3.2","trace_id":trace_id,"timestamp":__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            "provider":"backend_concurrency","model":None,"scenario":scenario,"mode":"mutant_shadow" if mutant else "normal_backend",
            "fault_report":fault.report(),"mutation_events":mutation_events(fault.report(),trace_id),"requests":requests,
            "authority_before":before,"authority":after,"followup_query":followup,
            "database_isolation":{"temporary_only":True,"source_schema_not_altered":True,"shadow_only_mutation":mutant,
                                  "source_data_unchanged_in_mutant":hashlib.sha256(source.read_bytes()).hexdigest()==source_hash if mutant else None},
            "concurrency":{"workers":workers,"arrival_barrier":True,"read_before_write_barrier":mutant,"application_global_mutex":False,
                           "sqlite_single_writer_transactions":True,"note":"requests overlap; SQLite commits serialize natively, no application-wide lock added"},
            "judgement":{"case_id":scenario,"expected_behavior":"same lock unique; different locks independent; declared failures do not partially write",
                "actual_behavior":{"orders":len(stored),"distinct_returned_ids":len(returned),"counts_by_lock":dict(counts)},"assertions":checks,
                "dimensions":{"injection_applied":True if mutant and scenario!="different_locks" else None,"platform_defect_detected":defect,"agent_anomaly_recognized":None,
                              "agent_recovered":None,"safe_stop":None,"business_correct":not defect},
                "quality_verdict":"fail" if defect else "pass","test_verdict":"not_applicable" if mutant and scenario=="different_locks" else "pass" if (defect if mutant else not defect) else "fail",
                "failure_reasons":[c["failure_reason"] for c in checks if c["passed"] is False]},
            "real_api_requests":0,"resources_cleaned":False}
    audit["resources_cleaned"]=not root.exists()
    audit=sanitize(audit)
    if save:save_audit(audit,trace_dir)
    return audit
