"""Isolated local SQLite idempotency load; never invokes a model."""
import argparse,json,sys,time,statistics,threading
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))

def run(out,levels=(1,10,50)):
    import config
    from target import mock_core
    from data.seed import build_db
    from web.runtime import scoped
    out.mkdir(parents=True,exist_ok=False);reports=[]
    for concurrency in levels:
        folder=out/str(concurrency);folder.mkdir();db=folder/'tickets.db'
        build_db(db)
        with scoped({'DB_PATH':db}):
            day=(config.today()+timedelta(days=1)).isoformat()
            lock=mock_core.lock_seat('G7301',day,'二等座',['性能测试乘客'])
            if 'lock_id' not in lock:raise RuntimeError('load_setup_failed')
            gate=threading.Barrier(concurrency)
            def task(i):
                gate.wait(timeout=30);t=time.perf_counter()
                try:
                    r=mock_core.create_order(lock['lock_id'],['性能测试乘客'],config.CURRENT_USER_PHONE)
                    return {'index':i,'latency_ms':(time.perf_counter()-t)*1000,'ok':'error' not in r,'result':r}
                except Exception as e:return {'index':i,'latency_ms':(time.perf_counter()-t)*1000,'ok':False,'error':type(e).__name__}
            cpu=time.process_time();start=time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:rows=list(pool.map(task,range(concurrency)))
            elapsed=time.perf_counter()-start; cpu=time.process_time()-cpu
            times=sorted(r['latency_ms'] for r in rows)
            percentile=lambda p:times[max(0,__import__('math').ceil(len(times)*p)-1)]
            ids={r['result'].get('order_id') for r in rows if r['ok']}
            import sqlite3
            with closing(sqlite3.connect(db)) as c:orders=c.execute('SELECT count(*) FROM orders WHERE lock_id=?',(lock['lock_id'],)).fetchone()[0]
            reports.append({'concurrent_clients':concurrency,'requests':len(rows),'success':sum(r['ok'] for r in rows),
                'failures':sum(not r['ok'] for r in rows),'qps':len(rows)/elapsed,'elapsed_s':elapsed,'mean_ms':statistics.mean(times),
                'p50_ms':percentile(.5),'p95_ms':percentile(.95),'p99_ms':percentile(.99),'cpu_process_seconds':cpu,
                'rss_bytes':None,'timeouts':None,'db_lock_wait_ms':None,'orders_for_lock':orders,
                'idempotency_passed':orders==1 and len(ids)==1,'rows':rows})
        db.unlink()  # Only this newly-created synthetic database; raw request evidence remains.
    result={'mode':'offline_sqlite_same_lock','real_api_requests':0,'python':sys.version,'levels':reports,
            'limits':'One synchronized wave per level; not a sustained capacity benchmark. Timeouts and lock waits are not separately instrumented.'}
    (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
