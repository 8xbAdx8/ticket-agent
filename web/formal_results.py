"""Read-only import of teammate-supplied formal results; no new verdicts."""
import json,re
from collections import Counter
from web.evidence import DIMENSIONS, cases


def parse_formal_results(data, audits, session_id):
    if len(data)>2*1024*1024: raise ValueError('文件超过 2 MB')
    try: payload=json.loads(data.decode('utf-8-sig'))
    except (UnicodeError,ValueError): raise ValueError('文件必须是 UTF-8 JSON') from None
    if not isinstance(payload,dict) or payload.get('schema')!='ticket-agent-b-formal-results/1': raise ValueError('缺少受支持的 schema')
    meta=payload.get('batch')
    if not isinstance(meta,dict) or any(not isinstance(meta.get(k),str) or not meta[k].strip() for k in ('batch_id','git_sha','provider','model','mode')): raise ValueError('批次信息不完整')
    if not re.fullmatch(r'[0-9a-fA-F]{40}',meta['git_sha']):raise ValueError('git_sha 必须是完整 40 位 SHA')
    expected_mode={'deepseek_live':'live','bailian_live':'live','mock':'mock','langchain_mock':'mock'}.get(meta['provider'])
    if expected_mode is None or meta['mode']!=expected_mode:
        raise ValueError('Provider 与模式不匹配，mode 必须是 live 或 mock')
    records=payload.get('results')
    if not isinstance(records,list) or not records or len(records)>10000:raise ValueError('results 必须是非空列表且不超过 10000 条')
    catalogue={c['id']:c['dimension'] for c in cases()}
    trace_index={a.get('trace_id'):a for a in audits if a.get('trace_id')}
    accepted=[]; excluded=[]; seen=set()
    for r in records:
        if not isinstance(r,dict):raise ValueError('结果项必须是对象')
        case=r.get('case_id'); dimension=r.get('dimension'); verdict=r.get('verdict'); trace=r.get('trace_id')
        if not isinstance(case,str) or case not in catalogue or dimension!=catalogue[case]: raise ValueError('用例编号或维度与 B 用例目录不一致')
        if verdict not in ('pass','fail','indeterminate','skipped','not_applicable'):raise ValueError('结果状态无效')
        if not isinstance(trace,str) or not re.fullmatch(r'[0-9a-fA-F]{32}',trace):raise ValueError('每条结果必须有 32 位 Trace ID')
        if case in seen:raise ValueError('同一批次不能重复包含相同用例编号')
        seen.add(case)
        audit=trace_index.get(trace)
        if not audit:excluded.append({'case_id':case,'trace_id':trace,'reason':'当前会话未找到对应 Trace'});continue
        public=audit.get('public_trace') or {}
        if public.get('session_id')!=session_id or audit.get('provider')!=meta['provider'] or audit.get('model')!=meta['model']:
            excluded.append({'case_id':case,'trace_id':trace,'reason':'会话、Provider 或模型不匹配'});continue
        accepted.append({'id':case,'dimension':dimension,'status':{'pass':'passed','fail':'failed','indeterminate':'indeterminate','skipped':'skipped','not_applicable':'not_applicable'}[verdict], 'trace_id':trace})
    return {'batch':meta,'rows':accepted,'excluded':excluded,'total':len(records)}


def formal_dimensions(rows):
    result=[]
    for dimension in DIMENSIONS:
        counts=Counter(r['status'] for r in rows if r['dimension']==dimension)
        executed=counts['passed']+counts['failed']
        result.append({'dimension':dimension,'passed':counts['passed'],'failed':counts['failed'],
          'indeterminate':counts['indeterminate'],'skipped':counts['skipped'],'not_applicable':counts['not_applicable'],
          'executed':executed,'rate':counts['passed']/executed if executed else None})
    return result
