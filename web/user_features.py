"""Session-scoped independent user panels; queries preserve the Agent chain."""
import json
import uuid
from datetime import date,timedelta,datetime,time as clock_time
import streamlit as st
import config
from web.presentation import ticket_cards,order_card
from web.result_rows import iter_rows
from web.runtime import CALL_LOCK
from target import order_read_model

NAMES=('查余票','问政策','看订单','退票费率','行李费用','改签')
# 演示默认路线：广州 → 深圳，与对话里的主要车站示例（广州南 → 深圳北）一致。
DEFAULT_ORIGIN='广州'
DEFAULT_DESTINATION='深圳'
STARTER_TASKS=(('查余票','选择站点和出行日期'),('退票费率','核算手续费与退款金额'),
               ('看订单','核对订单与支付状态'),('改签','查找可改签的车次'))
FORM_KEYS=('ft_from','ft_to','ft_date','ft_kind','ft_seat','ft_from_name','ft_to_name',
           'ft_origin_stop','ft_destination_stop','fp_category','fp_search','fc_order',
           'fr_from','fr_to','fr_date','fr_time','fr_amount','fr_kind','fr_status','fr_changed',
           'baggage_weight','baggage_length','baggage_width','baggage_height','baggage_person')


def _status(text):
    """面板内结果状态：只描述已经发生/已经呈现的事，不把提议说成已执行。"""
    st.caption('状态：'+text)


def _guide(text):
    """面板内下一步引导：客户可继续用文字或面板推进同一业务。"""
    st.caption('下一步：'+text)


def _trade_notice():
    """保留调用点兼容性；确认动作只在主对话确认卡发生，不再逐面板重复说明。"""
    return


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
    st.session_state['user_info_open']=True
    st.session_state.pop('p3_reschedule',None)

def shortcuts(sid):
    from web.interaction import launch
    with st.container(key='user_shortcuts'):
        for col,name in zip(st.columns(4),NAMES[:4]):
            col.button(name,key='feature_quick_'+name,width='stretch',on_click=launch,args=(sid,name))


def starter_tasks(sid):
    from web.interaction import launch
    with st.container(key='starter_tasks'):
        st.markdown('**从常见任务开始**')
        with st.container(key='starter_grid'):
            for name,description in STARTER_TASKS:
                st.button(description,key='starter_'+name,on_click=launch,args=(sid,name),width='stretch')

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
    """上一版风格：一组出发 / 到达下拉，不再做「城市名 → 候选站」两步输入。

    站点明确选择交给对话链路处理，右栏只保留一处目的地输入，避免同一个
    页面出现两组出发/到达控件，也避免候选站列表把右栏撑满。
    """
    from web import railway_defaults as defaults
    s=state(session)
    cities=['广州','深圳','上海','杭州','北京','南京','成都','武汉','长沙','西安','厦门','天津','重庆']
    earliest=config.today()
    simulation=(getattr(session,'business_view',None) or {}).get('simulation_clock')
    if simulation:
        earliest=date.fromisoformat(simulation['now'][:10])
    default_day=max(earliest,defaults.default_service_date())
    if (st.session_state.get('ft_date') or default_day)<earliest:
        st.session_state['ft_date']=earliest
    with st.form('feature_tickets_'+session.sid):
        pair=st.columns(2,gap='small')
        origin=pair[0].selectbox('出发地',cities,index=cities.index(DEFAULT_ORIGIN),key='ft_from')
        dest=pair[1].selectbox('到达地',cities,index=cities.index(DEFAULT_DESTINATION),key='ft_to')
        day=st.date_input('出行日期',value=default_day,min_value=earliest,key='ft_date')
        settings=st.columns(2,gap='small')
        kinds=['高铁','机票']
        seats=['二等座','一等座','商务座','经济舱','公务舱']
        kind=settings[0].selectbox('交通方式',kinds,key='ft_kind')
        seat=settings[1].selectbox('席别',seats,key='ft_seat')
        submit=st.form_submit_button('查询车票',type='primary',width='stretch')
    if submit:
        compatible={'高铁':['二等座','一等座','商务座'],'机票':['经济舱','公务舱']}
        if origin==dest:
            st.warning('出发地和到达地不能相同')
        elif not day or day<earliest:
            st.warning('请选择当前业务日期或之后的日期')
        elif seat not in compatible[kind]:
            st.warning('席别与交通方式不兼容，请重新选择')
        else:
            from web.interaction import enqueue
            text=f'查询{day.isoformat()} {origin}到{dest}的{kind}{seat}车次和余票。'
            if enqueue(session.sid,text,'form:查余票','查询车票'):
                st.rerun()
            else:
                st.warning(st.session_state.pop('feature_notice_'+session.sid,'请求未发送，请稍后重试。'))
    if s.get('railway_default_error'):
        e=s.pop('railway_default_error');st.warning(e['message']);st.caption('状态：'+e['status']+' · 未自动重试，未切换数据源。')
        _guide('核对日期与站点后重新提交；也可以直接用文字说明出发地、到达地和日期。')
    if 'railway_default' in s:
        r=s['railway_default']; rows=r.get('rows',[]); result=r.get('trips',{})
        st.caption(r['origin']['stop_name']+' → '+r['destination']['stop_name'])
        st.caption('共 '+str(result.get('total_count',len(rows)))+' 班，完整车次卡片见左侧聊天区。')
        if not rows:
            st.info('没有匹配车次，可调整出发地、到达地或出行日期后重试。')
            _guide('改选别的日期或城市后重新查询；也可用文字说明需求。')
        else:
            _status('已列出本次查询结果，共 '+str(result.get('total_count',len(rows)))+' 班。')
            _guide('选定车次后在对话里继续询价或下单。')
    if 'tickets' in s:
        from web.train_data import source_status
        source_status(s['tickets'])
        trains=s['tickets'].get('trains',[])
        if not trains and not s['tickets'].get('data_source'):
            st.info('没有匹配车次，可调整日期，或先明确出发 / 到达站。')
            _guide('改选别的日期或具体车站后重新查询；也可以直接在对话框用文字说明「从哪里到哪里、哪一天」。')
        elif trains:
            _status('已呈现 '+str(len(trains))+' 个车次。')
        for i,t in enumerate(trains):
            st.markdown(ticket_cards({'trains':[t],'data_source':s['tickets'].get('data_source')}),unsafe_allow_html=True)
            if st.button('选择这个车次',key='ft_pick_'+session.sid+'_'+str(i)):
                s['selected_train']=t
        _guide('选定车次后在对话里继续询价或下单；也可用文字调整日期、站点重新查询。')
        if s.get('selected_train'):
            st.write('已选择：',s['selected_train']['train_no'])
            if st.button('取消选择',key='ft_clear'):s.pop('selected_train',None);st.rerun()
    if 'railway_default' not in s and 'tickets' not in s:
        st.info('选择出发地、到达地、出行日期与席别后点「查询车票」。')
        _guide('也可以直接在左侧对话框用文字说明「从哪里到哪里、哪一天」，两种方式结果一致。')
    _trade_notice()

def policy_browser_panel(session):
    from target.rag_store import documents,keyword
    docs=documents(config.POLICY_PATH)
    st.info('按分类浏览或输入关键词定位条款，点「就这条提问」继续追问。')
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
    if not filtered:
        st.info('没有匹配政策。可清空筛选、更换分类或关键词后重试。')
        _guide('也可以点「就这条提问」，或回到对话框用文字直接问政策。')
    for d in filtered:
        with st.expander(d['doc_id']+' · '+d['title']):
            st.write(d['content']);st.caption('来源：'+d['source'])
            if st.button('就这条提问',key='fp_'+session.sid+'_'+d['chunk_id']):
                state(session)['policy_context']=d
                from web.interaction import enqueue
                if enqueue(session.sid,'查询政策条款 '+d['doc_id']+'《'+d['title']+'》的适用条件和例外。','policy:document'):
                    st.rerun()
                else:st.warning(st.session_state.pop('feature_notice_'+session.sid,'请求未发送，请稍后重试。'))
    if state(session).get('policy_context'):
        st.info('已选政策：'+state(session)['policy_context']['doc_id']+'；请回到聊天继续提问。')
        _status('已把该条款带入对话，等待当前 Agent 按条款回答。')
        _guide('回到左侧对话继续追问适用条件与例外；或点「取消政策上下文」后重新选择。')
        if st.button('取消政策上下文',key='fp_context_clear'):state(session).pop('policy_context',None)
    else:
        _guide('选定条款后点「就这条提问」，或直接在对话框提问。')

def my_orders_panel(session):
    from web.payment import controls
    from web.order_actions import card_actions,execute,allowed
    s=state(session)
    _trade_notice()
    if st.button('查询我的订单',key='fo_query_'+session.sid):
        from web.interaction import enqueue
        if enqueue(session.sid,'查询我的订单，仅查看本人订单。','form:看订单'):
            st.rerun()
        else:st.warning(st.session_state.pop('feature_notice_'+session.sid,'请求未发送，请稍后重试。'))
    # The V3.9 page-operation orders live in the committed railway read model,
    # not in the legacy tickets.db used by this panel.  Showing only the legacy
    # source made a just-created order look like 「没有订单」 on the same screen
    # as its 建单成功 receipt.
    try:
        from web.business_state import current as business_view
        committed=[o for o in ((business_view(session).get('railway') or {}).get('orders') or [])
                   if isinstance(o,dict) and o.get('order_id')]
    except Exception:
        committed=[]
    if committed:
        st.markdown('**当前会话的铁路订单**')
        for o in committed[:3]:
            label={'PENDING_PAYMENT':'待支付','PAID':'已支付','CANCELLED':'已取消',
                   'CHANGED':'已改签','REFUNDED':'已退款'}.get(o.get('order_status'),o.get('order_status') or '')
            st.write(str(o['order_id'])+' · '+str(label)+' · ¥'+f"{(o.get('total_fen') or 0)/100:.2f}")
        if any(o.get('order_status')=='PENDING_PAYMENT' for o in committed):
            _guide('回到对话底部点「继续完成支付」。')
            return
        from web.railway_queries import paid_orders,change_candidates,journey,refund_terms
        eligible=paid_orders(session)
        if eligible and not session.read_only:
            order=eligible[0]
            leg=journey(session,order)
            st.markdown('**订单后续办理**')
            st.write(str(leg.get('train'))+' · '+str(leg.get('origin'))+' → '+str(leg.get('destination')))
            facts=[str(leg.get('date_label') or '')]
            if leg.get('depart'):facts.append(str(leg['depart'])+' 开')
            if leg.get('arrive'):facts.append(str(leg['arrive'])+' 到')
            st.caption(' · '.join(p for p in facts if p))
            terms=refund_terms(session,order,leg)
            candidates,args=change_candidates(session,order)
            facts=[]
            if terms is not None:
                facts.append('现在退票手续费 ¥'+f"{terms['fee_fen']/100:.2f}"+'，可退 ¥'+f"{terms['net_fen']/100:.2f}")
            facts.append('可改签 '+str(len(candidates))+' 班')
            st.caption(' · '.join(facts))
            # The ticket card in the conversation owns refund/change so one
            # screen holds one set of actions; this rail only summarises.
            _guide('点对话里的「查看订单」即可办理退票或改签，提交后在同一处确认。')
        return
    for row in reversed(list(iter_rows(getattr(session,'results',[])))):
        found=row['result'] if row.get('ok') and row.get('tool')=='query_order' else None
        if found is not None:s['order_result']=found;break
    if 'order_result' not in s:
        st.info('点「查询我的订单」查看本会话订单。')
        return
    current=order_read_model.orders(session.root/'tickets.db')
    by_id={o['order_id']:o for o in current}
    recorded=s['order_result'].get('orders',[])
    list_mismatch={o['order_id'] for o in recorded}!=set(by_id)
    _status('已取得本人订单结果，状态见下方订单卡片。')
    _guide('可在面板内办理退票 / 支付 / 改签，或回到对话继续。')
    if not recorded and not list_mismatch:
        st.info('这次没有查到本人订单。')
        _guide('下单后再回到本面板查看订单状态与后续操作。')
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
            with st.expander('上次查询结果'):st.write({k:old.get(k) for k in ('order_id','train_no','date','seat_type','amount','status')})
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
                        execute(session,'refund',q,confirmed=True);s.pop('order_result',None)
                        st.success('退票已完成，请重新查询订单。')
                        _guide('重新查询订单核对状态。')
                    except ValueError as e:st.warning(str(e))
        if st.button('查看政策',key='fo_policy_'+o['order_id']):
            s['related_policy_ids']=['P01','P02','P03','P07','P12'] if o['has_reschedules'] else ['P01','P07','P11','P12']
            open_panel(session.sid,'问政策');st.rerun()

def refund_calculator_panel(session):
    from target.order_refund import calculate
    st.info('请填写票价金额、发车日期与时间、票种和支付情况；缺少这些条件无法计算手续费。')
    with st.form('feature_refund_calc'):
        st.text_input('出发地（计算说明）',value='上海虹桥',key='fr_from');st.text_input('到达地或里程（不用于估价）',value='杭州东',key='fr_to')
        day=st.date_input('出发日期',value=config.today()+timedelta(days=3),key='fr_date');time=st.time_input('出发时间',value=clock_time(12,0),key='fr_time')
        amount=st.text_input('票价金额（元，必填）',value='500',key='fr_amount')
        kind=st.selectbox('票种',['高铁','机票'],key='fr_kind');status=st.selectbox('支付情况',['paid','pending'],format_func=lambda v:{'paid':'已支付','pending':'待支付'}[v],key='fr_status')
        changed=st.checkbox('此订单已经改签',key='fr_changed')
        submit=st.form_submit_button('计算退票费用')
    if submit:
        if not str(amount).strip():
            st.warning('请填写票价金额（元，必填）后再计算；也可先在对话里问清退票规则。')
            _guide('补齐票价与发车时间后重新计算。')
        else:
            try:
                r=calculate(amount,datetime.combine(day,time),status=status,kind=kind,changed=changed)
                if r.get('error'):
                    st.warning(r['error'])
                    _guide('按提示调整发车时间、支付状态或「是否已改签」后重算；或回到对话核对政策条款。')
                else:
                    st.write('适用条款：'+r['policy_ref'])
                    st.write(f"距发车：{r['seconds_before_departure']/3600:.2f}小时；费率：{r['fee_rate']:.0%}")
                    st.write(f"计算基数：¥{r['amount']:.2f}；手续费：¥{r['fee']:.2f}；退款金额：¥{r['refund']:.2f}")
                    st.write('计算基数×费率=手续费；退款=基数−手续费（待支付订单退款为0）')
                    _status('已按填写条件算出手续费与退款。')
                    _guide('可在对话里核对对应条款，或调整票价 / 时间重算。')
                    from web.interaction import enqueue
                    if enqueue(session.sid,f'查询退票政策条款并核对本次计算结果。票种{kind}，票面{amount}元，发车{datetime.combine(day,time).isoformat()}，支付状态{status}，已经改签{changed}；手续费{r["fee"]}元、退款{r["refund"]}元。仅解释，不执行退票。','form:退票费率'):
                        st.caption('状态：已把本次条件交给对话侧核对政策，结果见左侧聊天与运行记录。')
                    else:st.warning(st.session_state.pop('feature_notice_'+session.sid,'请求未发送，请稍后重试。'))
            except ValueError as e:
                st.warning(str(e))
                _guide('核对票价金额与发车时间格式后重试。')
    st.caption('最终能否退票，以订单状态和适用条款为准。')
    _trade_notice()

def baggage_panel(session):
    st.caption('填写携带品总重量与单件长宽高，查看免费额度、超重费用与尺寸判断。')
    with st.form('baggage_calculator'):
        person=st.selectbox('旅客类型',['成人','儿童'],key='baggage_person')
        weight=st.text_input('携带品总重量（千克）',value='25',key='baggage_weight')
        cols=st.columns(3)
        length=cols[0].text_input('长（厘米）',value='50',key='baggage_length')
        width=cols[1].text_input('宽（厘米）',value='40',key='baggage_width')
        height=cols[2].text_input('高（厘米）',value='30',key='baggage_height')
        calculate=st.form_submit_button('计算行李费用')
    if calculate:
        try:
            from target.baggage import calculate_baggage
            result=calculate_baggage(person,weight,length,width,height)
            state(session)['baggage_result']=result
            st.write('免费额度：'+result['free_kg']+' 千克；超重：'+result['excess_kg']+' 千克。')
            st.write('超重费用：¥'+result['weight_fee_yuan']+'（来源：P06）')
            st.write('该物品尺寸总和：'+result['item_sum_cm']+' 厘米；'+result['size_status'])
            st.caption(result['note'])
            _status('已按填写条件算出超重费用与尺寸状态。')
            _guide('可在对话里核对 P06 条款，或调整重量 / 尺寸后重新计算。')
            from web.interaction import enqueue
            if enqueue(session.sid,f'查询 P06 行李条款并核对本次计算结果：{person}，总重{weight}千克，单件长宽高{length}/{width}/{height}厘米，超重费用{result["weight_fee_yuan"]}元。仅解释，不办理交易。','form:行李费用'):
                st.caption('状态：已把本次条件交给对话侧核对政策，结果见左侧聊天与运行记录。')
            else:st.warning(st.session_state.pop('feature_notice_'+session.sid,'请求未发送，请稍后重试。'))
        except ValueError as exc:
            st.warning(str(exc))
            _guide('确认重量与长宽高为有效数字后重试；也可在对话里问清 P06 规定。')
    if not calculate and state(session).get('baggage_result'):
        result=state(session)['baggage_result']
        st.write('免费额度：'+result['free_kg']+' 千克；超重：'+result['excess_kg']+' 千克。')
        st.write('超重费用：¥'+result['weight_fee_yuan']+'（来源：P06）')
        st.write('该物品尺寸总和：'+result['item_sum_cm']+' 厘米；'+result['size_status'])
        st.caption(result['note'])
        _status('已保留上次计算结果。')
        _guide('调整条件后重新计算，或回到对话核对 P06 条款。')

def change_panel(session):
    from web.order_actions import change_panel as existing
    _trade_notice()
    # V3.9 paid orders live in the committed railway read model, not tickets.db.
    # Reading only the legacy table made a just-paid order look unchangeable.
    from web.railway_queries import paid_orders,open_change_card,change_candidates
    paid=paid_orders(session)
    if paid:
        order=paid[0];oid=str(order['order_id'])
        st.write('订单 '+oid+' · 票面 ¥'+f"{(order.get('total_fen') or 0)/100:.2f}")
        candidates,args=change_candidates(session,order)
        if not candidates:
            st.info('请先在对话里查询这一线路的车次，再选择要改签到的班次。')
            return
        target=st.selectbox('改签到',candidates,
            format_func=lambda t:str(t.get('trip_short_name') or t.get('trip_id'))+' · '+str(t.get('departure_at') or ''),
            key='fc_v39_target_'+oid)
        if st.button('生成改签确认卡',key='fc_v39_change_'+oid):
            ok,pid,reply=open_change_card(session,order,target,args,'办理改签')
            if ok:st.rerun()
            st.warning(reply)
        _guide('生成确认卡后，在主对话里核对差价并确认。')
        return
    rows=order_read_model.orders(session.root/'tickets.db') if not session.read_only else []
    eligible={o['order_id']:o for o in rows if o['actions']['reschedule']['allowed']}
    if not eligible:
        st.info('还没有可改签的已支付订单。完成下单与支付后即可在这里办理。')
        return
    _status('已列出 '+str(len(eligible))+' 个可改签订单。')
    _guide('选定订单后预览差价，再到右侧确认。')
    oid=st.selectbox('选择改签订单',list(eligible),key='fc_order');existing(session,eligible[oid])

def render(session):
    saved=state(session).setdefault('forms',{})
    same_session=st.session_state.get('feature_forms_owner')==session.sid
    st.session_state['feature_forms_owner']=session.sid
    for key in FORM_KEYS:
        if key in st.session_state:
            if same_session:
                saved[key]=st.session_state[key]
            else:
                st.session_state.pop(key)
        if key not in st.session_state and key in saved:
            st.session_state[key]=saved[key]
    # A refused request must never look like a button that did nothing.
    notice=st.session_state.pop('feature_notice_'+session.sid,None)
    if notice:st.warning(notice)
    st.markdown('**常用功能**')
    from web.interaction import launch,busy
    disabled=session.read_only or busy(session) or bool(session.pending_action())
    with st.container(key='feature_actions'):
        for name in NAMES:
            st.button(name,key='feature_nav_'+session.sid+'_'+name,on_click=launch,args=(session.sid,name),
                      width='stretch',disabled=disabled)
    name=st.session_state.get('feature_panel_'+session.sid)
    # Client handover note 2.2: panels open only on demand; the baggage panel
    # must not sit in the rail as a permanent expander.
    if name:
        with st.container(key='feature_panel_header',horizontal=True,vertical_alignment='center'):
            st.markdown('### '+name)
            if st.button('关闭面板',key='feature_close_'+session.sid):
                st.session_state.pop('feature_panel_'+session.sid,None);st.rerun()
        if name=='行李费用':
            baggage_panel(session);return
        dict(zip(NAMES,(ticket_search_panel,policy_browser_panel,my_orders_panel,refund_calculator_panel,baggage_panel,change_panel)))[name](session)
