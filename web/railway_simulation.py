"""Opt-in V3.9 workspace. Original four-panel workspace stays independent."""
from dataclasses import replace
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
import html,json,os,uuid,sqlite3
import streamlit as st
import config
from target.v39.context import Context,scope,digest
from target.v39.registry import NAMES,enabled,service_scope,dispatch
from target.v39.service import Service,insert
from target.v39.static import RailwayStatic,VERSION
from target.v39.store import Store
from target.v39.policy import Policy,VERSION as POLICY_VERSION

SEATS={'SECOND':'二等座','FIRST':'一等座','BUSINESS':'商务座'}
STATES={'PENDING_PAYMENT':'待模拟支付','PAID':'模拟支付成功','CHANGED':'已模拟改签','CANCELLED':'已取消','EXPIRED':'锁座已过期','PAYMENT_FAILED':'模拟支付失败'}
ERRORS={'POLICY_PENDING_USER_DECISION':'退款与改签政策尚待批准，当前没有执行交易。','PROPOSAL_CONFIG_STALE':'配置已变化，请重新生成确认卡。','PROPOSAL_ORDER_STALE':'订单已变化，请重新核对并生成确认卡。','INVENTORY_INSUFFICIENT':'模拟余票不足，没有完成锁座。','QUOTE_EXPIRED':'报价已过期，请重新查询价格。','CONFIRMATION_SECRET_LOST':'服务已重启，请取消旧确认卡并重新生成。','PROPOSAL_EXPIRED':'确认卡已过期，请重新生成。'}
ERRORS.update(WRITE_POLICY_DENIED='当前会话没有执行这项操作的权限。请在开发者工作台核对权限，再重新生成确认卡。',DEPARTURE_ALREADY_PASSED='该静态车次已经过了出发时间，请选择其他服务日或车次。',V39_TOOL_NOT_ALLOWED='当前会话未开放这项功能，请检查开发者配置。',PAYMENT_TIMEOUT='模拟支付超时，未记入成功付款，模拟座位已释放。')
ERRORS.update(PROPOSAL_PRICE_STALE='手续费或有效价格已经变化，请撤销旧卡并重新生成，重新核对金额。',REFUND_ALREADY_DONE='该乘客已经退款，本次未再次退款；独立失败尝试已保留。',V391_MIGRATION_REQUIRED='该数据库属于旧版本，请保留原件并使用独立的V3.9.1数据库路径。')

@st.cache_resource(show_spinner=False)
def resource(path):
    service=Service(Store(path),RailwayStatic(),policy=Policy());service.start()
    service.scenario('railway-demo',VERSION)
    return service

def _call(s,ctx,name,args,session=None):
    if session is not None:
        from web.business_actions import invoke
        result=invoke(session,name,args)
        if isinstance(result,dict) and result.get('error'):
            st.error(ERRORS.get(result['error'],'操作未完成：'+result['error']));return None
        return result
    with scope(ctx),service_scope(s):result,ok,elapsed=dispatch(name,args)
    # Page operations are page events, not fabricated Agent runs or model calls.
    s.page_event(ctx,name,args,result,ok,elapsed)
    if not ok:
        st.error(ERRORS.get(result.get('error'), '操作未完成：'+result.get('error','未知错误')))
        return None
    if isinstance(result,dict) and result.get('proposal_id'):st.session_state['v39_pending']=result['proposal_id']
    return result

def _confirm(s,ctx):
    rows=s.pending(ctx)
    if not rows:return
    st.subheader('待确认的模拟操作')
    labels={'CREATE_ORDER':'锁定模拟座位并建单','PAY':'模拟支付','CANCEL':'取消模拟订单','REFUND':'模拟退票','CHANGE':'模拟改签'}
    for row in rows:
        p=dict(row);pid=p['proposal_id'];args=json.loads(p['payload_json'])
        with st.container(border=True):
            st.markdown('**'+labels[p['action']]+'**')
            st.caption('确认卡 '+pid+' · 有效期至 '+p['expires_at'])
            preview=args.get('_refund_preview') or args.get('_display_preview')
            if preview:
                if 'net_fen' in preview:st.info('本次退款票面 ¥'+f"{preview['amount_fen']/100:.2f}"+'；手续费 ¥'+f"{preview['fee_fen']/100:.2f}"+'；净退款 ¥'+f"{preview['net_fen']/100:.2f}"+'。仅本地模拟退款。')
                elif 'difference_fen' in preview:st.info('改签后票面 ¥'+f"{preview['new_face_fen']/100:.2f}"+'；模拟补款/退差（负数）¥'+f"{preview['difference_fen']/100:.2f}")
                else:st.info('模拟订单总价 ¥'+f"{preview['total_fen']/100:.2f}")
            st.json({k:v for k,v in args.items() if not k.startswith('_')},expanded=False)
            approved=st.checkbox('我已核对，确认这次本地模拟操作',key='v39_ack_'+pid)
            left,right=st.columns(2)
            if left.button('确认执行模拟操作',key='v39_confirm_'+pid,disabled=not approved,type='primary'):
                try:
                    result=s.confirm(ctx,pid)
                    st.session_state['v39_notice']=dict(result,_ui_action=p['action'])
                    st.session_state.pop('v39_refund_items',None)
                    st.rerun()
                except ValueError as exc:st.error(ERRORS.get(str(exc),'未完成：'+str(exc)))
            if right.button('撤销确认卡',key='v39_decline_'+pid):
                s.decline(ctx,pid)
                st.rerun()

def _search(s,ctx):
    st.subheader('查找铁路行程')
    a,b=st.columns(2)
    origin=a.text_input('出发站',value='北京南',key='v39_origin_name')
    destination=b.text_input('到达站',value='上海虹桥',key='v39_destination_name')
    # The feed's service day, not today's real-time ticket window.
    service_day=st.date_input('始发服务日',value=date.today()+timedelta(days=1),key='v39_service_day')
    if st.button('查找车站',key='v39_find_stations'):
        st.session_state['v39_station_query']=(origin,destination)
        st.session_state['v39_origins']=_call(s,ctx,'railway_search_stations',dict(name=origin,limit=50))
        st.session_state['v39_destinations']=_call(s,ctx,'railway_search_stations',dict(name=destination,limit=50))
        st.session_state.pop('v39_search_result',None)
    starts=(st.session_state.get('v39_origins') or {}).get('data',[])
    ends=(st.session_state.get('v39_destinations') or {}).get('data',[])
    if not starts or not ends:
        st.info('先查找车站，再明确选择车站编号。同名站不会自动合并。');return
    if st.session_state.get('v39_station_query')!=(origin,destination):
        st.info('站名已变化，请重新查找车站。');return
    fmt=lambda r:r['stop_name']+'（'+r['stop_id']+'）'
    start=st.selectbox('选择出发站',starts,format_func=fmt,key='v39_origin_id')
    end=st.selectbox('选择到达站',ends,format_func=fmt,key='v39_destination_id')
    if st.button('查询静态车次',key='v39_search_trips',type='primary'):
        args=dict(service_date=service_day.isoformat(),origin_stop_id=start['stop_id'],destination_stop_id=end['stop_id'],limit=50)
        st.session_state['v39_search_result']=_call(s,ctx,'railway_query_trips',args)
        st.session_state['v39_search_args']=args
        st.session_state.pop('v39_quote',None)
    result=st.session_state.get('v39_search_result')
    args=st.session_state.get('v39_search_args',{})
    if not result:return
    if any(args.get(k)!=v for k,v in dict(service_date=service_day.isoformat(),origin_stop_id=start['stop_id'],destination_stop_id=end['stop_id']).items()):
        st.info('查询条件已变化，请重新查询车次。');return
    rows=result.get('data',[])
    st.caption('静态数据版本 '+result['dataset_version']+'；查询状态 '+result['status']+'。最多展示 50 班，非实时开行信息。')
    if not rows:st.info('该服务日和区间没有可展示的静态班次，请调整条件。');return
    st.dataframe([dict(车次=r.get('trip_short_name'),车次标识=r['trip_id'],出发=r.get('departure_at'),到达=r.get('arrival_at'),线路形状=r.get('shape_status')) for r in rows],hide_index=True,width='stretch')
    train=st.selectbox('选择车次',rows,format_func=lambda r:str(r.get('trip_short_name') or r['trip_id'])+' / '+r['trip_id'],key='v39_trip')
    if st.button('查看经停与时刻',key='v39_stops_button'):
        st.session_state['v39_stops']=_call(s,ctx,'railway_trip_stops',dict(trip_id=train['trip_id'],service_date=args['service_date']))
    stops=st.session_state.get('v39_stops')
    if stops and stops.get('status')=='FOUND' and stops['data']['trip']['trip_id']==train['trip_id']:
        with st.expander('经停站与跨日时间',expanded=True):
            st.dataframe([dict(站名=r['stop_name'],站序=r['raw_stop_sequence'],到达=r['arrival_at'],出发=r['departure_at']) for r in stops['data']['stops']],hide_index=True,width='stretch')
    seat=st.selectbox('模拟席别',list(SEATS),format_func=SEATS.get,key='v39_seat')
    passengers=st.text_input('模拟乘客姓名（用顿号分隔，最多六人）',value='演示乘客',key='v39_names')
    names=[n.strip() for n in passengers.replace('，','、').replace(',','、').split('、') if n.strip()]
    selection=dict(trip_id=train['trip_id'],service_date=args['service_date'],origin_stop_id=args['origin_stop_id'],destination_stop_id=args['destination_stop_id'],seat_class=seat)
    if st.button('查看模拟余票与报价',key='v39_quote_button'):
        inv=_call(s,ctx,'railway_check_inventory',dict(**selection,quantity=len(names)))
        quote=_call(s,ctx,'railway_quote_fare',dict(**selection,passenger_count=len(names))) if inv else None
        st.session_state['v39_inventory']=inv;st.session_state['v39_quote']=quote;st.session_state['v39_quote_selection']=digest([selection,names])
    q=st.session_state.get('v39_quote')
    if not q or st.session_state.get('v39_quote_selection')!=digest([selection,names]):return
    inv=st.session_state['v39_inventory'];fare=q['quote']
    st.info('模拟余票：'+('未知' if inv['available'] is None else str(inv['available']))+'；模拟总价 ¥'+f"{fare['total_fen']/100:.2f}"+'（'+str(len(names))+' 人）。按区段数、席别倍率及固定费用规则计算，非官方票价。')
    st.caption('报价 '+fare['quote_id']+'；价格规则 '+fare['rule_id']+' v'+str(fare['rule_version'])+'；有效期至 '+fare['expires_at'])
    if st.button('生成建单确认卡',key='v39_create_proposal',disabled=inv['available'] is None or inv['available']<len(names)):
        _call(s,ctx,'railway_create_order',dict(quote_id=fare['quote_id'],passengers=names,contact=ctx.owner_phone));st.rerun()

def _orders(s,ctx,snapshot=None,session=None):
    if session is None:st.subheader('我的铁路模拟订单')
    if 'railway_get_order' not in ctx.tool_whitelist:st.info('当前会话配置未开放订单查询。');return
    rows=snapshot['orders'] if snapshot is not None else s.order(ctx)
    if not rows:st.info('还没有铁路模拟订单。查询行程并确认建单后，订单会出现在这里。');return
    options=[r['order_id'] for r in rows]
    if st.session_state.get('v39_order') not in options:st.session_state['v39_order']=options[0]
    oid=st.selectbox('选择本人订单',options,key='v39_order')
    o=next(r for r in rows if r['order_id']==oid) if snapshot is not None else s.order(ctx,oid)
    marker=(ctx.session_id,oid,o['version'])
    if st.session_state.get('v39_order_items_context')!=marker:
        st.session_state['v39_refund_items']=[]
        st.session_state['v39_order_items_context']=marker
    timetable=s.static.trip(o['trip_id'],o['service_date'])
    detail=timetable['data'] if timetable['status']=='FOUND' else {}
    stops={v['stop_id']:v['stop_name'] for v in detail.get('stops',[])}
    train_no=detail.get('trip',{}).get('trip_short_name') or o['trip_id']
    with st.container(border=True):
        st.markdown('**'+html.escape(train_no)+'　'+html.escape(stops.get(o['origin_stop_id'],o['origin_stop_id']))+' → '+html.escape(stops.get(o['destination_stop_id'],o['destination_stop_id']))+'**')
        st.write(STATES[o['order_status']]+'　'+o['service_date']+'　'+SEATS[o['seat_class']])
        st.write('当前票面 ¥'+f"{o['total_fen']/100:.2f}"+'；累计模拟支付 ¥'+f"{o['paid_total_fen']/100:.2f}"+'；累计模拟退款 ¥'+f"{o['refunded_total_fen']/100:.2f}"+'；手续费 ¥'+f"{o['fee_total_fen']/100:.2f}")
        st.dataframe([dict(模拟乘客=i['passenger_name'],状态={'ACTIVE':'有效','REFUNDED':'已退款','SUPERSEDED':'历史版本'}.get(i['item_status']),票面元=f"{i['fare_fen']/100:.2f}",明细编号=i['item_id']) for i in o['items']],hide_index=True,width='stretch')
        if o['order_status']=='PENDING_PAYMENT':
            st.caption('支付仅改变本地演示状态，不会真实扣款；锁座截止 '+o['expires_at'])
            a,b=st.columns(2)
            expired=bool(o.get('hold_expired_at_read'))
            if expired:st.warning('锁座有效期已过，请重新查询；当前数据库原始状态保留，不能再支付。')
            pay_allowed='railway_pay_order' in ctx.tool_whitelist and not expired
            if not pay_allowed:st.caption('不能支付：'+('锁座已过期' if expired else '当前配置没有支付权限'))
            if a.button('生成模拟支付确认卡',key='v39_pay_proposal',type='primary',disabled=not pay_allowed):_call(s,ctx,'railway_pay_order',dict(order_id=oid,expected_total_fen=o['total_fen']),session);st.rerun()
            if b.button('生成取消确认卡',key='v39_cancel_proposal',disabled='railway_cancel_order' not in ctx.tool_whitelist):_call(s,ctx,'railway_cancel_order',dict(order_id=oid),session);st.rerun()
        if o['order_status'] in ('PAID','CHANGED') and o['active_item_count']:
            st.caption('D9 方案B已批准：改签后可退票，部分退款后可改签剩余乘客或继续退款；每单最多一次成功改签。P01：>48小时5%，24至48小时10%，<24小时20%。')
            active=[i for i in o['items'] if i['item_status']=='ACTIVE']
            by_id={i['item_id']:i for i in active}
            st.session_state['v39_refund_items']=[i for i in st.session_state.get('v39_refund_items',[]) if i in by_id]
            chosen=st.multiselect('选择要退票的模拟乘客',list(by_id),format_func=lambda i:by_id[i]['passenger_name'],key='v39_refund_items',placeholder='选择仍有效的乘客')
            if chosen:
                try:
                    estimate=s.refund_preview(ctx,oid,chosen)
                    st.caption('本次票面 ¥'+f"{estimate['amount_fen']/100:.2f}"+'；手续费 ¥'+f"{estimate['fee_fen']/100:.2f}"+'；净退款 ¥'+f"{estimate['net_fen']/100:.2f}")
                except ValueError as exc:st.warning(ERRORS.get(str(exc),'无法生成退款预览：'+str(exc)))
            refund_allowed=s.policy.approved and bool(chosen) and 'railway_refund_order' in ctx.tool_whitelist
            if not refund_allowed:st.caption('暂不能生成退票卡：'+('请先选择尚未退款的有效乘客' if not chosen else '当前配置未授权退票'))
            if st.button('生成退票确认卡',key='v39_refund_proposal',disabled=not refund_allowed):
                _call(s,ctx,'railway_refund_order',dict(order_id=oid,scope='ITEMS',item_ids=chosen),session);st.rerun()
            q=(st.session_state.get('v39_quote') or {}).get('quote')
            if snapshot is not None:
                valid=[v for v in snapshot['quotes'] if v['status']=='ACTIVE' and v['expires_at']>snapshot['updated_at'] and v['passenger_count']==o['active_item_count']]
                q=valid[0] if valid else None
                if len(valid)>1:q=st.selectbox('选择有效改签报价',valid,format_func=lambda v:v['trip_id']+' / '+SEATS[v['seat_class']]+' / ¥'+f"{v['total_fen']/100:.2f}",key='v39_change_quote')
                if session is not None and o['change_count']<1:
                    with st.expander('准备改签目标报价',expanded=not bool(q)):
                        from web.business_state import current
                        candidate=current(session).get('selected_trip') or o
                        seat=st.selectbox('改签目标席别',list(SEATS),format_func=SEATS.get,key='v39_change_seat')
                        st.caption('按当前选择行程生成 '+str(o['active_item_count'])+' 名有效乘客的报价；已退款乘客不参与。')
                        if st.button('生成改签目标报价',key='v39_change_target_quote'):
                            args={k:candidate.get(k,o[k]) for k in ('trip_id','service_date','origin_stop_id','destination_stop_id')}
                            _call(s,ctx,'railway_quote_fare',dict(args,seat_class=seat,passenger_count=o['active_item_count']),session);st.rerun()
            st.caption('改签目标使用当前查询面板的有效报价；人数须与订单剩余人数一致。')
            change_allowed=s.policy.approved and bool(q) and o['change_count']<1 and q['passenger_count']==o['active_item_count'] and 'railway_change_order' in ctx.tool_whitelist
            if not change_allowed:st.caption('暂不能改签：'+('本订单已成功改签一次' if o['change_count']>=1 else '缺少人数一致、未过期的有效报价' if not q else '当前配置未授权改签'))
            if st.button('生成改签确认卡',key='v39_change_proposal',disabled=not change_allowed):
                _call(s,ctx,'railway_change_order',dict(order_id=oid,target_quote_id=q['quote_id'],**{'target_'+k:q[k] for k in ('trip_id','service_date','origin_stop_id','destination_stop_id','seat_class')}),session);st.rerun()
        with st.expander('模拟交易与退改历史'):
            st.json(dict(transactions=o['transactions'],refunds=o['refunds'],changes=o['changes']),expanded=False)

def _chat(s,ctx,path,effective):
    st.subheader('铁路出行对话')
    engine=effective.engine
    st.caption('当前离线引擎：'+engine+'；可在开发者工作台调整这个铁路会话的 Mock 配置。')
    st.caption('当前为确定性离线演示助手，不会调用真实模型。支持按日期和站名查询，以及本人订单操作提案；交易仍须页面确认。')
    history=st.session_state.setdefault('v39_messages',[])
    for item in history[-20:]:
        with st.chat_message(item['role']):st.write(item['content'])
    message=st.chat_input('例如：查询 2026-11-03 北京南到上海虹桥车次',key='v39_chat')
    if not message:return
    from target.agent import Agent,SYSTEM_PROMPT
    from target.v39.planner import RailwayDemoProvider
    from web.runtime import scoped
    namespace='v39_agent_'+engine+'_'+ctx.config_hash
    trace_root=Path(path).parent/'traces'/ctx.session_id/engine
    values=dict(PROVIDER='mock',ENGINE=engine,LC_TOOLSET='all',DB_PATH=Path(path).parent/'unused-legacy.sqlite',TRACE_DIR=trace_root,MODEL_NAME=effective.model,BASE_DIR=Path(path).parent/'run-metadata')
    with scoped(values),scope(ctx),service_scope(s):
        agent=st.session_state.get(namespace)
        if agent is None:
            # Respect the selected offline engine while preserving the exact
            # session override and the dedicated experimental namespace identity.
            agent=Agent(engine=engine,provider=RailwayDemoProvider(),effective_config=effective)
            st.session_state[namespace]=agent
        try:
            result=agent.chat(ctx.session_id,message)
            reply=result['reply']
        except Exception:reply='本轮未完成，请检查输入日期或稍后重试；没有因此完成交易。'
    history.extend([dict(role='user',content=message),dict(role='assistant',content=reply)])
    st.rerun()

def _current_trip():
    q=(st.session_state.get('v39_quote') or {}).get('quote')
    if q:
        return ('当前报价 '+q['trip_id'],q['service_date'],q['origin_stop_id']+' → '+q['destination_stop_id'],q['total_fen'])
    order=st.session_state.get('v39_order')
    return ('当前订单',str(order or '未选择'),'',None)

def page():
    if not enabled():st.info('铁路出行服务尚未启用。');return
    st.markdown('<div style="height:4.2rem"></div>',unsafe_allow_html=True)
    st.title('Ticket Agent · 铁路出行助手')
    st.caption('一个工作空间：真实静态车站/车次/经停查询，自然语言咨询，以及本地模拟报价、订单、支付、改签和退款。静态时刻不是实时开行，余票、价格和交易均为本地模拟。')
    path=os.getenv('RAILWAY_SIM_DB_PATH',str(config.BASE_DIR/'artifacts/runtime/v392-user'/date.today().isoformat()/'simulation.sqlite'))
    try:s=resource(path)
    except (ValueError,OSError) as exc:st.error('铁路服务不可用：'+str(exc));return
    except sqlite3.Error:
        st.error('铁路数据库未能通过初始化或身份核验。请保留数据库原件，在独立的新路径恢复；当前未执行交易。');return
    sid=st.session_state.setdefault('v39_sid','rail-'+uuid.uuid4().hex)
    scenarios=st.session_state.setdefault('v39_scenarios',{'railway-demo':'共享演示场景'})
    sessions=st.session_state.setdefault('v39_sessions',{sid:'当前铁路会话'})
    sessions.setdefault(sid,'当前铁路会话')
    with st.expander('演示场景与会话（与旧演示订单隔离）',expanded=False):
        queued=st.session_state.pop('v39_select_scenario_next',None)
        if queued in scenarios:st.session_state['v39_scenario']=queued
        selected=st.selectbox('当前铁路场景',list(scenarios),format_func=scenarios.get,key='v39_scenario')
        scenario_name=st.selectbox('新场景库存设置',['default','tight','sufficient','sold_out','payment_fail'],key='v39_new_scenario_type')
        st.caption('新建场景使用同一版本的模拟规则和初始库存，不删除或重置既有订单、交易和审计。')
        if st.button('新建独立演示场景',key='v39_fork_scenario'):
            new_id=sid+'-'+uuid.uuid4().hex[:8]
            s.scenario(new_id,VERSION,name=scenario_name)
            scenarios[new_id]=scenario_name+' / '+new_id[-8:]
            st.session_state.pop('v39_quote',None)
            st.session_state['v39_select_scenario_next']=new_id
            st.rerun()
        history_choice=st.selectbox('历史铁路会话',list(sessions),format_func=sessions.get,key='v39_session_choice')
        if history_choice!=sid:
            st.session_state.setdefault('v39_message_store',{})[sid]=st.session_state.get('v39_messages',[])
            st.session_state['v39_sid']=history_choice
            st.session_state['v39_messages']=st.session_state['v39_message_store'].get(history_choice,[])
            for key in ('v39_quote','v39_inventory','v39_search_result','v39_pending','v39_config_session'):
                st.session_state.pop(key,None)
            st.rerun()
        a,b=st.columns(2)
        if a.button('新铁路会话',key='v39_new_chat_session'):
            st.session_state.setdefault('v39_message_store',{})[sid]=st.session_state.get('v39_messages',[])
            new_sid='rail-'+uuid.uuid4().hex
            sessions[new_sid]='会话 '+new_sid[-8:]
            st.session_state['v39_sid']=new_sid
            st.session_state['v39_messages']=[]
            for key in ('v39_quote','v39_inventory','v39_search_result','v39_pending','v39_config_session'):
                st.session_state.pop(key,None)
            st.rerun()
        if b.button('清空当前会话消息',key='v39_clear_chat'):
            st.session_state['v39_messages']=[]
            st.rerun()
        b.caption('当前会话 '+sid[-8:]+'；历史会话仅保存在本次浏览器会话。')
    from web.runtime import Conversation
    session=st.session_state.get('v39_config_session')
    if session is None:
        session=Conversation('user',sid=sid,engine='legacy',live=False,full_tools=True,execution_mode='developer_custom',root=config.BASE_DIR/'artifacts/runtime/v39-user-context'/sid)
        st.session_state['v39_config_session']=session
    effective=session.resolve_config()
    if effective.execution_mode=='baseline':st.info('正式 Baseline 不提供 V3.9 工具。请在开发者工作台切回会话实验模式。');return
    if effective.provider!='mock':
        st.info('当前为在线模式，但 V3.9.1 铁路交易只使用本地确定性模拟与只读静态数据；本轮不把在线模型或真实铁路/支付作为已验收能力。')
        effective=replace(effective,provider='mock')
    required={n:('query_tickets',) for n in NAMES[:5]}
    required.update(dict(railway_create_order=('lock_seat','create_order'),railway_get_order=('query_order',),railway_pay_order=('pay_order',),railway_cancel_order=('cancel_order',),railway_refund_order=('cancel_order',),railway_change_order=('lock_seat','create_order','cancel_order')))
    names=tuple(n for n in NAMES if all(v in effective.tool_whitelist for v in required[n]))
    suffix='\n当前为独立 railway_ 模拟命名空间。车次来自只读静态时刻表，余票和价格为本地模拟。写工具仅创建提案；只能由用户在界面确认，不得声称已经真实出票、扣款、退款。'
    prompt=effective.prompt+suffix
    import hashlib
    effective=replace(effective,prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),config_source='railway_simulation/'+effective.config_source,tool_whitelist=tuple((*effective.tool_whitelist,*names)),config_hash=digest([effective.config_hash,names,prompt,selected,s.policy.version,'railway_simulation_v391']))
    ctx=Context(sid,config.CURRENT_USER_PHONE,selected,enabled=enabled(),config_hash=effective.config_hash,config_revision=effective.override_revision,tool_whitelist=names)
    notice=st.session_state.pop('v39_notice',None)
    with st.container(key='v39_receipt'):
        if notice:
            if notice.get('error') or notice['status'] not in STATES:st.warning(ERRORS.get(notice.get('error') or notice['status'],str(notice['status'])))
            elif notice.get('_ui_action') in ('REFUND','CANCEL') and 'refund_fen' in notice:
                st.success('本次模拟退款成功：净退款 ¥'+f"{notice['refund_fen']/100:.2f}"+'；手续费 ¥'+f"{notice['fee_fen']/100:.2f}"+'；剩余乘客 '+str(notice['remaining_passengers'])+' 人。')
            else:st.success(STATES[notice['status']]+'；仅影响本地模拟数据。')
    st.caption('静态数据版本 '+VERSION+'；187 个异常班次整班隔离。缺失线路形状不推测；同名车站需明确选择。仅用于本地学习演示，不代表官方票价、实时余票或真实出票。')
    from target.execution_config import scope as effective_scope
    with effective_scope(effective):
        main,aside=st.columns([2.35,1],gap='large')
        # Render the search/chat column first so the side order panel sees any
        # quote or proposal created by the current interaction in the same run.
        with main:
            with st.container(key='v39_search_area'):
                _search(s,ctx)
            st.divider()
            with st.container(key='v39_chat_area'):
                _chat(s,ctx,path,effective)
        with aside:
            st.subheader('订单与操作')
            with st.container(key='v39_confirmation_area'):_confirm(s,ctx)
            with st.container(key='v39_orders_area'):_orders(s,ctx)
            with st.container(border=True):
                st.markdown('**当前行程**')
                title,day,route,total=_current_trip()
                st.caption(title);st.write(day);st.write(route or '尚未选择')
                if total is not None:st.caption('模拟票面 ¥'+f"{total/100:.2f}")
                st.markdown('**政策与费用**')
                st.caption('D9 方案B：改签后可退；部分退款后可改签剩余 ACTIVE 乘客并继续退款；每乘客最多一次成功退款，每订单最多一次成功改签。')
                st.caption('P01：>48h 5%；24–48h 10%；<24h 20%；整数分 half-up，基数为当前有效乘客价格快照。')
                st.caption('所有价格、库存、支付、退款均为本地模拟，不连接真实铁路或支付。')

