"""Deterministic presentation suggestions. No model or database calls."""
import hashlib,json,uuid


def identity(sid,row):
    return hashlib.sha256(json.dumps([sid,row],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def draft(state,sid):
    keys=('ft_from','ft_to','ft_date','ft_kind','ft_seat','rq_'+sid+'_from','rq_'+sid+'_to','rq_'+sid+'_date','rq_'+sid+'_kind','rq_'+sid+'_origin','rq_'+sid+'_destination')
    return json.dumps({k:state[k] for k in keys if k in state},sort_keys=True,default=str,ensure_ascii=False)


def register(session,row):
    if row['tool']=='railway_search_stations' and row.get('source')=='page_query':
        session.railway_followup_row=None
        return
    if row['tool']!='railway_query_trips':return
    session.railway_followup_row=dict(row,id=row.get('id') or uuid.uuid4().hex) if row.get('ok') else None


def build(sid,row,names,focus=None,detail=None):
    from web.railway_cards import instant,minutes
    if not row or not row.get('ok'):return []
    result=row['result'];rows=result.get('data') or []
    args=result.get('query_parameters') or row.get('args',{})
    day=args.get('service_date');origin=args.get('origin_stop_id');destination=args.get('destination_stop_id')
    if not rows or not day:return []
    token=identity(sid,row);out=[]
    selected=next((r for r in rows if r.get('trip_id')==focus),None)
    times=[r for r in rows if instant(r.get('departure_at')) and instant(r.get('arrival_at'))]
    prefix='出行日期 '+day+'；'
    if origin and destination:prefix='查询'+day+' '+names.get(origin,origin)+'到'+names.get(destination,destination)+'的车次。'+prefix
    if origin and destination:prefix+='出发站 '+names.get(origin,origin)+'（'+origin+'），到达站 '+names.get(destination,destination)+'（'+destination+'）；'
    prefix+='沿用当前查询条件，以本轮查询结果为准，仅执行只读查询。'
    def add(label,request,train=None):
        out.append(dict(label=label,message=prefix+' '+request,train_id=(train or {}).get('trip_id'),service_date=day,origin_stop_id=origin,destination_stop_id=destination,context_id=token))
    stops=(detail or {}).get('result',{}).get('data',{}) if (detail or {}).get('ok') else {}
    stops=stops.get('stops',[]) if isinstance(stops,dict) else []
    if selected:
        number=selected.get('trip_short_name')
        if stops:
            valid=[s for s in stops if minutes(instant(s.get('arrival_at') or s.get('arrival_time'),day),instant(s.get('departure_at') or s.get('departure_time'),day)) is not None]
            if valid:add('哪个站停留时间最长？',f'查询{number}的真实经停，比较停站时长，指出数据足够计算的最长停站。',selected)
            add(number+'经过多少站？',f'查询{number}的完整经停并统计真实站点数量。',selected)
            positions=[i for i,s in enumerate(stops) if s.get('stop_id')==destination]
            if positions and positions[0]>0:add('到达目的地前的最后一站？',f'查询{number}到达{names.get(destination,destination)}之前的最后一站。',selected)
        else:add('查看 '+str(number)+' 的经停站',f'查询{number}的完整真实经停。',selected)
        depart=instant(selected.get('departure_at'));arrive=instant(selected.get('arrival_at'))
        elapsed=minutes(depart,arrive)
        if elapsed is not None and any(minutes(instant(r.get('departure_at')),instant(r.get('arrival_at'))) is not None and minutes(instant(r.get('departure_at')),instant(r.get('arrival_at')))<elapsed for r in times):
            add('找运行时间更短的车次',f'查询同路线，找区间运行时间小于{elapsed}分钟的替代车次。',selected)
        if depart and any(instant(r.get('departure_at')) and instant(r['departure_at'])<depart for r in times):
            label='找比'+depart.strftime('%H:%M')+'更早出发的车次'
            add(label,'筛选出发时间早于'+depart.isoformat()+'的同路线车次。',selected)
        if arrive and any(instant(r.get('arrival_at')) and instant(r['arrival_at'])<arrive for r in times):
            add('找比'+arrive.strftime('%H:%M')+'更早到达的车次','筛选到达时间早于'+arrive.isoformat()+'的同路线车次。',selected)
        index=rows.index(selected)
        if index+1<len(rows):
            other=rows[index+1];add('比较 '+str(number)+' 和 '+str(other.get('trip_short_name')),f'比较{number}与{other.get("trip_short_name")}的真实出发、到达与区间运行时长。',selected)
    else:
        for label,low,high in [('上午出发（06–12时）',6,12),('下午出发（12–18时）',12,18),('晚上出发（18–24时）',18,24)]:
            if any(low<=instant(r['departure_at']).hour<high for r in times):
                add(label,f'查询同路线，按出发地当地时间筛选{day} {low:02}:00（含）至'+(f'{day} {high:02}:00（不含）' if high<24 else '次日00:00（不含）')+'出发的车次。')
        if len(times)>1:add('哪趟运行时间最短？','查询同路线并按实际到发时间比较区间运行时长，不根据车次号猜测。')
        if len(out)<4:
            train=rows[0];add('查看 '+str(train.get('trip_short_name'))+' 的经停站','查询'+str(train.get('trip_short_name'))+'的完整真实经停。',train)
    seen=set();unique=[]
    for q in out:
        if q['label'] not in seen:unique.append(q);seen.add(q['label'])
    return unique[:4]


def consume(session,request,questions):
    if not request or request.get('sid')!=session.sid or session.read_only:return None
    return next((dict(request,question=q['message']) for q in questions if request.get('context_id')==q['context_id'] and request.get('message')==q['message']),None)


def render(session,row,names,focus=None,detail=None):
    import streamlit as st
    questions=build(session.sid,row,names,focus,detail)
    if not questions:return
    draft_key='rail_query_draft_'+identity(session.sid,row)
    original=st.session_state.setdefault(draft_key,draft(st.session_state,session.sid))
    if original!=draft(st.session_state,session.sid):return
    st.markdown('**继续了解这趟行程**')
    if session.live:st.caption('建议基于本轮查询结果生成；点击后按当前模型发送一条消息并计费。')
    def queue(q):
        st.session_state['railway_followup_request']=dict(q,sid=session.sid,request_id=uuid.uuid4().hex,draft=draft(st.session_state,session.sid))
    with st.container(horizontal=True,key='rail_chips_'+identity(session.sid,row)[:20]):
        for index,q in enumerate(questions):
            st.button(q['label'],key='rail_chip_'+identity(session.sid,row)[:20]+'_'+str(index),on_click=queue,args=(q,),disabled=session.read_only or bool(session.pending_action()))
