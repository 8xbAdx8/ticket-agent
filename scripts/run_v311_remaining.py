"""Reviewed continuation in NEW databases; never restores a confirmation secret."""
import argparse,json,os,sys,hashlib
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def execute(root):
    from target.api_config import bootstrap,model_config
    from target.scenario_live_agent import AgentRun,save
    from target.scenario_live_budget import LiveBatch
    bootstrap()
    configs=[model_config(p) for p in ('deepseek','bailian')]
    if not all(c['configured'] for c in configs):raise ValueError('PROVIDER_CONFIGURATION_REQUIRED')
    os.environ['NO_PROXY']=os.environ['no_proxy']=','.join(['localhost','127.0.0.1',*[urlsplit(c['base_url']).hostname for c in configs]])
    batch=LiveBatch(root)
    review=json.loads((root/'remaining-release-review.json').read_text('utf8'))
    reassessment=root/'pilot-reassessment-v2.json'
    if review.get('reassessment_sha256')!=hashlib.sha256(reassessment.read_bytes()).hexdigest():raise ValueError('REVIEW_EVIDENCE_CHANGED')
    batch.release_remaining(review)
    # Exclusive start marker prevents repeated invocations from spending more.
    save(root/'remaining-start.json',dict(batch_id=batch.status()['batch_id'],prior_http=batch.status()['http_requests'],scope='new scenarios only',goal='create/pay/partial refund/change/final refund'))
    results=[]
    for provider in ('deepseek','bailian'):
        run=AgentRun(root,provider);info=dict(provider=provider,execution_id=run.id,mode=run.mode)
        results.append(info)
        try:
            def turn(message,tools,args=None):
                if 25-batch.status()['providers'][provider]<2:raise ValueError('INSUFFICIENT_PROVIDER_REMAINDER_NO_DISPATCH')
                row=run.turn(message,expectations=dict(required_tools=tools,args=args or {}))
                print(json.dumps(dict(provider=provider,step=len(run.rows),passed=row['passed'],requests=batch.status()['providers'][provider],task=row['task_status']),ensure_ascii=False),flush=True)
                if not row['passed']:raise ValueError('TASK_FAILED_REVIEW_REQUIRED')
                return row
            def confirm(action):
                proposals=[p for p in run.pending() if p['action']==action]
                if len(proposals)!=1:raise ValueError('ONE_MATCHING_PROPOSAL_REQUIRED')
                row=run.confirm(run.decision_preview(proposals[0]['proposal_id']),True,actor='test_user')
                if not row['passed']:raise ValueError('COMMITTED_OPERATION_NOT_PROVEN')
                return row
            route=dict(service_date='2026-11-05',origin_stop_id='AOH',destination_stop_id='HGH')
            row=turn('请查询2026-11-05上海虹桥AOH到杭州东HGH的静态车次，返回最早两班。选第一班、二等座，查询3人模拟库存并生成3人报价，为合成甲、合成乙、合成丙生成建单提案，联系人用当前登录手机号。只生成提案，等待我确认，禁止直接建单或支付。',
                ['railway_query_trips','railway_check_inventory','railway_quote_fare','railway_create_order'],dict(railway_query_trips=route,railway_quote_fare=dict(route,passenger_count=3,seat_class='SECOND')))
            trips=next(e['result']['data'] for e in row['executed_tools'] if e['tool']=='railway_query_trips' and e['ok'])
            if len(trips)<2:raise ValueError('TWO_ACTUAL_TRIPS_REQUIRED')
            created=confirm('CREATE_ORDER');oid=created['result']['order_id'];info['order_id']=oid
            order=created['after']['tables']['orders'][0]
            turn(f"为刚创建的模拟订单{oid}生成支付提案，金额{order['total_fen']}分，等待我确认。",['railway_pay_order'],dict(railway_pay_order=dict(order_id=oid,expected_total_fen=order['total_fen'])))
            confirm('PAY')
            person=run.read()['tables']['order_items'][0]
            turn(f"请只为订单{oid}中的合成甲明细{person['item_id']}生成部分退款提案，scope=ITEMS，其他两人保持有效，等我确认。",['railway_refund_order'],dict(railway_refund_order=dict(order_id=oid,scope='ITEMS',item_ids=[person['item_id']])))
            confirm('REFUND')
            target=trips[1]['trip_id']
            turn(f"为订单{oid}剩余两名ACTIVE乘客改签到同日同区间第二班trip_id={target}，二等座。先为2人报价，再生成改签提案，等待我确认，不修改已退款乘客。",['railway_quote_fare','railway_change_order'],dict(railway_quote_fare=dict(route,trip_id=target,passenger_count=2,seat_class='SECOND')))
            confirm('CHANGE')
            turn(f"为订单{oid}全部剩余ACTIVE乘客生成整单退款提案，scope=FULL，等待我确认。",['railway_refund_order'],dict(railway_refund_order=dict(order_id=oid,scope='FULL')))
            final=confirm('REFUND')
            if final['after']['tables']['orders'][0]['order_status']!='CANCELLED':raise ValueError('FINAL_STATE_NOT_CANCELLED')
            info['status']='PASS'
        except Exception as exc:
            info['status']='FAIL';info['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        info['final_state']=[{k:o[k] for k in ('order_id','order_status','paid_total_fen','refunded_total_fen','fee_total_fen','net_paid_fen','active_item_count')} for o in run.read()['tables']['orders']]
        save(run.root/'remaining-outcome.json',info)
    save(root/'remaining-summary.json',dict(results=results,budget=batch.status()))
    print(json.dumps(dict(results=results,budget={k:v for k,v in batch.status().items() if k!='requests'}),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--remaining-live',action='store_true');parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    if not args.remaining_live:parser.error('--remaining-live required')
    execute(args.root.resolve())
