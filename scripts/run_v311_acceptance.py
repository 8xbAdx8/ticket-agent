"""Explicit, authorized ORIGINAL-Agent pilot. No model calls on import.

No candidate auto-approval, no DSL replay, no transaction retry. Each scenario
uses a new simulation database. Keep the process alive for its confirmation key.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def pilot(root):
    from target.api_config import bootstrap,model_config
    from target.scenario_live_budget import LiveBatch
    from target.scenario_live_agent import AgentRun,save
    bootstrap()
    configs=[model_config(p) for p in ('deepseek','bailian')]
    if not all(c['configured'] for c in configs):raise ValueError('BOTH_PROVIDERS_MUST_BE_CONFIGURED')
    hosts=[urlsplit(c['base_url']).hostname for c in configs]
    # Process-local bypass of an obsolete proxy; never changes system settings.
    os.environ['NO_PROXY']=os.environ['no_proxy']=','.join(['localhost','127.0.0.1',*hosts])
    batch=LiveBatch(root);batch.initialize_authorized()
    if batch.status()['http_requests']:
        raise ValueError('PILOT_ALREADY_STARTED_DO_NOT_REPEAT')
    plan=dict(mode='live_agent',providers=['deepseek','bailian'],goal='3 synthetic passengers: static query, proposal, trusted create, pay proposal, trusted payment',
              source='operator pre-reviewed natural-language acceptance; not AI-generated candidate',
              budget=dict(max_pilot=24,max_per_provider=12,output=2048,cost='UNKNOWN'),no_transaction_retry=True)
    save(root/'pilot-plan.json',plan)
    results=[]
    for provider in plan['providers']:
        run=AgentRun(root,provider)
        info=dict(provider=provider,execution_id=run.id,root=str(run.root),mode=run.mode)
        results.append(info)
        try:
            def turn(message,tools):
                row=run.turn(message,expectations=dict(required_tools=tools))
                print(json.dumps(dict(provider=provider,step=len(run.rows),passed=row['passed'],task=row['task_status'],http=batch.status()['providers'][provider]),ensure_ascii=False),flush=True)
                if not row['passed']:raise ValueError('PILOT_TASK_FAILED_REVIEW_EVIDENCE')
                return row
            turn('请查询2026年11月5日上海虹桥AOH到杭州东HGH的静态车次，最多返回3班；请先检索上海虹桥车站并查询车次，再查看第一班的完整经停。只读查询，不做订单。',
                 ['railway_search_stations','railway_query_trips','railway_trip_stops'])
            turn('选择刚查到的第一班、同一天同区间、二等座。请查询3人的模拟库存、计算3人模拟报价，并为合成甲、合成乙、合成丙生成建单提案，联系人使用当前登录的模拟用户手机号。只生成提案，等待我的确认，不要声称已建单或已锁座。',
                 ['railway_check_inventory','railway_quote_fare','railway_create_order'])
            pending=run.pending()
            if len(pending)!=1:raise ValueError('ONE_CREATE_PROPOSAL_REQUIRED')
            preview=run.decision_preview(pending[0]['proposal_id'])
            if preview['action']!='CREATE_ORDER':raise ValueError('CREATE_PROPOSAL_REQUIRED')
            decision=run.confirm(preview,True,actor='test_user')
            if not decision['passed']:raise ValueError('CREATE_RECEIPT_FAILED')
            oid=decision['result']['order_id']
            total=decision['after']['tables']['orders'][0]['total_fen']
            turn(f'我确认刚才已创建的模拟订单是{oid}，总金额{total}分。现在请为此订单生成模拟支付提案，金额必须匹配。只生成确认卡，等我确认。',['railway_pay_order'])
            pending=[p for p in run.pending() if p['action']=='PAY']
            if len(pending)!=1:raise ValueError('ONE_PAYMENT_PROPOSAL_REQUIRED')
            decision=run.confirm(run.decision_preview(pending[0]['proposal_id']),True,actor='test_user')
            if not decision['passed']:raise ValueError('PAYMENT_RECEIPT_FAILED')
            info['status']='PASS';info['order_id']=oid
        except Exception as exc:
            # Never restart or retry failed transactional turns to obtain PASS.
            info['status']='FAIL';info['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        save(run.root/'pilot-outcome.json',info)
    save(root/'pilot-summary.json',dict(plan=plan,results=results,budget=batch.status()))
    print(json.dumps(dict(results=results,budget={k:v for k,v in batch.status().items() if k!='requests'}),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Required: authorizes this explicit execution only within existing authorization.json')
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    if not args.live:parser.error('--live required; no implicit API invocation')
    pilot(args.root.resolve())
