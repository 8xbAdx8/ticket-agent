"""Passenger-facing projection only. No database access or simulated trades."""
from datetime import datetime, timedelta
from html import escape
from contextlib import ExitStack
import hashlib
import streamlit as st
from web.result_rows import iter_rows, as_row


def instant(value, day=None):
    if not value:return None
    try:
        if 'T' in str(value):return datetime.fromisoformat(value)
        h,m,s=map(int,str(value).split(':'))
        return datetime.fromisoformat(day)+timedelta(hours=h,minutes=m,seconds=s)
    except (ValueError,TypeError):return None


def minutes(a,b):
    if a is None or b is None:return None
    try:
        n=int((b-a).total_seconds()/60)
        return n if n>=0 else None
    except TypeError:return None


def duration(n):
    if n is None:return '时长未提供'
    return (str(n//60)+'小时' if n>=60 else '')+(str(n%60)+'分钟' if n%60 or n==0 else '')


def projection(train, args, names):
    day=args.get('service_date')
    a=instant(train.get('departure_at'),day);b=instant(train.get('arrival_at'),day)
    return dict(number=train.get('trip_short_name') or '车次未提供',
        origin=names.get(args.get('origin_stop_id'),'出发站未提供'),
        destination=names.get(args.get('destination_stop_id'),'到达站未提供'),
        departure=a.strftime('%H:%M') if a else '—',arrival=b.strftime('%H:%M') if b else '—',
        departure_date=a.strftime('%m月%d日') if a else '',
        arrival_date=b.strftime('%m月%d日') if b else '',
        day_offset=(b.date()-a.date()).days if a and b else 0,duration=duration(minutes(a,b)))


def card_html(v):
    e=lambda k:escape(str(v[k]))
    return '<article class="rail-journey"><header><strong>'+e('number')+'</strong><span>列车行程</span></header><div class="rail-route"><div class="rail-end"><b>'+e('departure')+'</b><strong>'+e('origin')+'</strong><small>'+e('departure_date')+'</small></div><div class="rail-line"><span>'+e('duration')+'</span><div class="rail-track"><i></i><i></i></div><small>沿途经停，点击查看</small></div><div class="rail-end rail-arrival"><b>'+e('arrival')+(' <sup>+'+str(v['day_offset'])+'天</sup>' if v['day_offset']>0 else '')+'</b><strong>'+e('destination')+'</strong><small>'+e('arrival_date')+'</small></div></div></article>'


def names_for(session):
    names={}
    groups=[getattr(session,'railway_queries',[])] + list(getattr(session,'results',[])) if session else []
    wanted=set()
    for row in iter_rows(groups):
        result=row.get('result') if isinstance(row.get('result'),dict) else {}
        if row.get('ok') and row.get('tool')=='railway_search_stations':
            names.update({r['stop_id']:r['stop_name'] for r in result.get('data',[]) if isinstance(r,dict) and 'stop_id' in r and 'stop_name' in r})
        args=row.get('args') if isinstance(row.get('args'),dict) else (result.get('query_parameters') if isinstance(result.get('query_parameters'),dict) else {})
        wanted.update(x for x in (args.get('origin_stop_id'),args.get('destination_stop_id')) if x)
    missing=wanted-set(names)
    if missing:
        try:
            from target.v39.static import RailwayStatic
            static=RailwayStatic()
            for stop_id in missing:
                station_result=static.station(stop_id)
                data=station_result.get('data') if isinstance(station_result,dict) else None
                if isinstance(data,list):data=next((x for x in data if isinstance(x,dict) and x.get('stop_name')),None)
                if isinstance(data,dict) and data.get('stop_name'):names[stop_id]=data['stop_name']
        except (ValueError,OSError):
            # Static lookup is only a label fallback; the card can still render
            # the trip with an explicit missing-station label.
            pass
    return names


def stops_view(result, day):
    data=result.get('data') or {};stops=data.get('stops',[]) if isinstance(data,dict) else []
    if not stops:st.info('暂未取得经停信息，请稍后重新查询。');return
    html=[]
    for s in stops:
        a=instant(s.get('arrival_at') or s.get('arrival_time'),day)
        b=instant(s.get('departure_at') or s.get('departure_time'),day)
        clock=lambda t:t.strftime('%m月%d日 %H:%M') if t else '未提供'
        dwell=minutes(a,b)
        html.append('<li><strong>'+escape(s['stop_name'])+'</strong><span>到达 '+clock(a)+'　出发 '+clock(b)+'</span>'+('<small>停站 '+duration(dwell)+'</small>' if dwell is not None else '')+'</li>')
    st.html('<ol class="rail-stops">'+''.join(html)+'</ol>')


def trips_view(row, session=None):
    row=as_row(row)
    if row is None:
        st.warning('车次数据格式无法识别，未渲染卡片；请查看原始运行记录。')
        return
    active=getattr(session,'railway_followup_row',None) if session else None
    # Agent public rows have no query ID; bind the current presentation copy
    # without changing the public result or old Trace.
    if active and not row.get('id') and active.get('result')==row.get('result'):
        row=active
    result=row.get('result') if isinstance(row.get('result'),dict) else {}
    if not result:
        st.warning('车次结果格式无法识别，未渲染卡片；请查看原始运行记录。')
        return
    args=result.get('query_parameters') if isinstance(result.get('query_parameters'),dict) else (row.get('args') if isinstance(row.get('args'),dict) else {})
    names=names_for(session);trains=[t for t in (result.get('data') or []) if isinstance(t,dict)]
    total=result.get('total_count',len(trains));limit=result.get('limit',20)
    page=int(args.get('cursor') or 0)//max(1,limit)+1
    st.markdown('### 车次查询')
    st.write(f'共 {total} 班 · 第 {page} 页 · 本页 {len(trains)} 班')
    st.caption('静态时刻不代表实时运行状态，库存、报价和交易为本地模拟。')
    if not trains:st.info('当前条件没有匹配车次，请调整日期或站点。')
    identity=str(row.get('id') or hashlib.sha256(str(row).encode()).hexdigest()[:16])
    from web import railway_followups as followups
    active=getattr(session,'railway_followup_row',None) if session else None
    current=bool(session and active and followups.identity(session.sid,active)==followups.identity(session.sid,row))
    focus_key='rail_focus_'+(session.sid if session else '')+'_'+identity
    if not trains:return
    with ExitStack() as stack:
        for index,train in enumerate(trains):
            if index == 3:
                stack.enter_context(st.expander('其余 '+str(len(trains)-3)+' 班（滚动查看）',expanded=False))
                stack.enter_context(st.container(height=360,key='rail_rest_'+identity,border=False))
            with st.container(key='journey_'+identity+'_'+str(index)):
                st.html(card_html(projection(train,args,names)))
                if session and not session.read_only and st.button('选择此车次',key='choose_'+identity+'_'+str(index)):
                    from web.business_state import select_trip
                    select_trip(session,row,train)
                    st.rerun()
                for item in reversed(list(iter_rows(getattr(session,'railway_queries',[]) if session else []))):
                    q=item.get('args',{})
                    if item.get('ok') and item.get('tool')=='railway_check_inventory' and q.get('trip_id')==train.get('trip_id') and all(q.get(k)==args.get(k) for k in ('service_date','origin_stop_id','destination_stop_id')):
                        inventory=item['result']
                        if inventory.get('status')=='SIMULATED_AVAILABLE' and type(inventory.get('available')) is int:
                            label={'SECOND':'二等座','FIRST':'一等座','BUSINESS':'商务座'}.get(q.get('seat_class'),'所选席别')
                            st.session_state['rail_inventory_'+identity+'_'+str(index)]=str(train.get('trip_short_name'))+' · '+label+' · 上次查询模拟余票 '+str(inventory['available'])+' 张'
                        break
                key='stops_'+(session.sid if session else 'replay')+'_'+identity+'_'+str(index)
                opened=st.session_state.get(key+'_open',False)
                if session and st.button('收起经停' if opened else '查看经停',key=key,disabled=session.read_only):
                    st.session_state[key+'_open']=not opened
                    st.session_state[focus_key]=train['trip_id']
                    from web.business_state import select_trip
                    select_trip(session,row,train)
                    if not opened and key+'_data' not in st.session_state:
                        if getattr(session,'_unified_interaction',False):
                            from web.railway_queries import submit
                            submit(session,'railway_trip_stops',dict(trip_id=train['trip_id'],service_date=args['service_date']))
                            st.rerun()
                        from web.railway_defaults import prepare
                        from web.railway_queries import query
                        try:
                            service,ctx,effective=prepare(session)
                            st.session_state[key+'_data']=query(session,service,ctx,effective,'railway_trip_stops',dict(trip_id=train['trip_id'],service_date=args['service_date']))
                        except Exception:st.warning('经停信息暂不可读取，请稍后重试。')
                    st.rerun()
                detail=st.session_state.get(key+'_data')
                if not detail and session and getattr(session,'_unified_interaction',False):
                    detail=next((r for r in reversed(list(iter_rows(session.results))) if r.get('ok') and r.get('tool')=='railway_trip_stops'
                        and (r['result'].get('data') or {}).get('trip',{}).get('trip_id')==train['trip_id']
                        and str(r['result'].get('service_date','')).replace('-','')==str(args.get('service_date','')).replace('-','')),None)
                if detail and opened:
                    if detail['ok']:stops_view(detail['result'],args.get('service_date'))
                    else:st.warning('经停查询未完成，请核对条件或当前权限。')
    if current:
        inventory=[st.session_state.get('rail_inventory_'+identity+'_'+str(i)) for i in range(len(trains))]
        for label in inventory:
            if label:st.caption(label)
        focus=st.session_state.get(focus_key)
        index=next((i for i,t in enumerate(trains) if t['trip_id']==focus),None)
        detail=st.session_state.get('stops_'+session.sid+'_'+identity+'_'+str(index)+'_data') if index is not None else None
        if not getattr(session,'_unified_interaction',False):followups.render(session,row,names,focus,detail)
