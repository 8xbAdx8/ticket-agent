"""Read-only projections of existing audits; never synthesize execution facts."""
import re


def workflow_rows(audit):
    rows=[]
    run=audit.get('trace_id')
    def add(kind,data,source,status='已记录'):
        rows.append({'run_id':run,'event_id':data.get('event_id'),
            'parent_event_id':data.get('parent_event_id'),'type':kind,'status':status,
            'timestamp':data.get('timestamp'),'latency_ms':data.get('latency_ms'),
            'source':source,'data':data})
    for i,event in enumerate(audit.get('framework_events') or []):
        add(event.get('event','未知事件'),event,f'framework_events[{i}]')
    fault=audit.get('fault_report') or {}
    for i,event in enumerate(fault.get('model_requests') or []):
        add('模型调用提议' if event.get('tool_calls') else '模型输出',event,f'fault_report.model_requests[{i}]')
    for i,event in enumerate(fault.get('executions') or []):
        for key in ('parameter_validation','execution_diagnostic'):
            if event.get(key):add(key,event[key],f'fault_report.executions[{i}].{key}')
        executed=event.get('executed')
        status=('已执行成功' if event.get('ok') is True else '已执行失败') if executed is True else '未执行／被拦截' if executed is False else '是否执行未记录'
        add(event.get('tool','工具'),event,f'fault_report.executions[{i}]',status)
    if audit.get('error'):add('运行异常',audit['error'],'error','失败')
    if audit.get('public_trace'):
        add('Agent 返回值',audit['public_trace'],'public_trace',
            '已返回' if audit.get('contract_returned') is True else '未返回' if audit.get('contract_returned') is False else '返回状态未记录')
    return rows


def policy_evidence(audit,results):
    reply=(audit.get('public_trace') or {}).get('reply','')
    rows=[]
    for i,result in enumerate(results):
        if result.get('tool')!='search_policy' or result.get('ok') is not True:continue
        for j,hit in enumerate((result.get('result') or {}).get('hits') or []):
            doc=hit.get('doc_id')
            rows.append({'doc_id':doc,'version':hit.get('version'),'rank':hit.get('rank'),
                'score':hit.get('score'),'content':hit.get('content'),'source':hit.get('source'),
                'trace_id':audit.get('trace_id'),
                'cited_in_reply':bool(doc and re.search(r'(?<![A-Za-z0-9])'+re.escape(doc)+r'(?![A-Za-z0-9])',reply)),
                'evidence_location':f'results[{i}].result.hits[{j}]'})
    return rows


RULE_CASES={1:('F01','F02'),2:('T01','T02','T03','T04','T05'),
    3:('R01','R02','R04','R06','R07'),4:('T17','T23'),5:('F07',),
    7:('R11',),8:('F03','T21','T22'),9:('T06','T07','T08','T09'),
    10:('F14',),11:('F13',),12:('R13','R14','T25')}


def rule_rows(prompt,catalogue,manifest):
    cases={c['id']:c for c in catalogue}
    rows=[]
    for match in re.finditer(r'(?m)^(\d+)\.(.*)$',prompt):
        number=int(match.group(1));ids=[x for x in RULE_CASES.get(number,()) if x in cases]
        rows.append({'rule_id':f'BASE-{number:02}', 'text':match.group(0),
            'case_ids':ids,'case_names':[cases[x]['name'] for x in ids],
            'mapping_basis':'人工核对规则原文与用例名称/expect；关联不代表通过' if ids else '待关联',
            'historical_code_sha':manifest.get('code_commit'),
            'verification':'已配置，当前版本尚未验证'})
    return rows
