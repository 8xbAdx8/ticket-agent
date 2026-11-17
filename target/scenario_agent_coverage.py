"""Mode-separated evidence counters; never merges DSL, SDK and real Agent scores."""
from target.scenario_quality import STATES,TRANSITIONS,ratio
from target.v39.registry import NAMES


def coverage(runs,mode):
    selected=[r for r in runs if r.get('mode')==mode]
    rows=[row for r in selected for row in r['rows']]
    valid=[row for row in rows if row.get('passed') is True and row.get('task_status')=='PASS']
    def outcome(row):
        if row.get('error') or row.get('task_status')=='FAIL' or row.get('invariant_status')=='FAIL':return 'FAIL'
        if row.get('passed') is True and row.get('task_status')=='PASS':return 'PASS'
        return 'NOT_SCORED'
    turns=[row for row in valid if row['kind']=='agent_turn' and not row.get('request_replayed')]
    tools={e['tool'] for row in turns for e in row['executed_tools'] if e.get('ok') is True}
    states={o['order_status'] for row in valid for o in row['after']['tables']['orders']}
    edges=set()
    for row in valid:
        old={o['order_id']:o['order_status'] for o in row['before']['tables']['orders']}
        for e in row['after']['tables']['audit_events']:
            if e in row['before']['tables']['audit_events'] or e.get('aggregate_type')!='order':continue
            edge=(e.get('from_state') or 'NONE',e.get('to_state'))
            if edge in TRANSITIONS:edges.add(edge)
    def refunded(row):
        rid=row.get('result',{}).get('refund_id')
        return row.get('passed') and rid and any(r['refund_id']==rid and r['status']=='SUCCEEDED' for r in row['after']['tables']['refund_requests']) and any(t['refund_id']==rid and t['transaction_type']=='REFUND' and t['status']=='SUCCEEDED' for t in row['after']['tables']['transactions'])
    flows=dict(query=bool(set(NAMES[:3])&tools),create='railway_create_order' in tools and 'PENDING_PAYMENT' in states,
               payment='railway_pay_order' in tools and 'PAID' in states,refund='railway_refund_order' in tools and any(refunded(row) for row in rows),
               change_cancel=bool({'railway_change_order','railway_cancel_order'}&tools) and bool({'CHANGED','CANCELLED'}&states))
    return dict(population=mode,execution_count=len(selected),
        tasks=dict(total=len(rows),pass_count=sum(outcome(r)=='PASS' for r in rows),failed=sum(outcome(r)=='FAIL' for r in rows),not_scored=sum(outcome(r)=='NOT_SCORED' for r in rows)),
        dimensions=dict(task_failures=sum(r.get('task_status')=='FAIL' for r in rows),invariant_failures=sum(r.get('invariant_status')=='FAIL' for r in rows),errors=sum(bool(r.get('error')) for r in rows)),
        tools=ratio(len(tools&set(NAMES)),len(NAMES),'distinct successful original-Agent tool calls in independently checked turns'),tool_names=sorted(tools),missing_tools=sorted(set(NAMES)-tools),
        states=ratio(len(states&STATES),len(STATES),'independently checked committed order states'),observed_states=sorted(states&STATES),
        transitions=ratio(len(edges&TRANSITIONS),len(TRANSITIONS),'observed database audit transitions in passing checked steps'),observed_transitions=sorted([list(e) for e in edges]),
        workflows=ratio(sum(flows.values()),5,'query/create/payment/refund/change-or-cancel; not a guarantee of every failure branch'),flow_evidence=flows,
        trace=ratio(sum(bool(r.get('trace_id') and r.get('events')) for r in turns),len(turns),'passing checked nonreplay model turns with original framework trace events'),
        all_turn_trace=ratio(sum(bool(r.get('trace_id') and r.get('events')) for r in rows if r['kind']=='agent_turn' and not r.get('request_replayed')),sum(r['kind']=='agent_turn' and not r.get('request_replayed') for r in rows),'all nonreplay model turns, including failed/truncated turns, with trace events'),
        security=dict(status='NOT_SCORED',reason='requires case-level rejection assertions; tool counts alone do not prove permission safety'),
        rag=dict(status='NOT_RUN',reason='this campaign does not validate answer-quality/RAG corpus'),
        reply_consistency=dict(status='PARTIAL',reason='bounded explicit business-success claims only; no general semantic judge'),
        multi_turn=ratio(sum(sum(row['kind']=='agent_turn' and row.get('passed') for row in r['rows'])>=2 for r in selected),len(selected),'runs with two independently checked original-Agent turns'))
