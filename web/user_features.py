"""Session-scoped independent user panels; queries preserve the Agent chain."""
import json
import uuid
from datetime import timedelta,datetime,time as clock_time
import streamlit as st
import config
from web.presentation import ticket_cards,order_card
from web.result_rows import iter_rows
from web.runtime import CALL_LOCK
from target import order_read_model

NAMES=('查余票','问政策','看订单','退票费率','行李费用','改签')

def state(session):
    s=st.session_state.setdefault('features_'+session.sid,{})
    source_hash=session.train_source_hash() if hasattr(session,'train_source_hash') else None
    if s.get('data_source_hash')!=source_hash and not session.read_only:
        s.pop('tickets',None);s.pop('selected_train',None);s['data_source_hash']=source_hash
    if session.read_only and hasattr(session,'results'):
        for row in iter_rows(session.results):
            if row.get('ok') and row.get('tool')=='query_order':s['order_result']=row['result']
            if row.get('ok') and row.get('tool')=='query_tickets':s['tickets']=row['result']
    return s

def open_panel(sid,name):
    st.session_state['feature_panel_'+sid]=name
    st.session_state.pop('p3_reschedule',None)

def shortcuts(sid):
    from web.interaction import launch
    with st.container(key='user_shortcuts'):
        for col,name in zip(st.columns(4),NAMES[:4]):col.button(name,key='feature_quick_'+name,on_click=launch,args=(sid,name))

def query(session,message,tool):
    if session.read_only:raise ValueError('历史会话只读，请新建会话执行查询')
    if session.live:
        from web.conversation import _live_request_allowed
        from web.runtime import live_ready
        if not _live_request_allowed(session) or not live_ready(session.live_provider):raise ValueError('当前会话或在线服务未就绪，未发送请求')
        candidate=session.resolve_config()
        if candidate and candidate.provider==session.live_provider:
            session.config_cost_consent=(session.sid,candidate.provider,candidate.override_revision)
    try:
        result=session.send(message,uuid.uuid4().hex)
        events=[r for r in iter_rows(session.results[-1]) if r.get('tool')==tool and (r.get('ok') or tool=='query_tickets' and r.get('result',{}).get('data_source'))]
        if not events:raise ValueError('本轮未取得所需工具的成功结果，请查看运行记录')
        return events[-1]['result']
    except Exception as exc:
        # A side-panel query is a separate operation.  Preserve a diagnostic
        # for the developer workspace, but do not let it become the chat
        # workspace's request-level error banner.
        session.panel_error={'source':'user_feature','tool':tool,'type':type(exc).__name__,
                             'category':(session.error or {}).get('category')}
        session.error=None
        raise

def ticket_search_panel(session):
    from datetime import date
    from web import railway_defaults as defaults
    s=state(session)
    default_day=date.fromisoformat(defaults.DEMO_SERVICE_DATE)
    if default_day<config.today():default_day=config.today()
    with st.form('feature_tickets_'+session.sid):
        cities=['上海','杭州','北京','广州','南京','成都','武汉','长沙']
        origin=st.selectbox('出发地',cities,key='ft_from');dest=st.selectbox('到达地',cities,index=1,key='ft_to')
        day=st.date_input('出行日期',value=default_day,min_value=config.today(),key='ft_date')
        kind=st.selectbox('交通方式',['高铁','机票'],key='ft_kind')
        seat=st.selectbox('席别',['二等座','一等座','商务座','经济舱','公务舱'],key='ft_seat')
        submit=st.form_submit_button('查询车票')
    if submit:
        if origin==dest:st.warning('出发地和到达地不能相同')
        elif day<config.today():st.warning('请选择今天或以后的日期')
        elif seat not in ({'高铁':['二等座','一等座','商务座'],'机票':['经济舱','公务舱']}[kind]):st.warning('席别与交通方式不兼容，请重新选择')
        else:
            if getattr(session,'_unified_interaction',False):
                from web.interaction import enqueue
                enqueue(session.sid,f'查询{day.isoformat()} {origin}到{dest}的{kind}{seat}车次和模拟余票。','form:查余票','查询车票')
                st.rerun()
            else:
                try:s['tickets']=query(session,f'查{day.isoformat()}{origin}到{dest}的{kind}{seat}','query_tickets')
                except ValueError as exc:st.warning(str(exc))
    if s.get('railway_default_error'):
        e=s.pop('railway_default_error');st.warning(e['message']);st.caption('状态：'+e['status']+' · 未自动重试，未切换数据源。')
    if 'railway_default' in s:
        r=s['railway_default']; rows=r.get('rows',[]); result=r.get('trips',{})
        st.caption(r['origin']['stop_name']+' → '+r['destination']['stop_name'])
        st.caption('共 '+str(result.get('total_count',len(rows)))+' 班，完整车次卡片见左侧聊天区。')
    if 'tickets' in s:
        from web.train_data import source_status
        source_status(s['tickets'])
        trains=s['tickets'].get('trains',[])
        if not trains and not s['tickets'].get('data_source'):st.info('没有符合条件的演示车次。')
        for i,t in enumerate(trains):
            st.markdown(ticket_cards({'trains':[t],'data_source':s['tickets'].get('data_source')}),unsafe_allow_html=True)
            if st.button('选择这个车次',key='ft_pick_'+session.sid+'_'+str(i)):
                s['selected_train']=t
        if s.get('selected_train'):
            st.write('已选择：',s['selected_train']['train_no'])
            st.caption('选择不会下单或扣库存；后续订票仍需在聊天中确认。')
            if st.button('取消选择',key='ft_clear'):s.pop('selected_train',None);st.rerun()

def policy_browser_panel(session):
    from target.rag_store import documents,keyword
    docs=documents(config.POLICY_PATH)
    groups={'全部':None,'退票费率':['P01','P12'],'改签规则':['P02','P03'],'行李限额':['P06'],'支付时限':['P11'],'候补规则':['P08']}
    category=st.selectbox('政策分类',list(groups),key='fp_category')
    search=st.text_input('政策关键词',key='fp_search')
    if st.button('清空筛选',key='fp_clear',on_click=lambda:(st.session_state.update(fp_search='',fp_category='全部'))):pass
    related=state(session).get('related_policy_ids')
    if related:st.caption('当前订单关联政策：'+', '.join(related))
    if related and st.button('查看全部政策',key='fp_all'):state(session).pop('related_policy_ids',None);st.rerun()
    filtered=docs if groups[category] is None else [d for d in docs if d['doc_id'] in groups[category]]
    if related:filtered=[d for d in filtered if d['doc_id'] in related]
    if search:filtered=keyword(filtered,search,k=len(filtered) or 1)
    if not filtered:st.info('没有匹配政策。')
    for d in filtered:
        with st.expander(d['doc_id']+' · '+d['title']):
            st.write(d['content']);st.caption('来源：'+d['source']+' · 范围：项目内示例政策，不代表现实规定')
            if st.button('就这条提问',key='fp_'+session.sid+'_'+d['chunk_id']):
                state(session)['policy_context']=d
                from web.interaction import enqueue
                enqueue(session.sid,'查询项目示例政策'+d['doc_id']+'《'+d['title']+'》的适用条件和例外。','policy:document')
                st.rerun()
    if state(session).get('policy_context'):
        st.info('已选政策：'+state(session)['policy_context']['doc_id']+'；请回到聊天继续提问。')
        if st.button('取消政策上下文',key='fp_context_clear'):state(session).pop('policy_context',None)

def my_orders_panel(session):
    from web.payment import controls
    from web.order_actions import card_actions,execute,allowed
    s=state(session)
    if st.button('查询我的订单',key='fo_query_'+session.sid):
        from web.interaction import enqueue
        enqueue(session.sid,'查询我的订单，仅查看本人订单。','form:看订单')
        st.rerun()
    for row in reversed(list(iter_rows(getattr(session,'results',[])))):
        found=row['result'] if row.get('ok') and row.get('tool')=='query_order' else None
        if found is not None:s['order_result']=found;break
    if 'order_result' not in s:st.caption('点击查询，通过Agent取得本人的订单记录。');return
    current=order_read_model.orders(session.root/'tickets.db')
    by_id={o['order_id']:o for o in current}
    recorded=s['order_result'].get('orders',[])
    list_mismatch={o['order_id'] for o in recorded}!=set(by_id)
    if list_mismatch:
        st.warning('订单列表与上次Agent查询不一致，已禁用操作；请重新查询。')
        for o in current:
            if o['order_id'] not in {r['order_id'] for r in recorded}:st.markdown(order_card(o),unsafe_allow_html=True)
    for old in recorded:
        o=by_id.get(old['order_id']);same=not list_mismatch and o is not None and order_read_model.consistent(old,o)
        if not same:
            st.warning('订单数据不一致或当前状态不可核验，已禁用操作。请重新查询；历史工具结果保留。')
            if not session.read_only:
                import hashlib
                record={'source':'read_model_diagnostic','session_id':session.sid,'order_id':old['order_id'],
                        'tool':{k:old.get(k) for k in ('train_no','date','seat_type','amount','status')},
                        'database':{k:o.get(k) for k in ('train_no','date','seat_type','amount','status')} if o else None}
                raw=json.dumps(record,ensure_ascii=False,sort_keys=True)
                digest=hashlib.sha256(raw.encode()).hexdigest()
                if digest not in s.setdefault('diagnosed',[]):
                    with (session.root/'order-consistency.jsonl').open('a',encoding='utf-8') as f:f.write(raw+'\n')
                    s['diagnosed'].append(digest)
            st.markdown(order_card(o or old),unsafe_allow_html=True)
            with st.expander('上次Agent订单结果'):st.write({k:old.get(k) for k in ('order_id','train_no','date','seat_type','amount','status')})
            continue
        st.markdown(order_card(o),unsafe_allow_html=True)
        st.write('当前状态：'+o['display_status']+' · '+o['from_city']+' → '+o['to_city'])
        st.caption('支付：'+o['payment_status']+' · 退款：'+o['refund_status']+' · 改签：'+o['reschedule_status'])
        st.write('乘客：'+','.join(o['passengers_display'])+' · 创建时间：'+o['created_at'])
        with st.expander('订单详情 · '+o['order_id']):
            st.write('原支付金额：',o['original_payment_amount']);st.write('新票面金额：',o['new_ticket_amount']);st.write('差价仅记录：',o['difference'])
            for name in ('payment_record','refund_record','reschedule'):
                row=o.get(name)
                if row:st.write(name,{k:v for k,v in row.items() if k not in ('order_snapshot','target_snapshot','passengers')})
        if o['actions']['pay']['allowed']:
            if st.button('去支付',key='fo_pay_'+o['order_id']):s['pay_order']=o['order_id']
            if s.get('pay_order')==o['order_id']:controls(session,o,verified=not session.read_only,namespace="_center")
        card_actions(session,o,not session.read_only,namespace="_center")
        if o['actions']['refund']['allowed'] and allowed(session):
            if st.button('预览退票',key='fo_refund_'+o['order_id']):
                s['refund_quote']=o['refund_quote'];session.bind_page_proposal(o['refund_quote'])
            q=s.get('refund_quote')
            if q and q['order_id']==o['order_id']:
                st.write('手续费：',q['fee'],'退款：',q['refund'])
                if st.button('确认此订单退票',key='fo_confirm_'+o['order_id']):
                    try:
                        execute(session,'refund',q,confirmed=True);s.pop('order_result',None);st.success('演示退票完成，请重新查询订单。')
                    except ValueError as e:st.warning(str(e))
        if st.button('查看政策',key='fo_policy_'+o['order_id']):
            s['related_policy_ids']=['P01','P02','P03','P07','P12'] if o['has_reschedules'] else ['P01','P07','P11','P12']
            open_panel(session.sid,'问政策');st.rerun()

def refund_calculator_panel(session):
    from target.order_refund import calculate
    with st.form('feature_refund_calc'):
        st.text_input('出发地（计算说明）',value='上海虹桥',key='fr_from');st.text_input('到达地或里程（不用于估价）',value='杭州东',key='fr_to')
        day=st.date_input('出发日期',value=config.today()+timedelta(days=3),key='fr_date');time=st.time_input('出发时间',value=clock_time(12,0),key='fr_time')
        amount=st.text_input('票价金额（元，必填）',value='500',key='fr_amount')
        kind=st.selectbox('票种',['高铁','机票'],key='fr_kind');status=st.selectbox('支付情况',['paid','pending'],format_func=lambda v:{'paid':'已支付','pending':'待支付'}[v],key='fr_status')
        changed=st.checkbox('此订单已经改签',key='fr_changed')
        submit=st.form_submit_button('计算退票费用')
    if submit:
        try:
            r=calculate(amount,datetime.combine(day,time),status=status,kind=kind,changed=changed)
            if r.get('error'):st.warning(r['error'])
            else:
                st.write('适用示例政策：'+r['policy_ref'])
                st.write(f"距发车：{r['seconds_before_departure']/3600:.2f}小时；费率：{r['fee_rate']:.0%}")
                st.write(f"计算基数：¥{r['amount']:.2f}；手续费：¥{r['fee']:.2f}；退款金额：¥{r['refund']:.2f}")
                st.write('计算基数×费率=手续费；退款=基数−手续费（待支付订单退款为0）')
                from web.interaction import enqueue
                enqueue(session.sid,f'查询项目示例退票政策并核对本地计算器结果。票种{kind}，票面{amount}元，发车{datetime.combine(day,time).isoformat()}，支付状态{status}，已经改签{changed}；计算器手续费{r["fee"]}元、退款{r["refund"]}元。仅解释，不执行退票。','form:退票费率')
        except ValueError as e:st.warning(str(e))
    st.caption('最终能否退票，以订单状态和适用政策校验为准。计算器不会修改订单或产生退款。')

def baggage_panel(session):
    with st.form('baggage_calculator'):
        person=st.selectbox('旅客类型',['成人','儿童'],key='baggage_person')
        weight=st.text_input('携带品总重量（千克）',value='25',key='baggage_weight')
        cols=st.columns(3)
        length=cols[0].text_input('长（厘米）',value='50',key='baggage_length')
        width=cols[1].text_input('宽（厘米）',value='40',key='baggage_width')
        height=cols[2].text_input('高（厘米）',value='30',key='baggage_height')
        calculate=st.form_submit_button('计算模拟行李费用')
    if calculate:
        try:
            from target.baggage import calculate_baggage
            result=calculate_baggage(person,weight,length,width,height)
            state(session)['baggage_result']=result
            st.write('免费额度：'+result['free_kg']+' 千克；超重：'+result['excess_kg']+' 千克。')
            st.write('模拟超重费用：¥'+result['weight_fee_yuan']+'（来源：P06）')
            st.write('该物品尺寸总和：'+result['item_sum_cm']+' 厘米；'+result['size_status'])
            st.caption(result['note'])
            from web.interaction import enqueue
            enqueue(session.sid,f'查询P06项目示例行李政策并核对本地计算器结果：{person}，总重{weight}千克，单件长宽高{length}/{width}/{height}厘米，模拟超重费用{result["weight_fee_yuan"]}元。仅解释，不办理交易。','form:行李费用')
        except ValueError as exc:
            st.warning(str(exc))
    if not calculate and state(session).get('baggage_result'):
        result=state(session)['baggage_result']
        st.write('免费额度：'+result['free_kg']+' 千克；超重：'+result['excess_kg']+' 千克。')
        st.write('模拟超重费用：¥'+result['weight_fee_yuan']+'（来源：P06）')
        st.write('该物品尺寸总和：'+result['item_sum_cm']+' 厘米；'+result['size_status'])
        st.caption(result['note'])

def change_panel(session):
    from web.order_actions import change_panel as existing
    rows=order_read_model.orders(session.root/'tickets.db') if not session.read_only else []
    eligible={o['order_id']:o for o in rows if o['actions']['reschedule']['allowed']}
    if not eligible:st.info('没有可改签的本人已支付高铁订单。');return
    oid=st.selectbox('选择改签订单',list(eligible),key='fc_order');existing(session,eligible[oid])

def render(session):
    saved=state(session).setdefault('forms',{})
    for k in list(st.session_state):
        if k in ('ft_from','ft_to','ft_date','ft_kind','ft_seat','fp_category','fp_search','fc_order','fr_from','fr_to','fr_date','fr_time','fr_amount','fr_kind','fr_status','fr_changed','baggage_weight','baggage_length','baggage_width','baggage_height','baggage_person'):saved[k]=st.session_state[k]
    for k,v in saved.items():
        if k not in st.session_state:st.session_state[k]=v
    if session.live:st.caption('查询与发送消息一样可能产生当前Provider的模型费用；不会自动重试。')
    st.markdown('**常用功能**')
    from web.interaction import launch,busy
    for name in NAMES:st.button(name,key='feature_nav_'+session.sid+'_'+name,on_click=launch,args=(session.sid,name),width='stretch',disabled=session.read_only or busy(session) or bool(session.pending_action()))
    name=st.session_state.get('feature_panel_'+session.sid)
    with st.expander('行李费用（P06）',expanded=name=='行李费用'):
        baggage_panel(session)
    if name:
        st.markdown('### '+name)
        if st.button('关闭面板',key='feature_close_'+session.sid):st.session_state.pop('feature_panel_'+session.sid,None);st.rerun()
        if name=='行李费用':return
        dict(zip(NAMES,(ticket_search_panel,policy_browser_panel,my_orders_panel,refund_calculator_panel,baggage_panel,change_panel)))[name](session)
