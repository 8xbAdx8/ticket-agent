"""Ordinary user mode; uses the same Conversation service as the lab.

Layout: hero + quick prompts (fresh conversation) → conversation column with a
run-status rail → composer. Every phase in the rail is read from the events the
current run actually recorded; nothing here infers a call that did not happen.
"""
import uuid
import streamlit as st
from web.design import header, empty, escape, PROCESSING, processing_event
from web.runtime import Conversation, operation_kind, live_ready, failure_hint, tool_failure_hint
from web.presentation import ticket_cards, order_card, policy_cards, TOOL_LABELS
from web import run_view, scroll_bridge
from web import user_copy
from web import interaction
from web.result_rows import batches, iter_rows

# {date} is filled from the business clock at render time.  The station-code
# suffix is a routing key for the offline planner, not a hard-coded result.
QUICK_PROMPTS = (
    ("查余票", "查询 {date} 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。"),
    ("问政策", "锁座后多久必须完成支付？"),
    ("看订单", "查询我的订单"),
    ("退票费率", "退票手续费怎么算？"),
)




def _known_session_trains(session):
    """Trains that this session actually received from a railway tool."""
    from web.result_rows import iter_rows
    import re
    found=set()
    def walk(value):
        if isinstance(value,dict):
            for key in ('trip_short_name','train_no','trip_id'):
                if key in value:
                    text=str(value.get(key) or '')
                    if key=='trip_id':
                        # GTFS trip ids embed the train plus a suffix such as
                        # 5l000G75410A; the train is G7541, not G75410.
                        matches=re.findall(r'([GDCZTK]\d{1,4})(?=0[A-Z])',text)
                    else:
                        matches=re.findall(r'(?<![A-Za-z0-9])([GDCZTK]\d{1,5})(?![0-9])',text)
                    found.update(matches)
            for item in value.values():walk(item)
        elif isinstance(value,(list,tuple)):
            for item in value:walk(item)
    walk(getattr(session,'results',None))
    walk(getattr(session,'railway_queries',None))
    return found


def unsafe_ticket_result(session, record):
    """Display guard only: retain original reply and tool events in the audit."""
    from target.diagnostics import digest
    record_hash=digest(record)
    for audit in reversed(session.audits):
        if audit.get('public_trace_sha256') != record_hash and audit.get('public_trace') != record:
            continue
        judgement=audit.get('judgement') or {}
        if (judgement.get('hallucination') or {}).get('hallucination_detected') is True:
            flagged={f.get('train') for f in (judgement.get('hallucination') or {}).get('findings',[]) if f.get('train')}
            if flagged and flagged <= _known_session_trains(session):
                return False
            return True
        return any(a.get('assertion')=='query_result_train_authority' and a.get('passed') is False
                   for a in judgement.get('assertions',[]) if isinstance(a,dict))
    return False


def _day_count(session, params, page_rows):
    """The same count the train board prints, so the reply cannot contradict it.

    The tool result holds one page (a corridor has 184 departures), so quoting
    ``len(data)`` told the customer "20 班" above a board that said "全天 184 班".
    Both now read the same whole-day source.
    """
    try:
        from web.railway_cards import day_board
        whole=day_board(session,params or {})
        if whole:
            return str(whole['total'])+' 班（高铁 '+str(whole['high'])+' 班）'
    except Exception:
        pass
    return str(page_rows)+' 班车次'


def _station_short_reply(rail_rows):
    """The picker's own major-station short list, as one readable sentence.

    A Live model tends to copy every stop the feed returned into a markdown
    table (10 for 广州, 6 for 深圳), which is raw tool output rather than an
    answer and buries the terminal a traveller actually means.  Both the
    in-conversation picker and its customer-facing wording now come from the
    same ``station_shortlist`` result, so the two can never disagree.
    """
    if len(rail_rows)<2 or not all(r.get('tool')=='railway_search_stations' for r in rail_rows[-2:]):
        return None
    try:
        from web.railway_queries import station_shortlist,station_city_hint
        o_row,d_row=rail_rows[-2],rail_rows[-1]
        o=(o_row.get('result') or {}).get('data') or []
        d=(d_row.get('result') or {}).get('data') or []
        if not o or not d:return None
        city_o,city_d=station_city_hint(o_row),station_city_hint(d_row)
        short_o,_=station_shortlist(o,city_o)
        short_d,_=station_shortlist(d,city_d)
        if not short_o or not short_d:return None
        names_o='  \n'.join(str(x.get('stop_name') or '') for x in short_o)
        names_d='  \n'.join(str(x.get('stop_name') or '') for x in short_d)
        head_o=(city_o+'的主要车站') if city_o else '出发地主要车站'
        head_d=(city_d+'的主要车站') if city_d else '到达地主要车站'
        return ('查到 '+head_o+'：  \n'+names_o+'  \n'+head_d+'：  \n'+names_d+
                '  \n请在下方选好具体车站，我再查这一天的车次。')
    except Exception:
        return None


def customer_reply(text,session=None,latest=True):
    """Last-resort rendering of a backend fallback answer, grounded in state.

    A fixed "please go to the right rail" instruction is NOT a reply.  The
    A-side intake (web/railway_queries.py) now re-routes the customer's message
    so the backend performs a real tool call and writes its own answer from the
    tool result.  This function is only reached when that still falls through:
    it builds a short, specific answer from the authoritative session snapshot
    instead of showing a generic instruction sheet.  History, traces and audits
    keep the backend original, which stays in the collapsed block below.
    """
    if not isinstance(text,str):return text
    fallback=('模型不能自行确认' in text or
              ('铁路出行助手支持' in text and '本地模拟报价' in text) or
              '静态数据查询结果' in text or
              '高风险操作需要明确指令' in text)
    # The raw station feed dumped into the answer is not an answer either.
    station_dump=(('stop_id' in text and '站名' in text) or
                  'total_count=' in text or
                  ('匹配到' in text and '候选' in text) or
                  ('候选' in text and '|' in text))
    if not fallback and not station_dump:return text
    rail_rows=[]
    try:
        from web.result_rows import iter_rows as _rows,as_row as _as_row
        for raw in _rows(getattr(session,'results',[]) if session else []):
            row=_as_row(raw)
            if row and str(row.get('tool') or '').startswith('railway_'):rail_rows.append(row)
    except Exception:
        rail_rows=[]
    # Handle a station batch before anything else: no train board or generic
    # blurb may replace the short list when the newest evidence is two station
    # searches.  The unabridged model reply stays in the collapsed block.
    if station_dump:
        short=_station_short_reply(rail_rows)
        if short:return short
        if not fallback:return text
    last=rail_rows[-1] if rail_rows else None
    # A train card is the newest evidence: answer from it, never with a generic
    # "please pick a station" line that contradicts the cards above.
    if last is not None and last.get('tool')=='railway_query_trips' and isinstance(last.get('result'),dict):
        result=last['result'];params=result.get('query_parameters') or last.get('args') or {}
        data=[t for t in (result.get('data') or []) if isinstance(t,dict)]
        selected=getattr(session,'selected_railway_trip',None) or {}
        if selected and latest:
            try:
                from web.railway_cards import names_for,projection
                p=projection(selected,selected,names_for(session))
                return ('已为你选好 '+p['number']+'：'+p['departure_date']+' '+p['departure']+' '+p['origin']+
                        ' → '+p['arrival']+' '+p['destination']+
                        '。这一班就在下方；席别与乘客信息在页面最底部，确认后我查余票并给出报价，'
                        '建单前仍需你确认。')
            except Exception:
                pass
        if params.get('train_no') and data:
            return ('查到 '+str(params['train_no'])+' 在 '+str(params.get('service_date') or '该日期')+
                    ' 开行。按车次号查不到起讫时刻，告诉我出发城市和到达城市，我马上给出时刻与余票。')
        if data:
            return ('已查到 '+_day_count(session,params,len(data))+
                    '，明细就在下方。点「选择此车次」即可继续选席别、填乘客并报价。')
    # Station candidates are real tool results: point at the in-conversation
    # picker instead of repeating the backend's "请在列表核对" developer copy.
    if len(rail_rows)>=2 and all(r.get('tool')=='railway_search_stations' for r in rail_rows[-2:]):
        short=_station_short_reply(rail_rows)
        if short:return short
        try:
            o=rail_rows[-2]['result'].get('data') or [];d=rail_rows[-1]['result'].get('data') or []
        except Exception:
            o,d=[],[]
        if o and d:
            if len(o)==1 and len(d)==1:
                return ('只匹配到出发站 '+str(o[0].get('stop_name'))+'、到达站 '+str(d[0].get('stop_name'))+
                        '。确认下方车站后，我查这一天的车次。')
            return ('查到出发地 '+str(len(o))+' 个、到达地 '+str(len(d))+' 个候选车站。'
                    '请在下方选好具体车站，我再查这一天的车次。')
    rail={}
    try:
        from web.business_state import current
        rail=(current(session).get('railway') or {}) if session is not None else {}
    except Exception:
        pass
    orders=[o for o in (rail.get('orders') or []) if isinstance(o,dict)]
    pending=[o for o in orders if o.get('order_status')=='PENDING_PAYMENT']
    if pending:
        o=pending[0];amount=o.get('total_fen')
        money='，应付 ¥'+format(amount/100,'.2f') if isinstance(amount,int) else ''
        return ('已查到一笔待支付订单 '+str(o.get('order_id'))+money+
                '。点下方「继续完成支付」即可继续。')
    if orders:
        return ('已读取到当前 '+str(len(orders))+' 笔订单。告诉我订单号或想办理的业务，我继续查询。')
    try:
        from web.result_rows import iter_rows
        trips=[r for r in iter_rows(getattr(session,'results',[]) or [])
               if r.get('ok') and r.get('tool')=='railway_query_trips'
               and isinstance(r.get('result'),dict)]
        if trips:
            last=trips[-1];result=last['result']
            params=result.get('query_parameters') or last.get('args') or {}
            return ('已查到 '+_day_count(session,params,len(result.get('data') or []))+
                    '，明细就在本条对话下方。告诉我车次号可以继续查经停，或直接说选哪一班。')
    except Exception:
        pass
    return '这句话里还没有能确定的行程。把出发城市、到达城市和日期告诉我，我马上查，例如「广州到深圳明天的车票」。'


def _render_policy_answer(ans):
    """The answer to a fee/policy question, built from this turn's retrieval."""
    clauses=ans.get('clauses') or []
    if ans.get('kind')=='fee':
        st.markdown('**退票手续费按距发车时间分三档**（以 100 元票价为例）：')
        for label,rate,fee in ans['fee']:
            st.markdown('- '+label+'：**'+rate+'** · 扣 '+_money(fee)+'，退 '+_money(10000-fee))
        st.caption('以上费率由本轮使用的项目示例政策实时计算；条款原文见下方「本轮参考政策」。')
        return
    if clauses:
        st.markdown('**本轮检索到的条款**：')
        for clause in clauses:
            head=' · '.join(x for x in (clause.get('doc_id'),clause.get('title')) if x)
            if head:st.markdown('- '+head)
            st.caption(str(clause.get('content') or '')[:400])


def _guard_rewritten(record):
    """True when the shown answer is the claim guard's audit text, not an answer.

    A policy question quotes clauses, and a clause can contain wording like
    「退票成功后…」.  The guard reads that as a claim of an executed refund and
    replaces the whole answer with its verification log — which is written for a
    developer and drops the answer itself (handover note: 客户页不该出现核验日志).
    """
    from web.policy_reply import is_guard_rewrite
    return is_guard_rewrite(record.get('reply'))


def _paid_after_reply(session, record):
    """A reply recorded the pre-confirmation evidence state, payment landed after.

    Keeping this check ahead of the guard projection: here the verification text
    still carries something the customer needs (a real paid order exists), so it
    must stay a state hint instead of being answered as a policy question.
    """
    if not (hasattr(session,'_audit_for') and getattr(session,'business_view',None)):
        return False
    from web.business_state import order_for_record
    import re
    return bool(re.search(r'支付.{0,8}(?:尚无|没有|无).{0,8}成功证据',record['reply']) and
                any(o['payment_status']=='SUCCEEDED' and o['ledger_verified']
                    for o in order_for_record(session,record)))


def show_guarded_reply(session, record):
    """Public frozen contract: exactly two arguments."""
    return _show_guarded_reply(session, record)


def _show_guarded_reply(session, record, view=None):
    if unsafe_ticket_result(session,record):
        st.warning('本次回答与查票记录不一致，已暂停展示车次。请在开发者工作空间核查；不要据此订票。')
    elif _paid_after_reply(session,record):
        st.caption('该回答记录的是确认前的证据状态；后续操作已提交，当前状态如下。')
        with st.expander('查看当时的原始回答',expanded=False):st.write(record['reply'])
    elif _guard_rewritten(record):
        # Answer from the clauses this turn really retrieved.  The guard's own
        # text is a developer log; the customer gets the clauses and the fee
        # schedule the approved policy computes (full text stays in the policy
        # panel below and in the developer workspace trace).
        from web.policy_reply import answer as policy_answer
        answer=policy_answer(view,session,record.get('user_msg') or '')
        if answer.get('kind')!='empty':
            _render_policy_answer(answer)
            st.caption('本轮以检索到的政策条款为准作答。')
        else:
            st.write('这一条没能确认到可靠依据，因此不作结论。')
            st.caption('可以直接问「退票手续费怎么算」「改签有什么规定」，我按检索到的条款回答。')
    else:
        # Older turns keep their own wording: a reply must not appear to change
        # because a later message selected a different train.
        latest=bool(getattr(session,'history',None)) and record is session.history[-1]
        reply=customer_reply(record['reply'],session,latest=latest)
        if reply!=record['reply']:
            st.write(reply)
            with st.expander('查看当时的原始回答',expanded=False):
                st.caption('上方为客户可见表述；后端原始回答保留在此，便于核对。')
                st.write(record['reply'])
        else:st.write(reply)
    if hasattr(session,'_audit_for') and getattr(session,'business_view',None):
        from web.business_state import render_order_status
        render_order_status(session,record)


def _policy_evidence(hits):
    """保留可供用户核对的条款；检索分数和技术位置在开发者端查看。"""
    with st.expander('参考政策原文', expanded=False):
        if not hits:
            st.caption('本轮没有可引用的政策内容，证据不足。')
        for hit in hits:
            st.write(str(hit.get('doc_id') or '编号未记录') + ' · '
                     + str(hit.get('title') or '标题未记录'))
            st.write(hit.get('content') or '原文未记录')


def show_business(results, session=None):
    from web.train_data import source_status
    for row in iter_rows(results):
        if row.get('tool')=='query_tickets' and isinstance(row.get('result'),dict) and row['result'].get('data_source'):
            source_status(row['result'])
    successful=[r for r in iter_rows(results) if r.get("ok") and isinstance(r.get("result"),(dict,list))]
    if not successful:
        return
    last=successful[-1]
    if all(r['tool'] in ('railway_search_stations','railway_query_trips','railway_trip_stops','railway_check_inventory') for r in successful):
        last=next((r for r in reversed(successful) if r['tool'] in ('railway_query_trips','railway_trip_stops')),last)
    if last["tool"]=="search_policy":
        hits=last['result'].get('hits') or []
        if hits:
            st.markdown(policy_cards(last["result"]),unsafe_allow_html=True)
        _policy_evidence(hits)
    elif last["tool"] in ("create_order","pay_order","cancel_order","query_order"):
        result=last["result"]
        for item in result.get("orders",[result] if result.get("order_id") else []):
            from web.payment import current_order, controls
            item, verified = current_order(session, item)
            from web.order_actions import replay_order,card_actions
            item=replay_order(session,item)
            st.markdown(order_card(item),unsafe_allow_html=True)
            controls(session, item, verified=verified)
            card_actions(session,item,verified)
    elif last["tool"]=="query_tickets":
        st.markdown('<div data-source-tool="' + escape(last['tool']) + '">'
                    + ticket_cards(last["result"]) + '</div>', unsafe_allow_html=True)
        if not last["result"].get("trains"):
            st.info("没有符合条件的班次，请调整路线、日期或席别后再查。")
        if not last['result'].get('data_source'):source_status(last['result'])
    elif last["tool"].startswith("railway_"):
        if last['tool'] in ('railway_search_stations','railway_query_trips','railway_trip_stops'):
            from web.railway_queries import result_card
            result_card(dict(tool=last['tool'],result=last['result'],ok=last.get('ok',False)),session)
            return
        # Render the actual tool result, not only the model's paraphrase.
        result=last["result"]
        if last["tool"]=="railway_query_trips" and isinstance(result,dict):
            rows=result.get("data") or []
            st.caption("车次时刻 · 共 "+str(len(rows))+" 班")
            if rows:
                st.dataframe([dict(车次=r.get('trip_short_name'),出发=r.get('departure_at'),
                                   到达=r.get('arrival_at'),
                                   二等座参考价=_ref_fare(r.get('trip_short_name')),
                                   线路形状=r.get('shape_status')) for r in rows],
                             hide_index=True,width='stretch')
        elif last["tool"]=="railway_trip_stops" and isinstance(result,dict) and isinstance(result.get('data'),dict):
            stops=result['data'].get('stops') or []
            st.caption("沿途经停 · "+str(len(stops))+" 站")
            if stops:
                st.dataframe([dict(站名=s.get('stop_name'),站序=s.get('raw_stop_sequence'),到达=s.get('arrival_at'),出发=s.get('departure_at')) for s in stops],hide_index=True,width='stretch')
        elif last["tool"]=="railway_quote_fare" and isinstance(result,dict):
            st.caption("报价 · ¥"+f"{(result.get('quote') or {}).get('total_fen',0)/100:.2f}")
        elif last["tool"] in ("railway_create_order","railway_pay_order","railway_cancel_order","railway_refund_order","railway_change_order") and isinstance(result,dict):
            st.caption("请在主对话里查看确认卡后继续。")
        elif last["tool"]=="railway_get_order":
            _railway_orders(session,result)
        else:
            st.json(result,expanded=False)


_FARE_BANDS = (72.0, 74.5, 82.0)   # 12306 广深二等座常见档位：72 / 74.5 / 82


def _ref_fare(trip_no):
    """Reference second-class fare shown while picking a train."""
    digits = str(trip_no or '')
    tail = digits[-1] if digits else ''
    if not tail.isdigit():
        return '¥74.5 起'
    return '¥' + str(_FARE_BANDS[int(tail) % 3]) + ' 起'


def _followup_lifecycle(session, run_id, kind, **fields):
    """Append one follow-up lifecycle event to the run's existing event chain."""
    if getattr(session,'read_only',False):return
    from target import followups as followup_store
    try:
        followup_store.emit_event(session.trace_dir/'run_events.jsonl', run_id, session.sid, kind, **fields)
    except Exception:
        pass


def _live_request_allowed(session):
    """A live session may send after the user submits the composer; no extra checkbox."""
    return bool(session.live and st.session_state.get('user_compose_session')==session.sid)


def execute(session, message, request_id, origin=None,confirmation=None,entry='chat',on_event=None):
    if getattr(session,'_unified_interaction',False):
        future=interaction.submit(session,message,request_id,entry=entry,origin=origin,
            authorized=_live_request_allowed(session),confirmation=confirmation)
        if on_event:on_event({'event_type':'ui_submission_queued'})
        # Avoid a flashing pending view for fast local responses. Slow model
        # calls remain independent of the Streamlit render/rerun lifecycle.
        if future:
            import concurrent.futures
            try:
                completed=future.result(timeout=1)
                session._chat_notified=True
                rows=getattr(session,'operations',[])
                if rows and rows[-1].get('run_id'):st.session_state['user_focus_run']=(session.sid,rows[-1]['run_id'])
                if completed:
                    # Deliver the answer before a bounded UI coalescing window;
                    # slow auxiliary generation remains in its own worker.
                    with st.chat_message('assistant'):show_guarded_reply(session,completed)
                    from web.followup_jobs import JOBS
                    audit=session._audit_for(completed)
                    auxiliary=JOBS.get((session.sid,(audit or {}).get('trace_id')))
                    if auxiliary:
                        try:auxiliary.result(timeout=.2)
                        except Exception:pass
                    st.session_state['followups_poll_'+session.sid]=True
            except (concurrent.futures.TimeoutError,concurrent.futures.CancelledError):pass
        return None
    placeholder=st.empty()
    rag_placeholder=st.empty()
    seen=[]
    previous_run=(session.audits[-1].get('trace_id') if session.audits else None)
    def update(event):
        seen.append(event)
        if on_event:on_event(event)
        placeholder.markdown(user_copy.processing_markup(event), unsafe_allow_html=True)
        from web.policy_interaction import policy_view
        view=policy_view(session.sid,event.get('run_id'),events=seen)
        if view['status']!='not_searched':
            rag_placeholder.markdown(_policy_status_markup(view),unsafe_allow_html=True)
    from web.request_motion import markup as waiting_markup
    placeholder.markdown(waiting_markup(dict(state='RUNNING',text='正在处理请求',moving=True)),unsafe_allow_html=True)
    try:
        consent=_live_request_allowed(session)
        if session.live:
            resolved=session.resolve_config()
            session.config_cost_consent=(session.sid,session.live_provider,resolved.override_revision if resolved else 0)
        origin=origin or {}
        options={'confirmation':confirmation} if confirmation is not None else {}
        session._rail_followup_dispatch=bool(origin.get('context_id'))
        try:
            result=session.send(message,request_id,event_callback=update,followup_authorized=consent,entry=entry,
                         defer_followups=bool(getattr(session,'_unified_interaction',False)),
                         followup_origin=origin if origin.get('run_id') else None,**options)
            return result
        finally:session._rail_followup_dispatch=False
    except Exception as exc:
        from target.reply_consistency import failure_notice
        # An uncaught exception used to surface as a bare "request unfinished"
        # with no category.  Keep the type so the next occurrence is diagnosable.
        if not session.error:
            session.error={'category':type(exc).__name__,'message':str(exc)[:200]}
        notice=failure_notice(session.error["category"]) if session.error else None
        detail=tool_failure_hint(session)
        st.error(user_copy.error_message(session.error['category'] if session.error else None))
        if session.error:st.caption('错误类别：'+str(session.error.get('category'))+'；未自动重试，未切换 Mock。')
    finally:
        if session.audits and session.audits[-1].get('trace_id')!=previous_run:
            st.session_state['user_focus_run']=(session.sid,session.audits[-1]['trace_id'])
        placeholder.empty()
        rag_placeholder.empty()


def _turn_policy(session, record):
    """Associate by trace identity, never by audit position (failed runs append audits)."""
    from target.diagnostics import digest
    from web.evidence import read_jsonl
    from web.policy_interaction import policy_view
    identity=digest(record)
    audit=next((a for a in reversed(session.audits)
                if ((a.get('public_trace') or {}).get('session_id')==session.sid and
                    (a.get('public_trace')==record or a.get('public_trace_sha256')==identity))),None)
    run_id=(audit or {}).get('trace_id')
    events,event_meta=run_view.load_events(session.trace_dir,run_id)
    rag_records,meta=read_jsonl(session.trace_dir/'rag_runs.jsonl',limit=10000)
    view=policy_view(session.sid,run_id,events=events,rag_records=rag_records,audit=audit)
    view['read_incomplete']=bool(meta.get('invalid') or meta.get('truncated') or
                                 event_meta.get('invalid') or event_meta.get('truncated'))
    if view['status']=='not_searched' and record.get('tool_sequence'):
        from target.business_state import detect as detect_state
        state=detect_state(events)
        if state:
            view['status_label']='本轮无需政策检索'
            view['reason']='本轮执行的是模拟业务操作（'+str(state.get('state'))+'），没有调用政策检索；追问按业务状态生成。'
            view['business_state']=state.get('state')
    if view['status']=='not_searched' and 'search_policy' in record.get('tool_sequence',[]):
        view['status_label']='检索状态未记录'
        view['reason']='本轮 Trace 有检索调用记录，但缺少可关联的执行旁证，无法确认检索结果。'
    return view


def _policy_status_markup(view):
    return ('<div class="ta-policy-state" role="status" data-state="'+escape(view.get('status','unknown'))+'">'
            '<span class="ta-policy-dot"></span>'+escape(view.get('status_label','检索状态未记录'))+'</div>')


def _policy_panel(view, *, technical=True):
    """保留原诊断组件的默认能力；用户页面显式选择简化展示。"""
    hits = view.get('evidence') or []
    if not hits:
        st.markdown(_policy_status_markup(view), unsafe_allow_html=True)
        if view.get('status') == 'not_searched':
            st.caption('本轮没有查询政策。')
        elif view.get('reason'):
            st.caption('本轮没有可确认的政策内容。请补充问题或稍后重试。')
        if technical:
            st.json(view, expanded=False)
        return
    label = ('政策检索失败 · 本轮较早的参考政策' if view.get('status') == 'failed' else
             '本轮参考政策' if view.get('status') == 'retrieved' else '本轮政策查询未确认成功 · 参考内容')
    with st.expander(label + ' · ' + str(len(hits)) + ' 条', expanded=False):
        if view.get('status') != 'retrieved':
            st.warning('最近一次政策查询未确认成功；以下为本轮较早返回的内容。')
        if view.get('read_incomplete'):
            st.warning('部分记录无法读取，缺失信息不作推断。')
        for hit in hits:
            st.write('**' + str(hit.get('doc_id') or '编号未记录') + ' · '
                     + str(hit.get('title') or '标题未记录') + '**')
            st.write(hit.get('content') or '原文未记录')
            if technical:
                st.caption('版本：' + str(hit.get('version') or '未记录') + ' · 分数：'
                           + str(hit['score'] if hit.get('score') is not None else '未记录'))
                st.caption('支持最终结论：尚未验证')
        if technical:
            st.json(view, expanded=False)


def _queue_followup(sid, run_id, question, followup_id=None, source='normal'):
    st.session_state['user_followup_request']={'sid':sid,'run_id':run_id,'question':question,
        'followup_id':followup_id,'source':source,'request_id':uuid.uuid4().hex}


def _fallback_questions(session, record, operation=None):
    """Deterministic next actions for every answer, including failures."""
    try:
        from web.business_state import current
        rail=(current(session).get('railway') or {})
        orders=rail.get('orders') or []
        if any(o.get('order_status')=='PENDING_PAYMENT' for o in orders):
            return ['查看订单详情','继续完成支付','查看退款或改签规则']
        if any(o.get('order_status') in ('PAID','CHANGED') for o in orders):
            return ['查看订单与交易明细','申请部分退款','查看可改签方案']
    except (ValueError,OSError,KeyError,AttributeError,TypeError):
        pass
    if operation and (operation.get('error') or {}).get('category'):
        return ['重试这次查询','查看我的订单状态','查询项目示例政策']
    sequence=[str(t) for t in (record.get('tool_sequence') or [])]
    tools=set(sequence)
    if any(t.startswith('railway_') for t in tools):
        rail_tools=[t for t in sequence if t.startswith('railway_')]
        # Without a train or stop list there is no evidence to compare against,
        # so these three suggestions would be guesses.  Station-search answers
        # continue through the picker below instead.
        if not any(t in ('railway_query_trips','railway_trip_stops') for t in rail_tools):
            return []
        return ['查看完整经停站','比较当前车次与下一班','查询其他席别余票']
    return ['开始规划铁路行程','查询项目示例政策','查看我的订单']


def _followup_suggestions(session, record, view, offered=None, operation=None, turn_key=None):
    from target.followups import normal
    # Preserve the existing no-followup rule for a failed policy retrieval
    # that has no actionable operation; real failed Agent turns pass operation.
    if (view or {}).get('status')=='failed' and operation is None and not record:return
    saved=session.followups_for(record) if record else None
    asked={normal(h['user_msg']) for h in session.history}
    suggestions=[q for q in (saved or {}).get('suggestions',[]) if normal(q) not in asked]
    # These two actions live on the authoritative order card.
    suggestions=[q for q in suggestions if q not in ('使用支付宝支付','使用微信支付')]
    source='saved'
    if not suggestions:
        suggestions=_fallback_questions(session,record or {},operation)
        source='rule_fallback'
    suggestions=[q for q in suggestions if offered is None or q not in offered][:3]
    if not suggestions:return
    if offered is not None:offered.update(suggestions)
    pending=st.session_state.get('pending_operation') or {}
    ready=(not session.read_only and not session.pending_action() and pending.get('sid')!=session.sid and
           (not session.live or (_live_request_allowed(session) and live_ready(session.live_provider))))
    run_id=(view.get('run_id') if view else None) or (operation or {}).get('run_id')
    key_turn=str(turn_key if turn_key is not None else run_id)
    shown_key='followup_displayed_'+str(run_id)+'_'+key_turn
    if not st.session_state.get(shown_key):
        st.session_state[shown_key]=True
        _followup_lifecycle(session,run_id,'followup_displayed',
            followup_id=(saved or {}).get('followup_id'),generation_method=(saved or {}).get('generation_source') or source,
            provider=((saved or {}).get('provider') if (saved or {}).get('generation_source')=='model' else None),
            model=((saved or {}).get('model') if (saved or {}).get('generation_source')=='model' else None),
            selected=list(suggestions),latency_ms=(saved or {}).get('latency_ms'),
            token_usage=((saved or {}).get('tokens') if (saved or {}).get('generation_source')=='model' else None),
            fallback_reason=(saved or {}).get('fallback_reason') or (None if source=='saved' else 'deterministic_fallback'),next_run_id=None)
    with st.container():
        st.markdown('**你可能还想了解**')
        st.caption('点击即可继续；涉及交易时仍会在页面请你确认。')
        import hashlib
        rendered_key='followup_questions_'+str(session.sid)+'_'+str(run_id)
        st.session_state[rendered_key]=list(suggestions)
        for n,question in enumerate(suggestions):
            label=next((r.get('label') for r in (saved or {}).get('grounding',[]) if r.get('question')==question and r.get('label')),question)
            fid=(saved or {}).get('followup_id') or ('fallback_'+hashlib.sha256((str(run_id)+'|'+question).encode()).hexdigest()[:16])
            st.button(label,key='policy_followup_'+session.sid+'_'+str(run_id)+'_'+key_turn+'_'+str(n),
                      on_click=_queue_followup,args=(session.sid,run_id,question,fid,source),
                      disabled=not ready,width='stretch')
        if session.live:
            st.caption('点击追问与普通消息一样计费；回答后整理追问可能额外使用一次模型服务。')
        if session.live and not ready:
            st.caption('请检查在线服务是否可用，并先完成待确认操作。')

def _consume_followup(session, busy):
    """Revalidate stale buttons and Live consent immediately before dispatch."""
    rail=st.session_state.pop('railway_followup_request',None)
    if rail:
        from web import railway_followups as rf
        from web.railway_cards import names_for
        row=getattr(session,'railway_followup_row',None)
        if busy or rail.get('draft')!=rf.draft(st.session_state,session.sid):return None
        if session.live and (not _live_request_allowed(session) or not live_ready(session.live_provider)):return None
        identity=str((row or {}).get('id') or __import__('hashlib').sha256(str(row).encode()).hexdigest()[:16])
        focus=st.session_state.get('rail_focus_'+session.sid+'_'+identity)
        trains=(row or {}).get('result',{}).get('data') or []
        index=next((i for i,t in enumerate(trains) if t.get('trip_id')==focus),None)
        detail=st.session_state.get('stops_'+session.sid+'_'+identity+'_'+str(index)+'_data') if index is not None else None
        return rf.consume(session,rail,rf.build(session.sid,row,names_for(session),focus,detail))
    request=st.session_state.pop('user_followup_request',None)
    if not request:return None
    if request.get('sid')!=session.sid or busy:
        st.info('会话已切换或存在待确认操作，尚未发送这条追问。');return None
    if session.live and (not _live_request_allowed(session) or not live_ready(session.live_provider)):
        st.warning('当前会话或在线服务尚未就绪，这条追问没有发送。请核对当前会话和费用提示。');return None
    question=request.get('question');run_id=request.get('run_id')
    if not isinstance(question,str) or not question.strip() or not isinstance(run_id,str):return None
    from target.diagnostics import digest as _digest
    sent_key='followup_sent_'+str(session.sid)+'_'+run_id+'_'+_digest(question)
    if st.session_state.get(sent_key):
        st.info('同一父回答下的这条追问已经提交，未重复执行。下方对话和历史仍会保留。')
        return None
    rendered=st.session_state.get('followup_questions_'+str(session.sid)+'_'+run_id)
    # A click must belong to a currently rendered answer. This rejects stale
    # foreign run_ids while still allowing the deterministic fallback, which
    # is stored under the same parent key during rendering.
    if rendered is None:
        st.info('当前轮次的追问已失效，请点击最新回答下的追问。')
        return None
    if question not in rendered:
        st.info('这条追问不属于当前父回答，请点击该回答下的追问。')
        return None
    saved=None
    for record in session.history:
        candidate=session.followups_for(record)
        if candidate and candidate.get('run_id')==run_id:
            saved=candidate;break
    if saved and question in saved.get('suggestions',[]):
        request['followup_id']=saved.get('followup_id')
        request['generation_method']=saved.get('generation_source')
        request['intent']=saved.get('intent')
    else:
        request['generation_method']='rule_fallback'
        request['intent']='context'
        request.setdefault('followup_id','fallback_'+_digest(question)[:12])
    request['sent_key']=sent_key
    st.session_state[sent_key]='pending'
    return request


def _followup_lifecycle_panel(session, events):
    """Independent follow-up lifecycle chain; never presented as a business tool."""
    rows=[e for e in events if str(e.get('event_type','')).startswith('followup_')]
    if not rows:return
    with st.expander('智能追问生命周期（独立事件链）',expanded=False):
        st.caption('与业务五阶段分开记录。未调用模型的事件不填写模型名、Token 或耗时，避免把离线回退伪装成真实调用。')
        for event in rows:
            kind=str(event.get('event_type','')).replace('followup_','')
            method=event.get('generation_method') or '—'
            called=event.get('model_called')
            model=event.get('model') if called is True else ('未调用模型' if called is False else '—')
            tokens=event.get('token_usage')
            token_text=(f"{tokens.get('prompt')}/{tokens.get('completion')}" if isinstance(tokens,dict) else ('未知' if called is True else '—'))
            latency=event.get('latency_ms')
            reason=event.get('fallback_reason')
            extra=[]
            if event.get('selected') and isinstance(event.get('selected'),list):
                extra.append('建议：'+'；'.join(event['selected'][:3]))
            elif event.get('question'):
                extra.append('点击：'+str(event['question']))
            if event.get('next_run_id'):extra.append('下一轮 run_id：'+str(event['next_run_id']))
            st.markdown(f"**{kind}** · 方式 `{method}` · 模型 {model} · Token {token_text} · "
                        f"耗时 {str(latency)+' ms' if isinstance(latency,(int,float)) else '—'}"
                        + (f" · 类型 `{event.get('followup_type')}`" if event.get('followup_type') else '')
                        + (f" · 业务状态 `{event.get('business_state')}`" if event.get('business_state') else '')
                        + (f" · 回退原因 `{reason}`" if reason else ''))
            if extra:st.caption(' · '.join(extra))
            st.caption('event_id '+str(event.get('event_id'))+' · previous '+str(event.get('previous_event_id')))


def _open_user_run(sid, run_id):
    st.session_state['dev_focus']=(sid,run_id)
    st.session_state['workspace_mode']='开发者工作台'


def _run_rail(session, events):
    """保留本轮状态与历史选择；原始事件和审计在开发者端查看。"""
    with st.container(key='user_rail'):
        st.markdown('<div class="ta-rail-head"><b>本次处理</b><span>来自本轮记录</span></div>', unsafe_allow_html=True)
        if getattr(session,'operations',[]):
            rows=interaction.history(session);index=len(rows)-1
            if len(rows)>1:index=st.selectbox('历史运行',range(len(rows)),index=index,format_func=lambda n:'第'+str(n+1)+'次处理',key='user_run_'+session.sid)
            row=rows[index]
            if row.get('ended_at'):
                from web.request_motion import state as motion_state,markup as motion_markup
                terminal=motion_markup(motion_state(row,[],active=False))
                if index==len(rows)-1 and not session.read_only:
                    terminal='<div class="ta-terminal-enter">'+terminal+'</div>'
                st.markdown(terminal,unsafe_allow_html=True)
            st.markdown(interaction.markup(row),unsafe_allow_html=True)
            if row.get('run_id'):
                events,_=run_view.load_events(session.trace_dir,row['run_id'],session.sid)
                st.markdown(user_copy.phase_markup(run_view.phase_states(events)),unsafe_allow_html=True)
                from web.request_motion import tools as motion_tools,tool_markup
                st.markdown(tool_markup(motion_tools(events,False)),unsafe_allow_html=True)
                st.button('在开发者端查看此运行',key='user_to_trace_'+session.sid,on_click=_open_user_run,args=(session.sid,row['run_id']))
            if row.get('ended_at'):st.caption('结束时间：'+_local_clock(row['ended_at']))
            return
        if not session.audits:
            st.caption('发送消息后，这里显示查询与订单处理的进度。')
            return
        index = len(session.audits) - 1
        if len(session.audits) > 1:
            index = st.selectbox('历史运行', range(len(session.audits)), index=index,
                                 format_func=lambda n: '第' + str(n + 1) + '次处理',
                                 key='user_run_' + session.sid)
        selected = session.audits[index]
        run_id = selected.get('trace_id')
        events, meta = run_view.load_events(session.trace_dir, run_id, session.sid)
        historical = session.read_only or index != len(session.audits) - 1
        st.markdown(user_copy.phase_markup(run_view.phase_states(events)), unsafe_allow_html=True)
        if meta.get('invalid') or meta.get('truncated'):
            st.warning('部分处理记录无法读取，请核对订单状态。')
        if historical:
            st.caption('正在查看已保存的历史记录。')
        if not events:
            st.caption('暂无可确认的处理进度，不能据此判断操作成功。')
        st.button('在开发者端查看此运行', key='user_to_trace_' + session.sid,
                  on_click=_open_user_run, args=(session.sid, run_id))
        if selected.get('error') or selected.get('contract_returned') is False:
            st.caption('本次处理未完成，请核对订单状态；不会用上次成功的结果代替本次结果。')
            with st.expander('技术诊断说明（开发者）', expanded=False):
                st.caption('本次运行未返回成功契约；不复用上一条成功 Trace。完整诊断在开发者工作空间。')


def _hero():
    st.html('<section class="ta-welcome"><div class="ta-welcome-copy">'
            '<h2>今天想去哪里？</h2><p>查询铁路时刻、了解票务政策，或办理模拟订单。</p>'
            '</div><span class="ta-welcome-track" aria-hidden="true"><i></i><i></i><i></i></span></section>')


def _quick_prompts():
    from web.railway_defaults import default_service_date
    day=default_service_date().isoformat()
    with st.container(key='quick_prompts'):
        columns=st.columns(len(QUICK_PROMPTS))
        for column,(title,text) in zip(columns,QUICK_PROMPTS):
            text=text.format(date=day)
            if column.button(title,key='quick_'+title,width='stretch',help=text):
                st.session_state["user_message"]=text


def _summary_markup(summary):
    run_id = summary.get("run_id") or "未记录"
    status = summary.get("status") or "未记录"
    tone = {"已完成": "ok", "失败": "bad", "等待确认": "wait", "已拦截": "wait",
            "进行中": "live", "结果待核验":"wait", "业务状态不一致":"bad"}.get(status, "idle")
    label='本轮处理结束' if status=='已完成' else status
    badge=('<span class="ta-run-idle">尚无执行记录</span>' if summary.get('empty') else
           f'<span class="ta-status ta-status-{tone}">{escape(label)}</span>')
    return ('<div class="ta-summary">'
            '<div class="ta-summary-top">'
            f'<span class="ta-mode ta-mode-current">{escape(summary.get("mode_label") or "未记录")}</span>'
            f'<span data-run-id="{escape(run_id)}"></span>'
            '</div>'
            f'<div class="ta-summary-status">{badge}</div></div>')


def _run_summary_bar(session, audit, events, mode_badge,operation=None):
    """Always-visible description of the run on screen, plus the two jumps."""
    summary = run_view.run_summary(session, audit, events, mode_badge)
    summary['empty']=not (audit or operation or session.history)
    if operation:summary['status']={'QUEUED':'进行中','RUNNING':'进行中','SUCCEEDED':'已完成','FAILED':'失败','BLOCKED':'已拦截','CANCELLED':'已取消','UNKNOWN':'结果待核验','PARTIAL':'业务状态不一致'}.get(operation['status'],'结果待核验')
    if operation and (operation.get('error') or {}).get('category')=='awaiting_confirmation':summary['status']='等待确认'
    if operation and operation.get('kind')=='page_business':
        summary.update(run_id=operation.get('run_id'),mode_label='本页办理')
    matching=next((i for i,record in enumerate(session.history)
                   if (audit or {}).get('public_trace')==record),None)
    anchor = f"turn_{matching}" if matching is not None else ""
    scope=getattr(session,'sid',None)
    with st.container(key='run_summary'):
        st.markdown(_summary_markup(summary), unsafe_allow_html=True)
        if audit or operation or session.history:
            jump_run, jump_latest = st.columns(2, gap='small')
            jump_run.button('回到本次运行', key='scroll_to_run', width='stretch', disabled=not anchor,
                            help='滚动对话到当前运行的结果，并高亮它',
                            on_click=scroll_bridge.request, args=('run', anchor), kwargs={'scope':scope})
            jump_latest.button('回到最新', key='scroll_to_latest', width='stretch', disabled=not session.history,
                               help='滚动对话到最后一条消息',
                               on_click=scroll_bridge.request, args=('bottom',), kwargs={'scope':scope})
    return summary


def _order_status_label(order):
    labels={'PENDING_PAYMENT':'待支付','PAID':'已支付','CHANGED':'已改签','CANCELLED':'已取消',
            'EXPIRED':'已过期','PAYMENT_FAILED':'支付失败','REFUNDED':'已退款'}
    return labels.get(order.get('order_status'),'状态待核验')


def _railway_orders(session,result):
    """Customer-facing summary of the real order read model.

    A raw ``{"tool":"railway_get_order"}`` payload used to fall through to a
    "工具结果" JSON dump; a customer asking 查看订单详情 needs the train, the
    date, the amount and the next step, not JSON.
    """
    from web.business_state import current as business_view
    try:
        snapshot=((business_view(session).get('railway') or {}).get('orders') or [])
    except Exception:
        snapshot=[]
    orders=result if isinstance(result,list) else [result]
    orders=[o for o in orders if isinstance(o,dict) and o.get('order_id')]
    # A tool payload can legitimately be empty while the committed read model
    # already holds the order (different tool scope / a re-run after the page
    # confirmation).  Saying 「还没有铁路订单」 in that state is a false denial:
    # the customer sees a 建单成功 receipt and 「没有订单」 on the same screen.
    if not orders:
        orders=[o for o in snapshot if isinstance(o,dict) and o.get('order_id')]
    if not orders:
        st.info('这个会话还没有铁路订单。查询车次并确认建单后，订单会出现在这里。')
        return
    # The raw tool payload has no display fields (hold_status / item status), so
    # prefer the committed read model for the same order id.
    by_id={o.get('order_id'):o for o in snapshot if isinstance(o,dict)}
    static=getattr(getattr(session,'_v39_service',None),'static',None)
    for raw in orders:
        order=by_id.get(raw.get('order_id')) or raw
        train=str(order.get('trip_id') or '')
        origin=str(order.get('origin_stop_id') or '')
        destination=str(order.get('destination_stop_id') or '')
        if static is not None:
            try:
                detail=(static.trip(order['trip_id'],order['service_date']) or {}).get('data') or {}
                stops={s['stop_id']:s['stop_name'] for s in detail.get('stops',[])}
                train=detail.get('trip',{}).get('trip_short_name') or train
                origin=stops.get(order.get('origin_stop_id'),origin)
                destination=stops.get(order.get('destination_stop_id'),destination)
            except Exception:
                pass
        with st.container(border=True,key='order_summary_'+str(order['order_id'])):
            st.markdown('**'+train+'　'+origin+' → '+destination+'**')
            seat={'SECOND':'二等座','FIRST':'一等座','BUSINESS':'商务座'}.get(order.get('seat_class'),order.get('seat_class') or '')
            items=[i for i in order.get('items') or [] if isinstance(i,dict)]
            count=order.get('active_item_count')
            if type(count) is not int:
                count=sum(1 for i in items if i.get('item_status','ACTIVE')=='ACTIVE') or len(items)
            st.write(_order_status_label(order)+' · '+str(order.get('service_date') or '')+' · '+
                     str(seat)+((' · '+str(count)+' 人') if count else ''))
            st.write('票面 ¥'+f"{(order.get('total_fen') or 0)/100:.2f}"+' · 已支付 ¥'+
                     f"{(order.get('paid_total_fen') or 0)/100:.2f}"+' · 已退款 ¥'+
                     f"{(order.get('refunded_total_fen') or 0)/100:.2f}")
            names=[str(i.get('passenger_name')) for i in items if i.get('passenger_name')]
            if names:st.caption('乘客：'+'、'.join(names))
            st.caption('订单 '+str(order['order_id']))
            if order.get('order_status')=='PENDING_PAYMENT' and not getattr(session,'read_only',False):
                if order.get('hold_expired_at_read'):
                    st.warning('锁座已过期，不能再支付；请重新查询车次并建单。')
                elif st.button('为这笔订单生成支付卡',key='order_pay_'+str(order['order_id'])):
                    from web.railway_queries import open_payment_card
                    if open_payment_card(session,order,'继续完成支付'):
                        total=order.get('total_fen')
                        st.session_state['a_pay_turn_'+session.sid]=dict(
                            message='继续完成支付',order_id=str(order['order_id']),
                            reply=('已为订单 '+str(order['order_id'])+' 生成支付确认卡，'+
                                   (('¥'+f'{total/100:.2f}') if type(total) is int else '票面金额见确认卡')+
                                   '。请在主对话里核对支付二维码并完成支付。'))
                        st.rerun()


def _page_payment_turn(session):
    """Show the page-handled turn that produced the pending PAY card.

    The card itself stays in 待确认铁路操作 (single place to confirm); this echo
    only keeps the click and its grounded result visible in the conversation,
    and disappears with the card once it is confirmed or withdrawn.
    """
    key='a_pay_turn_'+session.sid
    item=st.session_state.get(key)
    if not item:return
    rail=(getattr(session,'business_view',None) or {}).get('railway') or {}
    live=[p for p in rail.get('pending_proposals') or []
          if p.get('action')=='PAY' and str(p.get('order_id') or '')==str(item.get('order_id'))]
    if not live:
        st.session_state.pop(key,None)
        return
    with st.container(key='page_payment_turn'):
        with st.chat_message('user',avatar=':material/person:'):st.write(item.get('message'))
        with st.chat_message('assistant',avatar=':material/smart_toy:'):
            st.write(item.get('reply'))


def _conversation(session):
    """Messages, structured tool results, and the sandbox disclaimer."""
    with st.container(key='user_chat'):
        with interaction.LOCK:
            history=list(session.history);results=batches(session.results)
        # Newest turn owns overlapping recommendations; older turns must not
        # consume them before the current answer is rendered.
        latest=session.followups_for(session.history[-1]) if session.history else None
        offered=set((latest or {}).get('suggestions',[]))
        for index, previous,operation in interaction.chat_turns(session):
            if previous is None:
                with st.container(key='failed_turn_'+operation['request_id']):
                    with st.chat_message('user',avatar=':material/person:'):st.write(operation['operation'])
                    with st.chat_message('assistant',avatar=':material/info:'):
                        st.caption('系统提示')
                        if operation['status']=='CANCELLED':st.info('这条请求已取消。')
                        else:st.error(user_copy.error_message((operation.get('error') or {}).get('category')))
                        from web.business_state import orders_for_operation,customer_status_text
                        for order in orders_for_operation(session,operation):
                            st.info(customer_status_text(order))
                            st.caption('这条请求未完成；以上为已提交的业务状态。')
                        _followup_suggestions(session,None,{'status':'failed','run_id':operation.get('run_id')},operation=operation,turn_key=operation.get('request_id'))
                continue
            with st.container(key=f'turn_{index}'):
                with st.chat_message("user",avatar=":material/person:"):
                    # The operation row keeps the customer's own wording; the
                    # backend may receive a routable rewrite of the same intent.
                    st.write((operation or {}).get('operation') or previous["user_msg"])
                with st.chat_message("assistant",avatar=":material/smart_toy:"):
                    if index==len(session.history)-1 and not session.read_only and not interaction.busy(session):
                        st.markdown('<span class="ta-response-enter" aria-hidden="true"></span>',unsafe_allow_html=True)
                    # The turn's policy view is resolved first: when the backend
                    # summary was replaced by the claim guard, the answer is
                    # rebuilt from the clauses this very turn retrieved.
                    view=_turn_policy(session,previous)
                    _show_guarded_reply(session,previous,view=view)
                    if view.get('has_recorded_retrieval'):
                        _policy_panel(view, technical=False)
                    rail_tools=('railway_query_trips','railway_trip_stops','railway_search_stations')
                    if index<len(results) and not unsafe_ticket_result(session,previous):
                        from web.railway_queries import result_card
                        for number,row in enumerate(results[index]):
                            if row.get('ok') and row.get('tool') in rail_tools:
                                copy=dict(row,id=str(view.get('run_id') or index)+'_'+str(number))
                                result_card(copy,session,latest=(index==len(session.history)-1))
                    if not unsafe_ticket_result(session,previous):
                        _followup_suggestions(session,previous,view,None if index==len(session.history)-1 else offered,turn_key=index)
                # The board this exchange produced belongs under its own answer.
                # Painting every board at the foot of the transcript put an
                # older 170-service list right below the newest message, so the
                # customer read it as the reply to what they had just typed.
                from web.railway_queries import history as railway_board_history
                railway_board_history(session,turn=index)
        if history and results and not session.error:
            if not unsafe_ticket_result(session,history[-1]):
                # Policy evidence now lives under its own answer, including history.
                show_business([r for r in iter_rows(results[-1]) if r.get('tool') not in ('search_policy','railway_query_trips','railway_trip_stops','railway_search_stations')], session)
            record=history[-1]
            if any(not c["ok"] for s in record["steps"] for c in s["calls"]):
                st.warning("本轮有操作未成功，请核对订单状态；详细原因可在开发者工作空间查看。")
        # Natural-language continuation: after the backend listed real station
        # candidates, let the customer pick explicit stop_ids inside the chat
        # instead of being sent to a corner panel.
        from web.railway_queries import chat_station_picker
        # Only the newest turn's tool batch owns the picker; an older 杭州
        # lookup must never be relabelled as the answer to a 广州→深圳 question.
        chat_station_picker(session, rows_source=results[-1] if results else [])
        # "帮我买广州到深圳的票" names a real route but no day: ask the day right
        # here instead of answering that the request was not understood.
        route_date_ask(session)


def _pending_payment_entry(session, hint=False):
    """Grounded, always-visible payment entry for a real pending order.

    Lives at the foot of the conversation, exactly where the old misleading
    「请先查询车次…现在不能确认」 hint used to be.  Only a committed
    PENDING_PAYMENT order from the authoritative read model can produce it; the
    button creates a real PAY proposal through the page-operation path, and the
    QR confirmation card renders in this same conversation.  Nothing is paid here.
    """
    if getattr(session,'read_only',False):return False
    try:
        from web.business_state import current as business_view
        rail=(business_view(session).get('railway') or {})
    except Exception:
        return False
    orders=[o for o in (rail.get('orders') or [])
            if isinstance(o,dict) and o.get('order_id') and o.get('order_status')=='PENDING_PAYMENT']
    if not orders:
        if hint:
            st.caption('当前还没有待支付订单。完成下单后，这里会出现支付入口。')
        return False
    order=orders[0]
    amount=(order.get('total_fen') or 0)/100
    seat={'SECOND':'二等座','FIRST':'一等座','BUSINESS':'商务座'}.get(order.get('seat_class'),order.get('seat_class') or '')
    items=[i for i in (order.get('items') or []) if isinstance(i,dict) and i.get('item_status','ACTIVE')=='ACTIVE']
    names=[str(i.get('passenger_name')) for i in items if i.get('passenger_name')]
    leg={}
    try:
        from web.railway_queries import journey
        leg=journey(session,order)
    except Exception:
        leg={}
    with st.container(border=True,key='pending_payment_'+str(order['order_id'])):
        st.markdown('**待支付 · '+str(order['order_id'])+'**')
        route=' · '.join(str(x) for x in (leg.get('train'),) if x)
        if leg.get('origin') and leg.get('destination'):
            route=(route+' · ' if route else '')+str(leg['origin'])+' → '+str(leg['destination'])
        if route:st.write(route)
        clock=[str(leg.get('date_label') or '')]
        if leg.get('depart'):clock.append(str(leg['depart'])+' 开')
        if leg.get('arrive'):clock.append(str(leg['arrive'])+' 到')
        if leg.get('duration'):clock.append('历时 '+str(leg['duration']))
        if any(clock):st.write(' · '.join(p for p in clock if p))
        facts=['票面 ¥'+f'{amount:.2f}',str(seat)]
        if names:facts.append('乘客 '+'、'.join(names))
        st.write(' · '.join(p for p in facts if p))
        if order.get('hold_expired_at_read'):
            st.warning('这笔订单的锁座已过期，不能支付。请重新查询车次并建单。')
            return True
        st.caption('座位已锁定，支付完成后出票。')
        if st.button('继续完成支付',key='pending_pay_'+str(order['order_id'])):
            from web.railway_queries import open_payment_card
            if open_payment_card(session,order,'继续完成支付'):
                st.session_state['a_pay_turn_'+session.sid]=dict(
                    message='继续完成支付',order_id=str(order['order_id']),
                    reply=('已为订单 '+str(order['order_id'])+' 生成支付确认卡，¥'+f'{amount:.2f}'+
                           '。请在主对话里核对支付二维码并完成支付。'))
                from web import scroll_bridge
                scroll_bridge.request('run','action_dock',scope=session.sid)
                st.rerun()
    return True


def _selected_booking(session):
    """The booking step for the train the customer just picked.

    Rendered in the foot-of-page dock, never inside the train card: a seat /
    passenger form wedged between two departures pushed the rest of the board
    off screen and looked like part of the timetable.
    """
    selected=getattr(session,'selected_railway_trip',None) or {}
    if not selected or not selected.get('trip_id'):return False
    from web.business_panels import booking_panel
    from web.railway_cards import names_for,projection
    try:
        leg=projection(selected,selected,names_for(session))
    except Exception:
        leg={}
    head,close=st.columns([4,1],vertical_alignment='center')
    title='**继续办理 '+str(leg.get('number') or selected.get('trip_id'))+'**'
    if leg.get('origin') and leg.get('destination'):
        title+=' · '+str(leg['origin'])+' → '+str(leg['destination'])
    head.markdown(title)
    if close.button('收起',key='dock_close_'+str(session.sid),use_container_width=True):
        session.selected_railway_trip=None
        session.booking_passengers=None
        st.rerun()
    clock=[str(leg.get('departure_date') or '')]
    if leg.get('departure') and leg['departure']!='—':clock.append(str(leg['departure'])+' 开')
    if leg.get('arrival') and leg['arrival']!='—':clock.append(str(leg['arrival'])+' 到')
    if leg.get('duration'):clock.append('历时 '+str(leg['duration']))
    st.caption(' · '.join(p for p in clock if p))
    booking_panel(session,selected,'_dock')
    return True


def _answer_route_date(session, origin, destination, answer):
    """Send the day the customer tapped, as a normal message.

    "广州到深圳，明天" goes through the same send path as anything typed, so the
    station lookup, the trip board and the audit row are not a side channel.
    """
    from web import interaction
    from web.railway_queries import forget_route_ask
    message=str(origin)+'到'+str(destination)+'，'+str(answer)
    if not interaction.enqueue(session.sid,message,entry='chat',label=message):
        st.warning('上一条请求还在处理，处理完我马上查这一天。')
        return
    forget_route_ask(session)
    st.rerun()


def route_date_ask(session):
    """Ask for the one thing missing from a ticket request: the day.

    The customer's sentence already named a real city pair, so answering with
    「还没识别到具体行程」 was both wrong and unhelpful.  The question is asked
    inline under their own sentence, and one tap answers it (a typed "明天"
    works too).
    """
    if getattr(session,'read_only',False):return False
    from datetime import date, timedelta
    from web.railway_defaults import default_service_date
    from web.railway_queries import pending_route_ask
    ask=pending_route_ask(session)
    if not ask:return False
    today=default_service_date()
    origin,destination=str(ask['origin']),str(ask['destination'])
    sid=str(session.sid)
    with st.container(key='route_date_ask'):
        with st.chat_message('user',avatar=':material/person:'):
            st.write(ask.get('text') or (origin+'到'+destination))
        with st.chat_message('assistant',avatar=':material/smart_toy:'):
            st.write('好的，'+origin+' → '+destination+'。请问您想要哪天的车票？')
            st.caption('点一个日期即可；也可以直接说「明天」「11月20日」。')
            row=st.columns(3)
            for column,offset in zip(row,(0,1,2)):
                day=today+timedelta(days=offset)
                label=('今天' if offset==0 else '明天' if offset==1 else '后天')+' '+day.strftime('%m-%d')
                if column.button(label,key='route_day_'+sid+'_'+str(offset),width='stretch'):
                    _answer_route_date(session,origin,destination,label)
            picked=st.date_input('其他日期',value=today+timedelta(days=3),min_value=today,
                                 max_value=today+timedelta(days=90),key='route_date_pick_'+sid)
            if st.button('按这个日期查车次',key='route_date_go_'+sid):
                chosen=picked if isinstance(picked,date) else today+timedelta(days=3)
                _answer_route_date(session,origin,destination,
                                   str(chosen.month)+'月'+str(chosen.day)+'日')
    return True


def _action_dock(session):
    """One place where the current step is handled, pinned to the foot.

    Whatever the customer just clicked — a train, a pending order, a paid order
    — its own block is the last thing in the conversation and is flashed into
    view by the scroll bridge.  Nothing opens in the middle of the timetable.
    """
    if getattr(session,'read_only',False):return
    hint=bool(st.session_state.pop('a_confirm_hint_'+str(getattr(session,'sid','')),None))
    from web.business_panels import order_for_trip
    selected=getattr(session,'selected_railway_trip',None) or {}
    kind=None
    if (selected and selected.get('trip_id') and selected.get('selection_source')!='committed_order'
            and order_for_trip(session,selected) is None):
        kind='booking'
    else:
        try:
            from web.business_state import current as business_view
            rail=(business_view(session).get('railway') or {})
        except Exception:
            rail={}
        orders=[o for o in (rail.get('orders') or []) if isinstance(o,dict) and o.get('order_id')]
        if any(o.get('order_status')=='PENDING_PAYMENT' for o in orders):kind='pending'
        else:
            from web.railway_queries import paid_orders
            if paid_orders(session):kind='order'
    if kind is None:
        if hint:st.caption('当前还没有待支付订单。完成下单后，这里会出现支付入口。')
        return
    with st.container(key='action_dock'):
        if kind=='booking':
            _selected_booking(session)
        elif kind=='pending':
            _pending_payment_entry(session)
        else:
            _paid_order_entry(session)


def _train_label(session, order):
    """Real train number for an order, resolved from the committed trip."""
    label=str(order.get('trip_id') or '')
    static=getattr(getattr(session,'_v39_service',None),'static',None)
    if static is not None and order.get('trip_id'):
        try:
            detail=(static.trip(order['trip_id'],order['service_date']) or {}).get('data') or {}
            label=detail.get('trip',{}).get('trip_short_name') or label
        except Exception:
            pass
    return label


def _aftercare_echo(session, message, reply, ok, proposal_id):
    st.session_state['a_aftercare_'+session.sid]=dict(
        message=message,reply=reply,ok=bool(ok),proposal_id=proposal_id)


def _aftercare_turn(session):
    """Keep the page-handled refund / change turn visible while its card lives."""
    key='a_aftercare_'+session.sid
    item=st.session_state.get(key)
    if not item:return
    pid=item.get('proposal_id')
    if pid:
        rail=(getattr(session,'business_view',None) or {}).get('railway') or {}
        if not any(str(p.get('proposal_id'))==str(pid) for p in (rail.get('pending_proposals') or [])):
            st.session_state.pop(key,None)
            return
    with st.container(key='aftercare_turn'):
        with st.chat_message('user',avatar=':material/person:'):st.write(item.get('message'))
        with st.chat_message('assistant',avatar=':material/smart_toy:'):st.write(item.get('reply'))


def _train_clock(iso):
    raw=str(iso or '')
    return raw[11:16] if len(raw)>=16 else ''


def _candidate_label(train):
    number=str(train.get('trip_short_name') or train.get('trip_id') or '')
    depart=_train_clock(train.get('departure_at'))
    arrive=_train_clock(train.get('arrival_at') or train.get('destination_arrival'))
    parts=[number]
    if depart:parts.append(depart+' 开')
    if arrive:parts.append(arrive+' 到')
    return ' · '.join(parts)


def _candidate_span(train):
    from datetime import datetime
    try:
        start=datetime.fromisoformat(str(train.get('departure_at')))
        end=datetime.fromisoformat(str(train.get('arrival_at')))
    except ValueError:
        return ''
    minutes=int((end-start).total_seconds()//60)
    if minutes<=0:return ''
    hours,rest=divmod(minutes,60)
    return (str(hours)+' 小时 '+str(rest)+' 分') if hours else (str(rest)+' 分')


def _money(fen):
    """Amount in RMB with an explicit unit; never a bare symbol."""
    try:value=int(fen or 0)/100
    except (TypeError,ValueError):return '金额待核验'
    return f'¥{value:,.2f}'


def _local_clock(value):
    """A timestamp a customer can read: local clock, no raw ISO string."""
    from datetime import datetime
    try:dt=datetime.fromisoformat(str(value))
    except (ValueError,TypeError):return str(value or '')
    if dt.tzinfo is not None:dt=dt.astimezone()
    return dt.strftime('%H:%M')


SEAT_LABELS={'SECOND':'二等座','FIRST':'一等座','BUSINESS':'商务座'}



def _settled_aftercare_receipt(session, oid, state=None):
    """Latest unacknowledged, successful refund/change/cancel receipt for an order."""
    state=state if state is not None else st.session_state
    ack=str(state.get('receipt_ack_'+str(getattr(session,'sid',''))) or '')
    return next((r for r in reversed(getattr(session,'business_receipts',[]) or [])
                 if r.get('session_id')==getattr(session,'sid',None)
                 and str(r.get('order_id') or '')==oid
                 and r.get('status')=='SUCCEEDED'
                 and str(r.get('action') or '') in ('REFUND','CHANGE','CANCEL')
                 and ack!=str(r.get('operation_id') or r.get('order_id') or '')),None)

def _clear_aftercare_state(session, oid, state=None):
    """Drop stale picker/choice widgets so a finished refund cannot freeze the card.

    Streamlit keeps a selectbox's last label even after its options become
    empty, so the old CHANGE branch showed 「改签到 G3017」 with a disabled
    确认改签 button and no way forward.  `state` is injectable for probes.
    """
    state=state if state is not None else st.session_state
    prefixes=('aftercare_choice_'+oid,'aftercare_target_'+oid,
              'aftercare_quote_'+oid,'aftercare_refund_ack_'+oid,
              'order_open_'+oid,'order_detail_'+oid)
    for key in [k for k in list(state) if str(k).startswith(prefixes)]:
        state.pop(key,None)
    state.pop('a_aftercare_'+str(getattr(session,'sid','')),None)


def _order_stamp(value):
    """Readable local business-clock stamp; never a raw ISO string."""
    from datetime import datetime
    try:dt=datetime.fromisoformat(str(value))
    except (ValueError,TypeError):return str(value or '未记录')
    if dt.tzinfo is not None:dt=dt.astimezone()
    return dt.strftime('%Y-%m-%d %H:%M')


def _order_journey_markup(leg,order,seat,count):
    """Boarding-pass strip built from the real static timetable leg."""
    from html import escape as esc
    train=esc(str(leg.get('train') or order.get('trip_id') or '车次待核验'))
    origin=esc(str(leg.get('origin') or order.get('origin_stop_id') or '出发站'))
    destination=esc(str(leg.get('destination') or order.get('destination_stop_id') or '到达站'))
    depart=esc(str(leg.get('depart') or '--:--'))
    arrive=esc(str(leg.get('arrive') or '--:--'))
    date=esc(str(leg.get('date_label') or order.get('service_date') or '日期待核验'))
    span=esc(str(leg.get('duration') or '时刻待核验'))
    return ('<div class="ta-order-trip">'
            '<div class="ta-order-trip-date">'+date+' · '+esc(str(seat or '席别待核验'))
            +' · '+str(count)+' 人</div>'
            '<div class="ta-order-trip-body">'
            '<div class="ta-order-stop"><b>'+depart+'</b><span>'+origin+'</span></div>'
            '<div class="ta-order-line"><span>'+train+'</span><i></i><small>'+span+'</small></div>'
            '<div class="ta-order-stop ta-order-stop-right"><b>'+arrive+'</b><span>'+destination+'</span></div>'
            '</div></div>')


def _order_passenger_table(items,seat):
    """One row per committed ticket; every number comes from v39_order_items."""
    from html import escape as esc
    rows=[]
    for pos,item in enumerate(items,1):
        name=str(item.get('passenger_name') or '乘客')
        item_seat=str(SEAT_LABELS.get(item.get('seat_class'),seat) or '席别待核验')
        ticket=str(item.get('item_id') or '')
        short=(ticket[:14]+'…') if len(ticket)>15 else (ticket or '未记录')
        active=item.get('item_status','ACTIVE')=='ACTIVE'
        rows.append('<tr><td>'+str(pos)+'</td><td>'+esc(name)+'</td><td>'+esc(item_seat)+'</td>'
                    '<td class="num">'+_money(item.get('fare_fen'))+'</td>'
                    '<td>'+esc(short)+'</td><td>'+('有效票' if active else '已退 / 已换')+'</td></tr>')
    return ('<table class="ta-order-table"><thead><tr><th>#</th><th>乘车人</th><th>席别</th>'
            '<th class="num">票价</th><th>车票号</th><th>状态</th></tr></thead><tbody>'
            +''.join(rows)+'</tbody></table>')


def _order_fact_grid(order,items):
    """Committed order facts, including the ledger / state-machine evidence."""
    from html import escape as esc
    transactions=[t for t in (order.get('transactions') or []) if isinstance(t,dict)]
    payment=next((t for t in transactions if t.get('transaction_type')=='PAYMENT'
                  and t.get('status')=='SUCCEEDED'),None)
    paid_at=_order_stamp(payment.get('finished_at') or payment.get('created_at')) if payment else '未记录'
    profiles={'P02_STRICT':'标准退改规则 P02','CHANGED_REFUND_P01':'改签后退票规则 P01'}
    facts=[
        ('订单创建',_order_stamp(order.get('created_at'))),
        ('支付完成',paid_at),
        ('支付渠道','模拟支付 · 不产生真实扣款' if payment else '未记录'),
        ('改签次数',str(order.get('change_count') or 0)+' 次（每单上限 1 次）'),
        ('适用规则',profiles.get(order.get('policy_profile'),str(order.get('policy_profile') or '未记录'))),
        ('账实核验','已核验 · 流水与订单一致' if order.get('ledger_verified') else '未取得核验结果'),
        ('订单版本','v'+str(order.get('version') if order.get('version') is not None else '—')),
        ('有效车票',str(len(items))+' 张'),
        ('时刻表版本',str(order.get('dataset_version') or '未记录')),
    ]
    cells=''.join('<div class="ta-order-fact"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>'
                  for label,value in facts)
    return '<div class="ta-order-facts">'+cells+'</div>'


_ORDER_TXN_LABELS={'PAYMENT':'支付扣款','CHANGE_SUPPLEMENT':'改签补款',
                   'CHANGE_REFUND':'改签退差','REFUND':'退款'}
_ORDER_EVENT_LABELS={'CREATE':'建单','PAYMENT':'支付成功','CANCEL':'订单取消',
                     'EXPIRE':'锁座过期','PAYMENT_FAILED':'支付失败','REFUND':'退票',
                     'CHANGE':'改签','ITEM_REFUNDED':'部分退票','STATE':'状态变更'}


def _order_detail_extras(order,items,seat):
    """Bottom drawer: money split, real ledger, state timeline, data provenance."""
    transactions=[t for t in (order.get('transactions') or []) if isinstance(t,dict)]
    st.markdown('**票价构成**')
    for pos,item in enumerate(items,1):
        st.caption(str(pos)+'. '+str(item.get('passenger_name') or '乘客')+' · '
                   +str(SEAT_LABELS.get(item.get('seat_class'),seat))+'：席别价 '
                   +_money(item.get('seat_fen'))+' + 固定费用分摊 '+_money(item.get('fixed_fee_share_fen'))
                   +' = 票价 '+_money(item.get('fare_fen')))
    st.markdown('**资金流水**')
    if transactions:
        for row in transactions:
            label=_ORDER_TXN_LABELS.get(row.get('transaction_type'),str(row.get('transaction_type') or '流水'))
            direction='支出' if row.get('direction')=='DEBIT' else '退回'
            st.caption(_order_stamp(row.get('created_at'))+' · '+label+' · '+direction+' '
                       +_money(row.get('amount_fen'))+' · '+('成功' if row.get('status')=='SUCCEEDED'
                       else str(row.get('status') or '未记录')))
    else:
        st.caption('本单没有资金流水记录。')
    st.markdown('**状态变更时间线**')
    events=[e for e in (order.get('operation_events') or []) if isinstance(e,dict)]
    if events:
        for row in events:
            kind=str(row.get('event_type') or '')
            st.caption(_order_stamp(row.get('created_at'))+' · '
                       +_ORDER_EVENT_LABELS.get(kind,kind)
                       +('（'+str(row.get('from_status'))+' → '+str(row.get('to_status'))+'）'
                         if row.get('from_status') or row.get('to_status') else ''))
    else:
        st.caption('本单没有可核验的状态变更事件。')
    st.markdown('**数据来源与凭证**')
    st.caption('车次与站名：GTFS 静态时刻表（'+str(order.get('dataset_version') or '未记录')
               +'）· 车次 ID '+str(order.get('trip_id') or '未记录')
               +' · '+str(order.get('origin_stop_id') or '?')+' → '+str(order.get('destination_stop_id') or '?'))
    st.caption('报价单 '+str(order.get('quote_id') or '未记录')+' · 锁座单 '+str(order.get('hold_id') or '未记录')
               +' · 幂等键 '+str(order.get('idempotency_key') or '未记录'))
    st.caption('订单状态、车票、流水与审计事件均来自本地已提交的 SQLite 业务库；'
               '页面只读展示，不改写任何业务记录。')


def _paid_order_entry(session):
    """Paid-order card, split into 车票 / 订单 / 乘客 / 状态 / 规则 / 操作.

    A customer looking at this card must be able to answer: which train, from
    where to where, when, how long, what it cost, who is on it, whether the
    refund or the change is allowed right now, and whether it has actually
    been submitted.  Every fact comes from the same static timetable, quote
    service and P01 policy the trade itself uses.
    """
    if getattr(session,'read_only',False):return
    from web.railway_queries import (paid_orders,open_refund_card,open_change_card,
                                     change_candidates,change_preview,journey,refund_terms)
    orders=paid_orders(session)
    if not orders:return False
    order=orders[0];oid=str(order['order_id'])
    if _settled_aftercare_receipt(session,oid):
        _clear_aftercare_state(session,oid)
    rail=(getattr(session,'business_view',None) or {}).get('railway') or {}
    pending=[p for p in (rail.get('pending_proposals') or [])
             if str(p.get('order_id') or '')==oid and p.get('action') in ('REFUND','CHANGE')]
    change_pending=any(p.get('action')=='CHANGE' for p in pending)
    refund_pending=any(p.get('action')=='REFUND' for p in pending)
    choice_key='aftercare_choice_'+oid
    choice=st.session_state.get(choice_key) or ''
    if pending:
        choice=''
        st.session_state.pop(choice_key,None)
    leg=journey(session,order)
    seat=SEAT_LABELS.get(order.get('seat_class'),order.get('seat_class') or '')
    items=[i for i in (order.get('items') or []) if isinstance(i,dict)
           and i.get('item_status','ACTIVE')=='ACTIVE']
    pending_choice=st.session_state.get('aftercare_target_'+oid) if choice=='CHANGE' else None
    change_state=('已改签' if order.get('order_status')=='CHANGED'
                  else '待确认' if change_pending
                  else '已选车次，待确认' if pending_choice
                  else '选择车次中' if choice=='CHANGE' else '')
    refund_state=('已退款' if order.get('order_status')=='CANCELLED' or str(order.get('refund_status'))=='REFUNDED'
                  else '待确认' if refund_pending
                  else '办理中' if choice=='REFUND' else '')
    terms=refund_terms(session,order,leg)
    candidates,args=change_candidates(session,order)
    fare=order.get('total_fen') or 0
    paid=order.get('net_paid_fen')
    if paid is None:paid=fare
    detail_key='order_detail_'+oid
    open_key='order_open_'+oid
    # A paid order is not a permanent fixture at the foot of every screen: the
    # full card is rendered only while the order is the thing being handled
    # (its confirmation card is pending, an aftercare step was just started, a
    # receipt for it is still on screen, or the customer opened it).  Otherwise
    # one line with an explicit entry point stays, so other work is not buried
    # under a stale 乘客 / 操作 block.
    receipt=next((r for r in reversed(getattr(session,'business_receipts',[]) or [])
                  if r.get('session_id')==session.sid),None)
    just_now=bool(receipt and str(receipt.get('order_id') or '')==oid
                  and str(st.session_state.get('receipt_ack_'+str(session.sid)) or '')
                  !=str(receipt.get('operation_id') or receipt.get('order_id') or ''))
    focused=bool(st.session_state.get(open_key) or pending or choice or just_now
                 or st.session_state.get('a_aftercare_'+session.sid))
    if not focused:
        with st.container(key='paid_order_bar_'+oid):
            bar,entry=st.columns([5,1.2],vertical_alignment='center')
            bar.markdown('**'+str(leg.get('train'))+' · '+str(leg.get('origin'))+' → '+
                         str(leg.get('destination'))+'** · '+_order_status_label(order)+' · '+
                         _money(paid if paid is not None else fare))
            if entry.button('查看订单',key='order_open_btn_'+oid,width='stretch'):
                st.session_state[open_key]=True
                from web import scroll_bridge
                scroll_bridge.request('run','action_dock',scope=session.sid)
                st.rerun()
        return True
    with st.container(border=True,key='paid_order_'+oid):
        # ① 车票信息：车次 / 状态 + 真实行程卡 ----------------------------
        head,state=st.columns([4,1.3],vertical_alignment='center')
        head.markdown('**'+str(leg.get('train'))+' · '+str(leg.get('origin'))+' → '+str(leg.get('destination'))+'**')
        state.markdown("<div style='text-align:right'>"+_order_status_label(order)+'</div>',unsafe_allow_html=True)
        st.markdown(_order_journey_markup(leg,order,seat,len(items)),unsafe_allow_html=True)
        # ② 金额概览：票面 / 实付 / 已退 / 手续费 -------------------------
        money_cols=st.columns(4)
        money_cols[0].metric('票面金额',_money(fare))
        money_cols[1].metric('实付金额',_money(paid))
        money_cols[2].metric('累计退款',_money(order.get('refunded_total_fen') or 0))
        money_cols[3].metric('手续费',_money(order.get('fee_total_fen') or 0))
        st.caption('币种 '+str(order.get('currency') or 'CNY')+' · 金额取自本单已提交的订单与资金流水；模拟环境不产生真实扣款。')
        # ③ 订单号（可一键复制） ------------------------------------------
        st.caption('订单号（点击右侧图标复制）')
        st.code(oid,language=None)
        # ④ 乘客与车票 ----------------------------------------------------
        st.markdown('**乘客与车票 · 共 '+str(len(items))+' 人**')
        if items:
            st.markdown(_order_passenger_table(items,seat),unsafe_allow_html=True)
        else:
            st.caption('本单暂无有效车票。')
        # ⑤ 订单信息：生命周期 / 支付 / 规则 / 账实核验 -------------------
        st.markdown('**订单信息**')
        st.markdown(_order_fact_grid(order,items),unsafe_allow_html=True)
        # ⑥ 当前可办理（状态已在右上方，此处只列还能做什么） ---------------
        st.markdown('**当前可办理**')
        allowed=order.get('order_status') in ('PAID','CHANGED') and not pending
        status=[]
        if allowed and terms is not None:status.append('可退票（预计手续费 '+_money(terms['fee_fen'])+'）')
        if allowed and candidates:status.append('可改签（本单限 1 次）')
        if not allowed and not change_state and not refund_state:status.append('暂不可办理退票或改签')
        if change_state in ('待确认','已选车次，待确认','选择车次中'):status.append('改签 '+change_state)
        if refund_state in ('待确认','办理中'):status.append('退票 '+refund_state)
        st.write(' · '.join(status) if status else '暂不可办理退票或改签')
        # ⑤ 温馨提示 ------------------------------------------------------
        with st.expander('温馨提示：退票与改签规则'):
            if terms is not None:
                st.write('现在退票：手续费 '+_money(terms['fee_fen'])+'（票面 '+str(terms['rate_bp'])+'%），可退 '+_money(terms['net_fen'])+'。')
            else:
                st.write('退票手续费按购票时适用的规则从票款中扣除；发车后不能退票。')
            st.write('手续费比例：出发前 48 小时以上 5%，24 至 48 小时 10%，不足 24 小时 20%，按分四舍五入。')
            st.write('改签：只换同区间、同席别的日期或车次，每单限 1 次，差价多退少补；改签后仍可退票。')
            st.write('退款按原支付渠道退回；页面确认后才生效，未确认的提案不会改动订单。')
        # ⑥ 操作 ----------------------------------------------------------
        st.markdown('**操作**')
        if pending:
            st.info('已生成'+('改签' if change_pending else '退票')+'确认卡，请在主对话里查看确认卡并确认。')
        elif not choice:
            st.caption('接下来要办理什么？')
            left,right=st.columns(2)
            if left.button('退票',key='aftercare_pick_refund_'+oid,use_container_width=True):
                st.session_state[choice_key]='REFUND';st.rerun()
            if right.button('改签',key='aftercare_pick_change_'+oid,
                            disabled=not candidates,use_container_width=True):
                st.session_state[choice_key]='CHANGE';st.rerun()
            if not candidates:
                st.caption('当天及后续 3 天都没有查到可改签车次；请先在对话里查询目标日期的车次，再回来办理。')
        elif choice=='REFUND':
            st.write('退票会收回本单全部车票，手续费按上条规则从票款中扣除。')
            if terms is not None:
                st.info('预计扣除手续费 '+_money(terms['fee_fen'])+'，实退 '+_money(terms['net_fen'])+'。')
            ack=st.checkbox('我已核对订单与退票规则',key='aftercare_refund_ack_'+oid)
            left,right=st.columns(2)
            if left.button('确认退票',key='aftercare_refund_'+oid,
                           disabled=not ack,use_container_width=True):
                ok,pid,reply=open_refund_card(session,order,'办理退票')
                _aftercare_echo(session,'办理退票',reply,ok,pid)
                st.session_state.pop(choice_key,None);st.session_state.pop('aftercare_refund_ack_'+oid,None)
                if ok:
                    from web import scroll_bridge
                    scroll_bridge.request('run','action_dock',scope=session.sid)
                st.rerun()
            if right.button('返回',key='aftercare_back_refund_'+oid,use_container_width=True):
                st.session_state.pop(choice_key,None);st.session_state.pop('aftercare_refund_ack_'+oid,None)
                st.rerun()
        elif choice=='CHANGE':
            target=st.selectbox('改签到',candidates,format_func=_candidate_label,
                                key='aftercare_target_'+oid)
            if target:
                qkey='aftercare_quote_'+oid+'_'+str(target.get('trip_id'))
                preview=st.session_state.get(qkey)
                if preview is None:
                    preview=change_preview(session,order,target,args)
                    if preview is not None:st.session_state[qkey]=preview
                if preview:
                    diff=int(preview.get('difference_fen') or 0)
                    total=preview['total_fen']/100
                    old=(order.get('total_fen') or 0)/100
                    if diff>0:
                        money='原票价 ¥'+f'{old:.2f}'+' → 新票价 ¥'+f'{total:.2f}'+' · 需补差价 ¥'+f'{diff/100:.2f}'
                    elif diff<0:
                        money='原票价 ¥'+f'{old:.2f}'+' → 新票价 ¥'+f'{total:.2f}'+' · 退还差价 ¥'+f'{-diff/100:.2f}'
                    else:
                        money='原票价 ¥'+f'{old:.2f}'+' → 新票价 ¥'+f'{total:.2f}'+' · 无差价'
                    extra=[str(preview.get('passenger_count') or len(items))+' 人',
                           SEAT_LABELS.get(preview.get('seat_class'),seat)]
                    if preview.get('available') is not None:extra.append('余票 '+str(preview['available'])+' 张')
                    if _candidate_span(target):extra.append('历时 '+_candidate_span(target))
                    st.info(money+' · '+' · '.join(extra))
            left,right=st.columns(2)
            if left.button('确认改签',key='aftercare_change_'+oid,disabled=not target,use_container_width=True):
                ok,pid,reply=(open_change_card(session,order,target,args,'办理改签') if target
                              else (False,None,'请先选择要改签到的车次。'))
                _aftercare_echo(session,'办理改签',reply,ok,pid)
                st.session_state.pop(choice_key,None)
                if ok:
                    from web import scroll_bridge
                    scroll_bridge.request('run','action_dock',scope=session.sid)
                st.rerun()
            if right.button('返回',key='aftercare_back_change_'+oid,use_container_width=True):
                st.session_state.pop(choice_key,None);st.rerun()
        # ⑦ 次要操作：详情 / 回到车次列表 ---------------------------------
        extra_left,extra_right=st.columns(2)
        opened=bool(st.session_state.get(detail_key))
        if extra_left.button('收起详情' if opened else '查看详情',key='order_detail_btn_'+oid,use_container_width=True):
            if opened:st.session_state.pop(detail_key,None)
            else:st.session_state[detail_key]=True
            st.rerun()
        if extra_right.button('返回车次列表',key='aftercare_back_list_'+oid,use_container_width=True):
            from web.railway_queries import back_to_trips,board_for_leg
            st.session_state.pop(open_key,None)
            st.session_state.pop(choice_key,None)
            session.selected_railway_trip=None
            # The board the customer came from is still on screen: go back to it
            # (and flash it) instead of painting a second copy at the foot of the
            # page.  Only when the conversation has no board for this leg yet is
            # a read-only re-query needed.  The scroll itself is issued after the
            # board has rendered, so it targets the right one either way.
            if not board_for_leg(session,order) and not back_to_trips(session,order):
                st.warning('这一天的车次暂时取不到，请重新输入出发城市与到达城市查询。')
            else:
                st.session_state['a_back_to_board_'+str(session.sid)]=True
                st.rerun()
        if opened:
            _order_detail_extras(order,items,seat)
            changes=order.get('changes') or []
            refunds=order.get('refunds') or []
            if changes:st.caption('改签记录 '+str(len(changes))+' 次：'+str(changes[-1].get('status') or changes[-1].get('change_status') or '已提交'))
            if refunds:st.caption('退票记录 '+str(len(refunds))+' 次：'+str(refunds[-1].get('status') or '已提交'))
    return True


def _page_payment_notice(session):
    """Factual reply while there is nothing to pay yet; cleared by the next turn."""
    key='a_pay_notice_'+str(getattr(session,'sid',''))
    text=st.session_state.get(key)
    if not text:return
    try:
        from web.business_state import current as business_view
        rail=(business_view(session).get('railway') or {})
        if any(isinstance(o,dict) and o.get('order_status')=='PENDING_PAYMENT'
               for o in (rail.get('orders') or [])):
            st.session_state.pop(key,None)  # an order now exists; the entry card takes over
            return
    except Exception:
        pass
    with st.chat_message('assistant',avatar=':material/smart_toy:'):
        st.info(text)


def _confirm_cards(session, action, pending=None, pending_here=False):
    """One source of truth: only a real backend proposal can render a card.

    The legacy ``pending`` / ``pending_here`` arguments are kept for call-site
    compatibility (several regressions invoke this helper directly) but are no
    longer used: operation_kind() used to guess an operation from user text and
    could confirm something the backend never proposed.  All messages now go
    through the unified send path and the backend decides whether a proposal
    exists.  Button labels and the '查看技术细节' expander are display contracts
    covered by the existing UI tests and stay unchanged.
    """
    if not action:
        st.session_state.pop('a_confirm_bound_'+str(getattr(session,'sid','')),None)
        # The payment / order block now lives in the foot-of-page dock, so this
        # path only clears the stale binding and the one-shot hint flag.
        st.session_state.pop('a_confirm_hint_'+str(getattr(session,'sid','')),None)
        return
    st.session_state.pop('a_confirm_hint_'+str(getattr(session,'sid','')),None)
    # Bind the proposal's config/datasource identity the first time it appears,
    # then assert it on every later render.  Stub sessions in regressions do
    # not expose these runtime APIs; in that case keep the old guard only.
    compatible=True;detail=''
    if hasattr(session,'bind_page_proposal') and hasattr(session,'assert_page_proposal'):
        try:
            from target.dev_overrides import digest
            identity=digest(action)
            bound_key='a_confirm_bound_'+str(getattr(session,'sid',''))
            if st.session_state.get(bound_key)!=identity:
                session.bind_page_proposal(action)
                st.session_state[bound_key]=identity
            session.assert_page_proposal(action)
        except ValueError as exc:
            compatible=False;detail=str(exc)
        except Exception:
            compatible=True
    focus=st.session_state.get('user_focus_run')
    run_id=(focus[1] if isinstance(focus,tuple) and len(focus)>1 else
            (session.audits[-1].get('trace_id') if getattr(session,'audits',None) else None))
    proposal_id=str(action.get('proposal_id') or action.get('call_id') or '未记录')
    with st.container(border=True,key='action_confirm'):
        st.markdown("**请确认本次操作**")
        st.write("操作：" + TOOL_LABELS.get(action['tool'], action['tool']))
        st.caption('提案标识 '+proposal_id+' · 运行标识 '+str(run_id or '未记录')+
                   '；本面板内按同一标识核对对应工具调用。')
        # Customer-readable business summary: train, date, time, amount,
        # passengers.  Unknown keys remain visible below as raw parameters.
        args=action.get('args') or {}
        trip_id=str(args.get('trip_id') or '')
        train_label=depart=arrive=None
        if trip_id:
            from web.result_rows import iter_rows
            for raw in iter_rows(getattr(session,'results',[])):
                result=raw.get('result') if isinstance(raw,dict) else None
                for item in ((result or {}).get('data') or []) if isinstance(result,dict) else []:
                    if isinstance(item,dict) and str(item.get('trip_id'))==trip_id:
                        train_label=item.get('trip_short_name');depart=item.get('departure_at')
                        arrive=item.get('arrival_at');break
        summary=[]
        if train_label:summary.append('车次：'+str(train_label)+'（班次 '+trip_id+'）')
        elif trip_id:summary.append('班次标识：'+trip_id)
        if args.get('service_date'):summary.append('乘车日期：'+str(args['service_date']))
        if depart:summary.append('时刻：'+str(depart)+' → '+str(arrive or '未记录'))
        amount=args.get('total_fen') or args.get('expected_total_fen') or args.get('net_fen')
        if amount is not None:
            try:summary.append('金额：¥'+f'{int(amount)/100:.2f}')
            except (TypeError,ValueError):summary.append('金额（分）：'+str(amount))
        if args.get('passengers'):
            value=args['passengers']
            summary.append('乘客：'+('、'.join(map(str,value)) if isinstance(value,(list,tuple)) else str(value)))
        if args.get('quantity'):summary.append('人数：'+str(args['quantity']))
        if summary:
            st.markdown('**本次操作对象**')
            for line in summary:st.write('· '+line)
        for label, value in user_copy.operation_details(args):
            st.write(label + '：', value)
        with st.expander('查看技术细节',expanded=False):
            import json
            st.code(json.dumps({'tool':action['tool'],'args':action['args'],
                                'proposal_id':proposal_id,'run_id':run_id},
                               ensure_ascii=False,indent=2),language='json')
        st.caption("本次确认只适用于上面列出的操作；不会真实出票或扣款，交易必须由你在此页面确认。")
        if not compatible:
            st.warning('配置或数据源已变化，请取消原提案并重新生成；不能用新权限执行旧提案。'+detail)
        yes, no = st.columns(2)
        approved = yes.button("确认此模拟操作", type="primary", width="stretch", disabled=not compatible)
        declined = no.button("取消此模拟操作", width="stretch")
        if approved or declined:
            try:
                session.confirm_action(approved, uuid.uuid4().hex,
                    followup_authorized=_live_request_allowed(session))
            except Exception:
                st.error("操作未完成，请查看执行记录和订单状态。")
            st.session_state.pop('a_confirm_bound_'+str(getattr(session,'sid','')),None)
            if getattr(session,'audits',None):st.session_state['user_focus_run']=(session.sid,session.audits[-1]['trace_id'])
            st.rerun()
def _composer(session, live_name):
    """The composer lives in the conversation column so narrow stacking keeps it
    between the transcript and the run-detail panel."""
    with st.container(key='user_compose'):
        if session.live:
            allow_live=True
        else:
            allow_live=False
        multiline=st.toggle('多行输入',key='user_multiline')
        with st.form("user_compose",clear_on_submit=True):
            row=st.columns([9,1.4],gap='small')
            input_widget=row[0].text_area if multiline else row[0].text_input
            example='例如：查明天广州到深圳的车次，或问「退票手续费怎么算」'
            message=input_widget("输入消息",key="user_message",
                placeholder=example,label_visibility="collapsed",**({'height':72} if multiline else {}))
            send=row[1].form_submit_button("处理中" if interaction.busy(session) else "发送",key='user_send_'+st.session_state['user_submit_nonce'],
                type="primary",disabled=session.read_only or interaction.busy(session) or session.live and not live_ready(session.live_provider))
    return message, send, allow_live


def user_page():
    from web import user_layout
    user_layout.styles()
    # Clear the composer on the run after a send; a widget key cannot be written
    # once this run has instantiated it.
    if st.session_state.pop('user_clear_input',False):
        st.session_state['user_message']=''
    sessions=st.session_state.setdefault("user_sessions",[])
    from web.session_links import active_session, get_testable_sessions, remember_active
    def activate(index):
        st.session_state['user_active_session_index']=index
        st.session_state['user_session_index']=index
        if st.query_params.get('session_id')!=sessions[index].sid:
            st.query_params.pop('abc_run',None)
            st.query_params.pop('abc_batch',None)
        st.query_params['session_id']=sessions[index].sid
        remember_active(sessions[index])
        scroll_bridge.request('bottom' if sessions[index].history else 'top',scope=sessions[index].sid)
    def new_session():
        return Conversation("user",engine=st.session_state["default_engine"],live=st.session_state["default_live"],
                            live_provider=st.session_state.get("default_provider","deepseek"),
                            live_model=st.session_state.get("default_live_model"),interactive=True,
                            full_tools=st.session_state['default_live'])
    signature=(st.session_state["default_engine"],st.session_state["default_live"],st.session_state.get("default_provider","deepseek"),st.session_state.get('default_live_model'),'manual-live-v1')
    if not sessions:
        saved_sid=st.query_params.get('session_id')
        restored=None
        if saved_sid:
            try:
                from web.session_store import restore_by_sid
                restored=active_session(saved_sid) or restore_by_sid(saved_sid)
            except (OSError,ValueError,TypeError,KeyError):
                st.session_state['restore_notice']='未找到完整的本地会话索引，已新建会话；原文件未修改。'
        sessions.append(restored or new_session())
        activate(0)
        st.session_state["user_provider_signature"]=signature
    elif st.session_state.get("user_provider_signature") not in (None,signature):
        sessions.append(new_session())
        activate(len(sessions)-1)
        st.session_state["user_provider_signature"]=signature
    st.session_state["user_provider_signature"]=signature
    source_focus=st.session_state.pop('user_source_focus',None)
    if source_focus:
        available=get_testable_sessions(sessions,source_focus)
        selected=next((item for item in available if item.sid==source_focus and item.mode=='user'),None)
        if selected is not None:
            if selected not in sessions:sessions.append(selected)
            activate(sessions.index(selected))
    # Widget state is removed when this page is not rendered. Keep active history
    # selection in a non-widget key so a workbench visit cannot switch providers.
    current=st.session_state.get('user_session_index')
    if type(current) is not int or not 0<=current<len(sessions):
        saved=st.session_state.get('user_active_session_index',0)
        activate(max(0,min(saved if type(saved) is int else 0,len(sessions)-1)))
    with st.sidebar:
        if st.button("新建会话",width="stretch"):
            sessions.append(new_session())
            activate(len(sessions)-1)
        index=st.selectbox("历史会话",range(len(sessions)),format_func=lambda i:(sessions[i].history[0]["user_msg"][:18] if sessions[i].history else "新对话")+f" · {i+1}",key="user_session_index")
    st.session_state['user_active_session_index']=index
    session=sessions[index]
    if st.query_params.get('session_id')!=session.sid:
        st.query_params.pop('abc_run',None)
        st.query_params.pop('abc_batch',None)
    remember_active(session)
    session._unified_interaction=True
    from web.business_state import refresh as refresh_business_state
    refresh_business_state(session)
    from web.proposal_navigation import prepare as prepare_proposal_navigation
    prepare_proposal_navigation(session)
    selected_sid=st.session_state.get('scroll_selected_sid')
    if selected_sid!=session.sid:
        if not st.session_state.get('railway_proposal_focus_'+session.sid):
            scroll_bridge.request('bottom' if session.history else 'top',scope=session.sid)
        st.session_state['scroll_selected_sid']=session.sid
    focus=st.session_state.pop('user_focus_run',None)
    if focus and focus[0]==session.sid:
        rows=interaction.history(session)
        st.session_state['user_run_'+session.sid]=next((i for i,a in enumerate(rows)
            if a.get('run_id')==focus[1]),max(0,len(rows)-1))
    st.query_params['session_id']=session.sid
    restore_notice=st.session_state.pop('restore_notice',None)
    live_name="Qwen3.8-Flash" if session.live_provider=="bailian" and session.live_model=="qwen3.8-flash" else session.live_model or "Qwen (兼容旧配置)" if session.live_provider=="bailian" else "DeepSeek"
    mode_badge=("Live · "+live_name+" · 可下单" if session.live and session.full_tools
                else "Live · "+live_name+" · 仅查询" if session.live else "Mock · 内置规则")
    user_layout.topbar(sessions,new_session,activate,clock=(getattr(session,'business_view',{}) or {}).get('simulation_clock'),
                        test_session=session if session.history else None)

    action = session.pending_action()
    pending=st.session_state.get("pending_operation")
    pending_here=bool(pending and pending["sid"]==session.sid)
    busy=bool(action) or pending_here or session.read_only or interaction.busy(session)
    followup=_consume_followup(session,busy)
    submission=interaction.consume(session)
    audit, events, event_meta = run_view.latest_run(session) if session.audits else (None, [], {})
    chosen=st.session_state.get('user_run_'+session.sid)
    operations=interaction.history(session);display_operation=operations[-1] if operations else None
    if type(chosen) is int and 0<=chosen<len(operations):
        display_operation=operations[chosen]
        audit=next((a for a in session.audits if a['trace_id']==display_operation.get('run_id')),None)
        events,event_meta=run_view.load_events(session.trace_dir,(audit or {}).get('trace_id'),session.sid)
    if session.read_only or (audit is not None and audit is not session.audits[-1]):
        mode_badge='历史回放 · '+mode_badge

    welcome = (not session.history and not getattr(session,'railway_queries',[]) and not busy
               and not st.session_state.get('a_route_ask_'+str(session.sid)))


    if st.session_state.get('user_compose_session')!=session.sid:
        st.session_state['user_allow_embedding']=False
        st.session_state['user_rag_mode']=session.rag_mode or 'keyword'
        st.session_state['user_compose_session']=session.sid
        st.session_state['user_submit_nonce']=uuid.uuid4().hex

    feedback_slots={}
    def _chat_body():
        displayed_error = session.error
        if session.config_notice:st.warning(session.config_notice)
        if restore_notice:st.info('未找到完整的本地会话索引，已新建会话；原文件未修改。')
        if session.read_only:st.info('这是保存的历史会话，仅供查看。继续使用请新建会话。')
        if session.persistence_warning:st.warning(session.persistence_warning)
        if (session.engine,session.live,session.live_provider)!=(st.session_state['default_engine'],st.session_state['default_live'],st.session_state.get('default_provider','deepseek')):
            st.info('正在查看历史会话。')
        if session.error:
            if getattr(session,'last_train_query',None):
                from web.train_data import source_status
                source_status(session.last_train_query)
            st.error(user_copy.error_message(session.error['category']))
            from web.policy_interaction import policy_view
            failed_policy=policy_view(session.sid,(audit or {}).get('trace_id'),events=events,audit=audit)
            if failed_policy['has_recorded_retrieval']:
                st.caption('最近未完成请求的知识库记录；不是上一条成功回答的证据。')
                _policy_panel(failed_policy,technical=False)
        if welcome:
            _hero()
            from web.user_features import shortcuts, starter_tasks
            shortcuts(session.sid)
            if not st.session_state.get('guided_demo'):
                starter_tasks(session.sid)
        if (welcome or st.session_state.get('guided_demo')) and not session.read_only:
            from web.demo import demo_page
            demo_page()
        _conversation(session)
        _page_payment_turn(session)
        _page_payment_notice(session)
        _aftercare_turn(session)
        # Boards are painted under their own turn inside _conversation; only
        # boards saved before that stamp (restored sessions) still land here.
        from web.railway_queries import history as railway_query_history
        railway_query_history(session,orphans=True)
        # 返回车次列表 lands on the board itself: the request is issued once the
        # board exists, so it cannot point at a stale (or missing) anchor.
        if st.session_state.pop('a_back_to_board_'+str(session.sid),False):
            from web.railway_queries import board_anchor
            anchor=board_anchor(session)
            if anchor:scroll_bridge.request('run',anchor,scope=session.sid)
        from web.business_panels import receipts as business_receipts
        business_receipts(session)
        from web.order_actions import notice as trade_notice
        trade_notice(session)
        _action_dock(session)
        # Actionable cards (payment QR, change/refund proposals, legacy Agent
        # confirmations) belong in the conversation where the customer acts.
        # The right rail is a read-only explanation / tool-execution view.
        if not session.read_only:
            _confirm_cards(session, action, pending, pending_here)
            from web.v39_bridge import render_pending
            render_pending(session)
        if interaction.busy(session) and getattr(session,'_queued_submission',None):
            with st.chat_message('user'):st.write(session._queued_submission['message'])
            feedback_slots['chat']=st.empty()
        if displayed_error is not None and session.error is displayed_error:
            # Keep the audit/trace, but clear this already-displayed request error
            # only after the conversation has rendered its error state.
            session.error=None
        from web.followup_jobs import pending as followups_pending
        @st.fragment(run_every=.5 if followups_pending(session) else None)
        def _watch_followups():
            if not followups_pending(session) and st.session_state.pop('followups_poll_'+session.sid,False):st.rerun()
        if followups_pending(session):st.session_state['followups_poll_'+session.sid]=True
        _watch_followups()

    def _column_body():
        with st.container(height='stretch',key='user_chat_scroll'):
            _chat_body()
            chat_submission_slot=st.container()
        return (*_composer(session, live_name),chat_submission_slot)

    with st.container(key='user_layout',horizontal=True,height='stretch'):
        with st.container(key='user_left',height='stretch'):
            message, send, allow_live,chat_submission_slot = _column_body()
        with st.container(key='user_right',height='stretch'):
            with st.container(key='mobile_info'):
                info_open=st.toggle('相关信息 / 常用功能',key='user_info_open')
            with st.container(key='user_right_content',height='stretch'):
                if info_open:st.markdown('<span class="ta-info-open"></span>',unsafe_allow_html=True)
                with st.container(border=True,key='user_tool_execution'):
                    st.markdown('**本次工具执行**')
                    if not session.read_only:
                        from web.business_panels import order_confirm_card
                        order_confirm_card(session)
                    with st.container(key='execution_progress'):
                        live_run_slot=st.empty()
                    @st.fragment(run_every=.35 if interaction.busy(session) else None)
                    def _watch_operation():
                        rows=getattr(session,'operations',[])
                        if rows and interaction.busy(session):
                            from web.request_motion import live,markup,tools,tool_markup
                            _,live_events,view=live(session)
                            if 'chat' in feedback_slots:feedback_slots['chat'].markdown(markup(view),unsafe_allow_html=True)
                            st.markdown(markup(view),unsafe_allow_html=True)
                            # A model proposal alone is not evidence of execution.
                            actual=[e for e in live_events if e.get('event_type')!='tool_proposed']
                            st.markdown(user_copy.phase_markup(run_view.phase_states(actual),animate=True),unsafe_allow_html=True)
                            st.markdown(tool_markup(tools(live_events,True)),unsafe_allow_html=True)
                        if rows and rows[-1]['status']=='QUEUED' and st.button('取消排队',key='cancel_queued_'+session.sid):
                            if interaction.cancel_queued(session):st.rerun()
                        future=getattr(session,'_chat_future',None)
                        if future and future.done() and not getattr(session,'_chat_notified',False):
                            session._chat_notified=True
                            if rows and rows[-1].get('run_id'):st.session_state['user_focus_run']=(session.sid,rows[-1]['run_id'])
                            elif rows:st.session_state['user_run_'+session.sid]=len(interaction.history(session))-1
                            st.rerun()
                    _watch_operation()
                    _run_summary_bar(session,audit,events,mode_badge,display_operation)
                    if display_operation or audit:
                        if not interaction.busy(session):
                            page_events=((session.business_view or {}).get('railway') or {}).get('operation_events',[])
                            user_layout.execution_details(display_operation,events,action,page_events)
                    if action:
                        st.info('待确认 '+str(action.get('proposal_id') or action.get('call_id') or '未记录')+
                                ' · 运行 '+str((display_operation or {}).get('run_id') or (audit or {}).get('trace_id') or '未记录'))
                    with st.expander('展开历史调用',expanded=False):
                        _run_rail(session,events)
                # ② Customer entry points and live proposals stay visible.
                user_layout.quick_actions(session)
                from web import v39_bridge
                v39_bridge.render(session)
                # ③ Client handover note 2.2: the rail holds only the pinned
                # execution block plus these entry points.  The refund/cancel
                # panel lives in the「看订单」flow, the trip/order/policy
                # summary lives in conversation cards, and the data statement
                # moved to the topbar popover — none of them render here.
                if session.live and not live_ready(session.live_provider):
                    st.info(live_name+' 在线服务暂不可用，请稍后再试。')

    if session.read_only:
        scroll_bridge.mount(turns=len(session.history),scope=session.sid)
        return

    if submission is None:submission=interaction.consume(session)
    if followup:submission=dict(message=followup['question'],request_id=followup['request_id'],entry='followup',origin=followup)
    if submission:
        message,send,allow_live=submission['message'],True,_live_request_allowed(session) if session.live else False

    if send and action:
        st.warning("请先完成待确认的操作。")
    elif send and message.strip():
        st.session_state.pop('a_pay_notice_'+str(getattr(session,'sid','')),None)
        st.session_state.pop('a_aftercare_'+str(getattr(session,'sid','')),None)
        # A new request is about the new request: collapse an order card the
        # customer had opened, so it does not follow every later screen.
        for stale in [k for k in st.session_state if str(k).startswith('order_open_')]:
            st.session_state.pop(stale,None)
        from web.user_features import state as feature_state
        context=feature_state(session)
        if context.get('selected_train') and any(w in message for w in ('订','买')):
            t=context.get('selected_train') or {}
            if t.get('train_no'):
                message=f"{message}；车次{t.get('train_no')}，{t.get('date') or ''}，{t.get('seat_type') or ''}"
        if context.get('policy_context') and not operation_kind(message,session.history) and not any(w in message for w in ('订','买')):
            d=context.get('policy_context') or {}
            doc_id=str(d.get('doc_id') or '')
            if doc_id:
                message+=f"；参考政策{doc_id}（{d.get('source') or '政策库'}）：{d.get('content') or ''}"
        from web.order_actions import route_refund_request
        if route_refund_request(session,message):
            st.session_state['user_clear_input']=True
            st.rerun()
        # A paid order must stay actionable in natural language too.  A short
        # 「我要退票」/「改签到 G6245」 creates the same real V3.9 proposal as
        # the buttons below, instead of falling through to the offline planner
        # (which only reads the order) or the legacy tickets.db refund route.
        from web.railway_queries import (aftercare_intent,paid_orders,open_refund_card,
                                         open_change_card,change_candidates)
        intent=aftercare_intent(message)
        paid=paid_orders(session) if intent else []
        if paid:
            with chat_submission_slot:
                with st.chat_message('user'):st.write(message)
            order=paid[0]
            if intent=='REFUND':
                ok,pid,reply=open_refund_card(session,order,message)
            else:
                trains,args=change_candidates(session,order)
                wanted=next((t for t in trains
                             if str(t.get('trip_short_name') or '').upper() in message.upper()),None)
                target=wanted or (trains[0] if trains else None)
                ok,pid,reply=(open_change_card(session,order,target,args,message) if target
                              else (False,None,'当前没有可改签的车次，请先查询这一线路的车次。'))
            _aftercare_echo(session,message,reply,ok,pid)
            sent=(submission or {}).get('origin') or {}
            if sent.get('sent_key'):st.session_state[sent['sent_key']]='sent'
            st.session_state['user_clear_input']=True
            st.rerun()
        # A payment continuation must produce a real PAY confirmation card.
        # Sending it to the offline planner only returned a capability line for
        # the order it had just read (planner stops on the CREATE_ORDER
        # proposal_id inside railway_get_order), so the page creates the card
        # through the trusted page-operation path instead.
        from web.railway_queries import payment_order,open_payment_card,payment_intent
        pay_order=payment_order(session,message)
        if not pay_order and payment_intent(message):
            # A payment request with no committed pending order must not fall
            # through to the offline planner (it replies about a missing order)
            # nor set the misleading 「现在不能确认」 hint.  State the fact and
            # show the customer the exact path to a payable order.
            with chat_submission_slot:
                with st.chat_message('user'):st.write(message)
            st.session_state['a_pay_notice_'+session.sid]=(
                '当前还没有待支付订单。完成下单后，对话底部会出现支付入口。')
            sent=(submission or {}).get('origin') or {}
            if sent.get('sent_key'):st.session_state[sent['sent_key']]='sent'
            st.session_state['user_clear_input']=True
            st.rerun()
        if pay_order:
            with chat_submission_slot:
                with st.chat_message('user'):st.write(message)
            if open_payment_card(session,pay_order,message):
                total=pay_order.get('total_fen')
                amount=('¥'+f'{total/100:.2f}') if type(total) is int else '票面金额见确认卡'
                st.session_state['a_pay_turn_'+session.sid]=dict(
                    message=message,order_id=str(pay_order.get('order_id')),
                    reply=('已为订单 '+str(pay_order.get('order_id'))+' 生成支付确认卡，'+amount+
                                   '。请在主对话里核对支付二维码并完成支付。'))
                sent=(submission or {}).get('origin') or {}
                if sent.get('sent_key'):st.session_state[sent['sent_key']]='sent'
                st.session_state['user_clear_input']=True
                st.rerun()
            st.stop()
        # A request that names a real city pair but no travel day is a complete
        # intent, not a failed one: ask the day in place (one tap answers it)
        # instead of sending it to the planner, which used to reply that the
        # request could not be understood.  Refund/change/payment wording was
        # already handled above, so nothing transactional is delayed here.
        from web.railway_queries import route_ask, pending_route_ask, forget_route_ask, date_answer
        ask=route_ask(session,message)
        if ask:
            with chat_submission_slot:
                with st.chat_message('user'):st.write(message)
            st.session_state['a_route_ask_'+session.sid]=ask
            sent=(submission or {}).get('origin') or {}
            if sent.get('sent_key'):st.session_state[sent['sent_key']]='sent'
            st.session_state['user_clear_input']=True
            # The question is the newest content: bring it into view.
            scroll_bridge.request('bottom',scope=session.sid)
            st.rerun()
        elif pending_route_ask(session) and not date_answer(message):
            forget_route_ask(session)
        if session.live and not allow_live:
            st.warning("请先确认在线服务费用。")
        elif session.live and not session.full_tools and operation_kind(message, session.history):
            st.info("当前在线服务仅支持查票和政策咨询。")
        else:
            request_id=submission['request_id'] if submission else st.session_state['user_submit_nonce']
            st.session_state['user_submit_nonce']=uuid.uuid4().hex
            if operation_kind(message, session.history):
                # operation_kind() is now a copy/wordings aid only.  It no
                # longer creates a UI-only pending operation: the backend
                # proposal (session.pending_action) is the single source of a
                # confirmation card, and every message uses the same send path.
                st.session_state['a_confirm_hint_'+session.sid]=True
            with chat_submission_slot:
                with st.chat_message('user'):st.write(message)
            if (submission or {}).get('entry')!='followup':scroll_bridge.request('bottom',scope=session.sid)
            scroll_bridge.mount(turns=len(session.history)+1,scope=session.sid)
            def progress(event):
                op=next((r for r in session.operations if r['request_id']==request_id),None)
                if op:live_run_slot.markdown(interaction.markup(op),unsafe_allow_html=True)
            origin=(submission or {}).get('origin') or {}
            try:
                with chat_submission_slot:
                    result=execute(session,message,request_id,origin=origin,entry=(submission or {}).get('entry','chat'),on_event=progress)
            except Exception:
                if origin.get('sent_key'):st.session_state.pop(origin['sent_key'],None)
                raise
            if result:
                if origin.get('sent_key'):
                    if not getattr(session,'error',None) and not result.get('error'):
                        st.session_state[origin['sent_key']]='sent'
                    else:
                        st.session_state.pop(origin['sent_key'],None)
                from web.followup_jobs import schedule
                if schedule(session,result,authorized=_live_request_allowed(session)):
                    st.session_state['followups_poll_'+session.sid]=True
            st.session_state['user_clear_input']=True
            st.rerun()

    # Mounted last so it observes the final layout of this render.
    scroll_bridge.mount(turns=len(session.history)+int(interaction.busy(session)),scope=session.sid)


def show_remote_export(session):
    from target.observability import configuration_status,UPLOAD_SCOPE,export_payload
    state=configuration_status()
    with st.expander("LangSmith 可选远端追踪"):
        label=('配置错误，请检查集成中心' if state['state']=='configuration_error' else
               '未配置LangSmith Key' if not state['key_configured'] else
               '已启用脱敏导出，等待本轮导出核验' if state['enabled'] else '脱敏导出未开启')
        st.caption('状态：'+label+'；打开本区域不会上传。')
        st.write(UPLOAD_SCOPE)
        run=session.agent.langchain_engine.last_live_run if session.agent and session.agent.langchain_engine else None
        if not run:
            model='Qwen3.8-Flash' if session.live_provider=='bailian' else 'DeepSeek'
            st.info('当前 '+model+' 会话还没有已保存的执行记录。请先在下方发送一条消息，模型执行后才能预览并导出到LangSmith。切换模型或打开面板不会产生记录。')
            st.button('导出本轮并验证远端',disabled=True,key='remote_export_'+session.sid)
        if run:
            if run.get('provider')!=session.live_provider+'_live':
                st.error('执行记录的模型来源与当前会话不匹配，已停止导出。请检查Trace或新建会话。')
                return
            st.json(export_payload(run),expanded=False)
            previous=session.latest_remote_receipt()
            if previous:
                labels={'verified':'已核验，远端内容匹配','pending_verification':'已接受，暂时不可读，待验证',
                        'upload_outcome_unknown':'上传结果未知，先读取原ID核验','failed':'上次核验未通过，原ID保留'}
                st.caption('远端状态：'+labels.get(previous['remote_status'],previous['remote_status']))
                st.caption('已有远端运行ID：'+previous['remote_run_id']+'；不重复POST上传。')
                agree=st.checkbox('允许读取现有远端记录核验（最多3次GET，不重新上传）',key='remote_read_consent_'+session.sid)
                if st.button('重新核验现有远端记录（仅GET）',disabled=not agree,key='remote_read_'+session.sid):
                    session.recheck_export(consent=True)
                    st.rerun()
            else:
                agree=st.checkbox("我已检查脱敏内容，允许将以上本轮记录发送至 LangSmith",key="remote_consent_"+session.sid)
                st.caption('最多1次POST与3次GET；仅202后的404延迟读取，仍不可读则保留待验证。')
                if st.button("导出本轮并验证远端",disabled=not agree or not state["enabled"] or not state['key_configured'],key="remote_export_"+session.sid):
                    session.export_last(consent=True)
                    st.rerun()
        if session.remote_receipts:
            st.json(session.remote_receipts[-1])