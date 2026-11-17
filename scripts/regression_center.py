"""Offline regression batches: immutable inputs, isolated execution, inspectable outcomes."""
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
STORE=ROOT/'artifacts/runtime/regression-center'
PACKAGE='artifacts/deliverables/Ticket-Agent-V3.6-P0-离线复测包-20261029-v2.zip'
STEPS=(('environment','环境预检'),('evidence','证据与隔离副本'),('pytest','pytest 回归'),
       ('rag','RAG 离线检索评估'),('launcher','启动器预检'),('performance','可选数据库并发'),('protection','原文件保护校验'))
LABELS={'passed':'通过','failed':'失败','blocked':'阻塞','skipped':'未执行','running':'执行中','pending':'待执行','interrupted':'未完成（运行状态待确认）'}
GUARD='''import socket,ipaddress,os,json
_connect=socket.socket.connect
_connect_ex=socket.socket.connect_ex
def _allow(address):
 if not isinstance(address,tuple): return
 try: allowed=ipaddress.ip_address(address[0]).is_loopback
 except ValueError: allowed=False
 if not allowed:
  with open(os.environ['TICKET_REGRESSION_NETWORK_LOG'],'a',encoding='utf8') as f: f.write(json.dumps({'event':'external_connection_blocked'})+'\\n')
  raise OSError('offline regression blocked external connection')
def connect(s,a):
 _allow(a); return _connect(s,a)
def connect_ex(s,a):
 _allow(a); return _connect_ex(s,a)
socket.socket.connect=connect
socket.socket.connect_ex=connect_ex
'''


def now():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path=Path(path); temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');temporary.replace(path)


def source_files(root):
    """Source only; no secrets, environments, runtime data or symlink traversal."""
    result={}
    for directory,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if not d.startswith(('.git','.venv','.codex','.agents'))
                 and d not in ('artifacts','__pycache__','.pytest_cache','node_modules')
                 and not (Path(directory).name=='docs' and d=='evidence')
                 and not (Path(directory)/d).is_symlink()]
        for name in files:
            p=Path(directory)/name
            if p.is_symlink() or name.startswith('.env') or p.suffix.lower() in ('.zip','.db','.sqlite','.sqlite3','.pyc','.log','.key','.pem'):continue
            if p.suffix.lower() not in ('.py','.css','.md','.txt','.json','.jsonl','.csv','.toml','.ini','.cfg','.yaml','.yml','.cmd','.ps1'):continue
            result[p.relative_to(root).as_posix()]=p
    return result


def fingerprint(files):return sha(json.dumps({n:sha(p.read_bytes()) for n,p in sorted(files.items())},sort_keys=True).encode())


def environment(root,node):
    missing=[n for n in ('pytest','streamlit','langchain','langchain_deepseek','langchain_openai','chromadb','httpx') if importlib.util.find_spec(n) is None]
    if node and (not node.startswith('tests/') or '..' in PurePosixPath(node).parts or '\\' in node):raise ValueError('pytest 节点必须位于 tests/ 内')
    if node and not (root/node.split('::')[0]).is_file():raise ValueError('指定测试文件不存在')
    return {'python':sys.version.split()[0],'missing_dependencies':missing,'package_exists':(root/PACKAGE).is_file(),
            'mode':'offline_only','model_requests_enabled':False,'automatic_retries':0}


def protected_files(root):
    paths={}
    for folder in ('docs/evidence','data','cases','tests','traces','artifacts/runtime/v35-rag/index','artifacts/runtime/api-usage'):
        base=root/folder
        if base.is_dir():
            for directory,dirs,files in os.walk(base):
                dirs[:]=[d for d in dirs if d not in ('__pycache__','.pytest_cache') and not (Path(directory)/d).is_symlink()]
                for name in files:
                    p=Path(directory)/name
                    if p.is_file() and not p.is_symlink():paths[p.relative_to(root).as_posix()]=sha(p.read_bytes())
    return paths


def prepare(root,directory):
    """Use the corrected package only as frozen fixtures, overlay all current source."""
    snapshot=directory/'snapshot';snapshot.mkdir()
    package=root/PACKAGE
    with zipfile.ZipFile(package) as archive:
        receipt=json.loads(archive.read('ticket-agent/P0_补充证据校验.json'))
        for n,digest in {**receipt['evidence'],**receipt['cache_files']}.items():
            if sha(archive.read('ticket-agent/'+n))!=digest:raise ValueError('冻结证据哈希不一致：'+n)
        for entry in archive.infolist():
            name=PurePosixPath(entry.filename)
            if name.is_absolute() or '..' in name.parts or ':' in entry.filename or '\\' in entry.filename:raise ValueError('交接包包含非法路径')
            if entry.is_dir() or name.suffix=='.py':continue
            if any(p in ('.git','__pycache__') or p.startswith('.venv') or p.startswith('.env') for p in name.parts):continue
            dest=snapshot/Path(*name.parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.read(entry))
    checkout=snapshot/'ticket-agent'
    if os.name=='nt':
        link=str(checkout/'.venv-v35').replace("'","''");target=str(Path(sys.executable).parents[1]).replace("'","''")
        subprocess.run(['powershell','-NoProfile','-Command',f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' | Out-Null"],check=True,capture_output=True)
    current=source_files(root)
    for name,path in current.items():
        target=checkout/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    manifest={n:sha(p.read_bytes()) for n,p in sorted(current.items())}
    write(directory/'source-manifest.json',manifest)
    guard=directory/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD,encoding='utf8')
    env={k:v for k,v in os.environ.items() if not k.startswith(('AGENT_','DEEPSEEK_','DASHSCOPE_','RAG_','LANGCHAIN_','LANGSMITH_','TICKET_')) and not k.endswith(('_API_KEY','_TOKEN'))}
    env.update(PYTHONPATH=str(guard)+os.pathsep+str(checkout),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
        TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='1',LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',
        AGENT_PROVIDER='mock',AGENT_ENGINE='legacy',AGENT_USE_HTTP='0',AGENT_VECTOR_RAG='0',RAG_ALLOW_NETWORK='0',
        AGENT_DB_PATH=str(checkout/'artifacts/runtime/isolated.db'),AGENT_TRACE_DIR=str(checkout/'artifacts/runtime/isolated-traces'),
        TICKET_API_USAGE_DIR=str(checkout/'artifacts/runtime/api-usage'),TICKET_REGRESSION_NETWORK_LOG=str(directory/'network-blocks.jsonl'))
    return checkout,env,{'package_sha256':sha(package.read_bytes()),'source_files':len(manifest),'fixtures_verified':len(receipt['evidence'])+len(receipt['cache_files'])}


def run_command(command,cwd,env,log,timeout=900):
    started=time.monotonic()
    with log.open('w',encoding='utf8') as output:
        proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:code=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
            else:proc.kill()
            proc.wait();return {'exit_code':None,'category':'timeout','seconds':time.monotonic()-started}
    return {'exit_code':code,'seconds':round(time.monotonic()-started,3)}


def pytest_summary(path):
    report=read(path);rows=report.get('results',[])
    outcomes={};priority={'passed':0,'skipped':1,'failed':2}
    for row in rows:
        if not row.get('is_subtest') and priority[row['status']]>=priority.get(outcomes.get(row['case_id']),-1):outcomes[row['case_id']]=row['status']
    counts={s:sum(v==s for v in outcomes.values()) for s in ('passed','failed','skipped')}
    failures=[{'case_id':r['case_id'],'stage':r.get('stage'),'reason':r.get('assertion_evidence') or '未保存异常详情'}
              for r in rows if r['status']=='failed']
    counts.update(subtests_passed=sum(r['status']=='passed' and bool(r.get('is_subtest')) for r in rows),
                  subtests_failed=sum(r['status']=='failed' and bool(r.get('is_subtest')) for r in rows),failures=failures,exit_code=report.get('exit_code'))
    return counts


def launcher_checks(checkout,env,directory):
    rows=[]
    for name,mode,extra,expected in (
        ('离线','offline',{},'passed'),('DeepSeek配置','live',{'DEEPSEEK_API_KEY':'offline-check-only'},'passed'),
        ('Qwen配置','live',{'DASHSCOPE_API_KEY':'offline-check-only','DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1'},'passed'),
        ('缺少Key','live',{},'missing_key'),('百炼缺地址','live',{'DASHSCOPE_API_KEY':'offline-check-only'},'missing_bailian_base_url')):
        log=directory/('launcher-'+str(len(rows))+'.log')
        result=run_command([sys.executable,str(checkout/'scripts/launch_app.py'),'--mode',mode,'--check-only'],checkout,{**env,**extra},log,60)
        states=[]
        for line in log.read_text(encoding='utf8').splitlines():
            try:value=json.loads(line)
            except ValueError:continue
            if isinstance(value,dict):states.append(value)
        state=states[-1] if states else {}
        passed=(result['exit_code']==(0 if expected=='passed' else 2) and state.get('status')==expected and state.get('model_requests_sent')==0)
        rows.append({'case':name,'passed':passed,'expected_status':expected,'actual_status':state.get('status'),'model_requests_sent':state.get('model_requests_sent'),**result})
    return rows


def execute(root=ROOT,store=STORE,node='',rag=True,performance=False,notify=None):
    root=Path(root).resolve();store=Path(store).resolve()
    if not store.is_relative_to(root/'artifacts/runtime'):raise ValueError('批次目录必须位于项目 artifacts/runtime 内')
    directory=store/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True,exist_ok=False)
    files=source_files(root)
    try:git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,stderr=subprocess.DEVNULL).decode().strip()
    except (OSError,subprocess.SubprocessError):git_sha=None
    report={'schema':'ticket-regression-batch/1','batch_id':directory.name,'started':now(),'status':'running','owner':'A_offline_not_B_formal',
        'git_sha':git_sha,'source_sha256':fingerprint(files),'suite_sha256':fingerprint({n:p for n,p in files.items() if n.startswith('tests/')}),
        'configuration':{'pytest_node':node or 'tests','rag':rag,'performance':performance,'rag_origin':'offline_hash_not_real_embedding','python':sys.version.split()[0]},
        'steps':[{'id':k,'name':v,'status':'pending'} for k,v in STEPS],
        'network_policy':'external_socket_connections_blocked_no_real_keys','directory':str(directory)}
    report['config_sha256']=sha(json.dumps(report['configuration'],sort_keys=True).encode())
    before=protected_files(root);write(directory/'protected-before.json',before)
    checkout=env=None
    def publish():
        report['updated']=now();write(directory/'report.json',report)
        if notify:notify(report)
    publish()
    for step in report['steps']:
        step.update(status='running',started=now());publish();started=time.monotonic()
        try:
            key=step['id']
            if key=='environment':
                step['details']=environment(root,node)
                step['status']='passed' if not step['details']['missing_dependencies'] and step['details']['package_exists'] else 'blocked'
            elif key=='evidence':
                if report['steps'][0]['status']!='passed':step.update(status='blocked',reason='环境预检未通过，不创建执行副本')
                else:checkout,env,step['details']=prepare(root,directory);step['status']='passed'
            elif key=='protection':
                after=protected_files(root);changed=[n for n in before if after.get(n)!=before[n]];added=[n for n in after if n not in before]
                source_changed=fingerprint(source_files(root))!=report['source_sha256']
                step['details']={'checked':len(before),'changed_or_missing':changed,'added':added,'source_changed_during_run':source_changed}
                step['status']='failed' if changed or added or source_changed else 'passed'
            elif checkout is None or report['steps'][0]['status']!='passed':
                step.update(status='blocked',reason='环境或证据准备未通过，未执行该步骤')
            elif key=='pytest':
                out=checkout/'artifacts/runtime/center-pytest'
                command=[sys.executable,str(checkout/'scripts/v37_tests.py'),'--out',str(out)]
                if node:command+=['--case',node]
                step['process']=run_command(command,checkout,env,directory/'pytest-process.log')
                step['details']=pytest_summary(out/'results.json') if (out/'results.json').is_file() else {'failures':[],'reason':'未产生结构化测试结果；查看进程日志'}
                step['status']='passed' if step['process']['exit_code']==0 and step['details'].get('exit_code')==0 and not step['details']['failures'] else 'failed'
                for n in ('pytest.log','results.json','junit.xml'):
                    if (out/n).is_file():shutil.copy2(out/n,directory/n)
            elif key=='rag':
                if not rag:step.update(status='skipped',reason='本批次未选择RAG；不计为通过')
                else:
                    out=checkout/'artifacts/runtime/center-rag'
                    step['process']=run_command([sys.executable,str(checkout/'scripts/v37_rag.py'),'--out',str(out)],checkout,env,directory/'rag-process.log',300)
                    result=read(out/'report.json') if (out/'report.json').is_file() else {}
                    step['details']={k:v for k,v in result.items() if k!='rows'}
                    step['status']='passed' if step['process']['exit_code']==0 and result.get('metrics') else 'failed'
                    step['reason']='评估执行完成不代表检索质量达标；哈希向量不是真实Embedding'
                    if result:shutil.copy2(out/'report.json',directory/'rag-results.json')
            elif key=='launcher':
                step['details']=launcher_checks(checkout,env,directory);step['status']='passed' if all(r['passed'] for r in step['details']) else 'failed'
            elif key=='performance':
                if not performance:step.update(status='skipped',reason='未选择并发检查，不计为通过')
                else:
                    out=checkout/'artifacts/runtime/center-performance'
                    step['process']=run_command([sys.executable,str(checkout/'scripts/v37_performance.py'),'--out',str(out)],checkout,env,directory/'performance-process.log',180)
                    result=read(out/'report.json') if (out/'report.json').is_file() else {}
                    step['details']=[{k:v for k,v in r.items() if k!='rows'} for r in result.get('levels',[])]
                    step['status']='passed' if step['process']['exit_code']==0 and len(step['details'])==3 and all(r['idempotency_passed'] and r['failures']==0 for r in step['details']) else 'failed'
                    step['reason']='本地SQLite单波并发，不是模型吞吐量或持续容量上限'
                    if result:shutil.copy2(out/'report.json',directory/'performance-results.json')
        except Exception as exc:
            step.update(status='failed',reason='步骤异常：'+type(exc).__name__)
        step.update(ended=now(),seconds=round(time.monotonic()-started,3));publish()
    report['status']='failed' if any(s['status']=='failed' for s in report['steps']) else 'blocked' if any(s['status']=='blocked' for s in report['steps']) else 'completed'
    report['ended']=now()
    network=directory/'network-blocks.jsonl'
    report['blocked_external_connections']=len(network.read_text(encoding='utf8').splitlines()) if network.exists() else 0
    publish();(directory/'report.html').write_text(html_report(report),encoding='utf8')
    return report


def html_report(report):
    e=lambda x:html.escape(str(x))
    rows=''.join('<tr><td>'+e(s['name'])+'</td><td>'+e('评估执行完成' if s.get('id')=='rag' and s['status']=='passed' else LABELS[s['status']])+'</td><td>'+e(s.get('seconds','未记录'))+'</td><td>'+e(s.get('reason',''))+'</td></tr>' for s in report['steps'])
    sections=[]
    for step in report['steps']:
        details=step.get('details')
        if step.get('id')=='pytest' and isinstance(details,dict):
            sections.append('<h2>测试结果</h2><p>'+e('通过 '+str(details.get('passed','未知'))+' / 失败 '+str(details.get('failed','未知'))+' / 跳过 '+str(details.get('skipped','未知'))+'；子测试通过 '+str(details.get('subtests_passed','未知'))+' / 子测试失败 '+str(details.get('subtests_failed','未知')))+'</p>')
            for f in details.get('failures',[]):sections.append('<h3>'+e(f['case_id'])+'</h3><pre>'+e(f['reason'])+'</pre>')
        elif step.get('id')=='rag' and isinstance(details,dict):
            sections.append('<h2>RAG 离线诊断</h2><p>哈希向量；没有新的真实Embedding或模型成绩，不代表质量验收通过。</p><table><tr><th>模式</th><th>正样本</th><th>Recall@1</th><th>Recall@3</th><th>MRR</th><th>无答案误召回 / 负样本</th></tr>'+''.join('<tr>'+''.join('<td>'+e(v)+'</td>' for v in (m,r['positive_samples'],r['recall1'],r['recall3'],r['mrr'],str(r['no_answer_false_recall'])+' / '+str(r['negative_samples'])))+'</tr>' for m,r in details.get('metrics',{}).items())+'</table>')
    return '<!doctype html><meta charset="utf-8"><title>离线回归报告</title><style>body{font:15px sans-serif;max-width:1050px;margin:40px auto;padding:0 20px;color:#193340}td,th{border-bottom:1px solid #ddd;padding:14px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f7;padding:20px}table{width:100%;border-collapse:collapse}</style><h1>离线回归批次 '+e(report['batch_id'])+'</h1><p>A 工程验收；不替代 B 正式成绩。</p><p>批次状态：'+e(LABELS.get(report.get('status'),'流程完成' if report.get('status')=='completed' else '未知'))+'</p><p>Git '+e(report.get('git_sha') or '未记录')+' · 源码 '+e(report.get('source_sha256','未记录'))+'</p><table><tr><th>步骤</th><th>状态</th><th>秒</th><th>说明</th></tr>'+rows+'</table>'+''.join(sections)+'<details><summary>完整结构化证据（高级）</summary><pre>'+e(json.dumps(report,ensure_ascii=False,indent=2))+'</pre></details>'


def history(store=STORE):
    rows=[]
    for path in Path(store).glob('*/report.json'):
        try:
            record=read(path)
            if record.get('schema')=='ticket-regression-batch/1':
                if record['status']=='running':record={**record,'status':'interrupted'}
                rows.append(record)
        except (OSError,ValueError,KeyError):continue
    return sorted(rows,key=lambda r:r['started'],reverse=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node',default='');parser.add_argument('--skip-rag',action='store_true');parser.add_argument('--performance',action='store_true')
    args=parser.parse_args();result=execute(node=args.node,rag=not args.skip_rag,performance=args.performance)
    print(json.dumps({'batch_id':result['batch_id'],'status':result['status'],'directory':result['directory']},ensure_ascii=False))
    raise SystemExit(0 if result['status']=='completed' else 1)
