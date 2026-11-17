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


# Demo presentation: a commuter corridor really dispatches every 3-5 minutes,
# which is impossible to talk through on stage.  The board therefore collapses
# the full static day into one real G departure per clock hour — roughly the
# "one train an hour" sample the original handover used.  Every card keeps its
# own real trip_id and clock time; nothing is invented.  Display only: the tool
# result / total_count / pagination cursor are untouched, and the header states
# the real all-day total so the two views are never confused.
HIGH_SPEED_PREFIX = 'G'
BOARD_PAGE_SIZE = 10


def high_speed_only(trains, args, keep_number=None):
    """Return (high-speed trains, other trains) in the feed's original order.

    Only G-prefix services are "高铁" in this timetable.  An explicit train
    number lookup keeps its own result (a customer asking for C7005 must still
    see C7005), and a corridor with no G service keeps everything rather than
    rendering an empty board.
    """
    rows=[t for t in (trains or []) if isinstance(t,dict)]
    if args.get('train_no'):return rows,[]
    def _is_g(t):return str(t.get('trip_short_name') or '').upper().startswith(HIGH_SPEED_PREFIX)
    def _wanted(t):return keep_number and str(t.get('trip_short_name') or '')==str(keep_number)
    high=[t for t in rows if _is_g(t) or _wanted(t)]
    if not high:return rows,[]
    chosen={id(t) for t in high}
    return high,[t for t in rows if id(t) not in chosen]


def _hour_key(train):
    """Clock hour of a real static departure, tolerating ISO and HH:MM:SS."""
    stamp = str(train.get('departure_at') or '')
    if len(stamp) >= 13 and stamp[10] in ('T', ' '):
        return stamp[11:13]
    if ':' in stamp:
        return stamp.split(':', 1)[0].zfill(2)
    return ''


def day_board(session, args):
    """One real high-speed departure per clock hour, in departure order.

    One tool page only carries 50 rows, so a day with 159 services looked like
    three trains.  The static timetable is read-only, so the board reads the
    whole day and then samples one real G service per hour for the demo.  Total
    / high keep the real all-day counts; shown is what the board actually lists.
    Returns None whenever the full day cannot be read, so the caller keeps the
    tool result.
    """
    if session is None or getattr(session, 'read_only', False): return None
    if not all(args.get(k) for k in ('service_date', 'origin_stop_id', 'destination_stop_id')):
        return None
    try:
        from web.railway_queries import _day_trains
        rows = [t for t in (_day_trains(session, args) or []) if isinstance(t, dict)]
    except (ValueError, TypeError, OSError, KeyError):
        return None
    if not rows:
        return None
    is_g = lambda t: str(t.get('trip_short_name') or '').upper().startswith(HIGH_SPEED_PREFIX)
    rows.sort(key=lambda t: str(t.get('departure_at') or ''))
    high = [t for t in rows if is_g(t)]
    if not high:
        return None
    seen = set()
    shown = []
    for train in high:
        hour = _hour_key(train)
        if hour and hour in seen:
            continue
        if hour:
            seen.add(hour)
        shown.append(train)
    return dict(trains=shown, total=len(rows), high=len(high),
                shown=len(shown), other=len(rows) - len(high))


def card_html(v, *, selected=False):
    e=lambda k:escape(str(v[k]))
    marker=' rail-is-selected' if selected else ''
    badge='<span class="rail-selection">已选车次</span>' if selected else '<span>列车行程</span>'
    return '<article class="rail-journey'+marker+'"><header><strong>'+e('number')+'</strong>'+badge+'</header><div class="rail-route"><div class="rail-end"><b>'+e('departure')+'</b><strong>'+e('origin')+'</strong><small>'+e('departure_date')+'</small></div><div class="rail-line"><span>'+e('duration')+'</span><div class="rail-track"><i></i><i></i></div></div><div class="rail-end rail-arrival"><b>'+e('arrival')+(' <sup>+'+str(v['day_offset'])+'天</sup>' if v['day_offset']>0 else '')+'</b><strong>'+e('destination')+'</strong><small>'+e('arrival_date')+'</small></div></div></article>'


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


def trips_view(row, session=None, latest=False):
    """One train board, wrapped in a keyed container.

    The wrapper key is the scroll anchor 返回车次列表 uses: the page goes back to
    the board it already rendered instead of appending a second copy at the foot
    of the conversation (that copy buried every later step).
    """
    row=as_row(row)
    if row is None:
        st.warning('车次数据格式无法识别，未渲染卡片；请查看原始运行记录。')
        return
    identity=str(row.get('id') or hashlib.sha256(str(row).encode()).hexdigest()[:16])
    with st.container(key='board_'+identity):
        _trips_board(row,session,latest,identity)


def _trips_board(row, session=None, latest=False, identity=''):
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
    names=names_for(session);all_trains=[t for t in (result.get('data') or []) if isinstance(t,dict)]
    total=result.get('total_count',len(all_trains));limit=result.get('limit',50)
    page=int(args.get('cursor') or 0)//max(1,limit)+1
    more=' · 还有下一页' if result.get('has_more') else ''
    # Presentation only: the static timetable supplies the whole day, so the
    # board lists every real departure (real trip_id, real clock time) instead
    # of the single page the tool returned.  total_count / pagination / trip_id
    # of the tool result are untouched.
    pending_number=getattr(session,'pending_select_number',None) if session else None
    speed,other=high_speed_only(all_trains,args,pending_number)
    whole=day_board(session,args) if session and not args.get('train_no') else None
    # Every train that is listed must be selectable.  Without the static
    # whole-day read (rare fallback) the page shows its own rows as cards as
    # well, instead of a text list nobody can book.
    trains=whole['trains'] if whole else (speed+list(other))
    # "帮我买 G6505" asks for one train, not for the day's 170-service list.
    # Pin the named service so the board under that message is that train, and
    # keep the rest of the day one tap away.
    pin_key='board_pin_'+identity
    pin=None
    if session and whole:
        # Only the live board may take the number the customer just said: an
        # older board for the same corridor must keep showing the whole day.
        wanted=(str(pending_number or '') if latest else '') or str(st.session_state.get(pin_key) or '')
        hit=next((t for t in trains if str(t.get('trip_short_name') or '')==wanted),None) if wanted else None
        if hit:
            pin=wanted;st.session_state[pin_key]=wanted
        elif st.session_state.get(pin_key):
            st.session_state.pop(pin_key,None)
    if pin:
        trains=[t for t in trains if str(t.get('trip_short_name') or '')==pin]
    board_page=1;pages=1;offset=0;visible=trains
    if whole:
        pages=max(1,(len(trains)+BOARD_PAGE_SIZE-1)//BOARD_PAGE_SIZE)
        page_key='board_page_'+identity
        try:board_page=int(st.session_state.get(page_key) or 1)
        except (TypeError,ValueError):board_page=1
        board_page=min(max(1,board_page),pages)
        st.session_state[page_key]=board_page
        offset=(board_page-1)*BOARD_PAGE_SIZE
        visible=trains[offset:offset+BOARD_PAGE_SIZE]
    st.markdown('### 车次查询')
    if session and identity:
        # Remembered so 返回车次列表 can bring this board back into view.
        st.session_state['board_last_'+str(session.sid)]=identity
    head,pager=st.columns([3,2],vertical_alignment='center')
    if whole and pin:
        head.write(f'指定车次 {pin}')
        head.caption(f"静态时刻表全天 {whole['total']} 班（高铁 {whole['high']} 班）")
    elif whole:
        # Demo board: one real departure per clock hour, with the untouched
        # all-day total stated separately so the two numbers are never mixed.
        head.write(f"演示视图 · 每小时一班，共 {whole.get('shown', len(trains))} 班"+
                   (f' · 第 {board_page}/{pages} 页' if pages>1 else ''))
        head.caption(f"静态时刻表全天 {whole['total']} 班（高铁 {whole['high']} 班）；"
                     '此处按发车小时归并展示，卡片上的车次号与时刻均为真实数据。')
    else:
        head.write(f'共 {total} 班 · 第 {page} 页 · 本页 {len(visible)} 班'+more)
    # Pager sits in the header, never below the long train list.  Lazy import
    # avoids the railway_queries <-> railway_cards module cycle.
    if session and not getattr(session,'read_only',False):
        with pager:
            if whole and pin:
                if st.button('看当天全部车次',key='board_all_'+identity,use_container_width=True):
                    st.session_state.pop(pin_key,None);st.rerun()
            elif whole:
                if pages>1:
                    prev_col,next_col=st.columns(2)
                    if prev_col.button('上一页',key='board_prev_'+identity,disabled=board_page<=1,use_container_width=True):
                        st.session_state['board_page_'+identity]=board_page-1;st.rerun()
                    if next_col.button('下一页',key='board_next_'+identity,disabled=board_page>=pages,use_container_width=True):
                        st.session_state['board_page_'+identity]=board_page+1;st.rerun()
            else:
                from web.railway_queries import pagination
                pagination(session,row)
    if not trains:st.info('当前条件没有匹配车次，请调整日期或站点。')
    # A train-number lookup has no origin/destination leg, so the feed returns
    # no departure/arrival clock.  Showing a journey card full of "—" looks
    # like broken data; state exactly what is missing instead.
    if args.get('train_no') and all(not t.get('departure_at') for t in trains):
        st.write('查到车次 '+'、'.join(str(t.get('trip_short_name') or t.get('trip_id')) for t in trains[:10]))
        st.caption('正在查询这一班的时刻。')
        from web.railway_queries import resolve_train_number
        if resolve_train_number(session,row):return
        st.caption('暂时没有这一班的时刻；告诉我出发城市和到达城市，我再查一次。')
        return
    from web import railway_followups as followups
    active=getattr(session,'railway_followup_row',None) if session else None
    current=bool(session and active and followups.identity(session.sid,active)==followups.identity(session.sid,row))
    focus_key='rail_focus_'+(session.sid if session else '')+'_'+identity
    if not trains:return
    # "帮我买 G6023" is an explicit choice of one train: select it once, here,
    # where the card is rendered, so the booking step opens under that card.
    from web.business_state import query_identity,select_trip
    row_identity=query_identity(row)
    # A departure that already produced an order must not offer a booking form.
    has_order=False
    try:
        from web.business_panels import order_for_trip
        selected_now=getattr(session,'selected_railway_trip',None) or {}
        has_order=bool(selected_now and order_for_trip(session,selected_now))
    except Exception:
        has_order=False
    with ExitStack() as stack:
        for position,train in enumerate(visible):
            index=offset+position
            if not whole and position == 4:
                stack.enter_context(st.expander('其余 '+str(len(visible)-4)+' 班（展开查看）',expanded=False))
                stack.enter_context(st.container(height=360,key='rail_rest_'+identity,border=False))
            with st.container(key='journey_'+identity+'_'+str(index)):
                if latest and pending_number and str(train.get('trip_short_name') or '')==str(pending_number):
                    session.pending_select_number=None
                    select_trip(session,row,train)
                selected=getattr(session,'selected_railway_trip',None) or {}
                chosen=bool(selected and selected.get('trip_id')==train.get('trip_id')
                            and selected.get('query_identity')==row_identity)
                st.html(card_html(projection(train,args,names),selected=chosen))
                if session and not session.read_only:
                    if chosen and has_order:
                        # This departure already carries a committed order: the
                        # card says so instead of promising a booking form.
                        st.button('已订此车次',key='choose_'+identity+'_'+str(index),disabled=True)
                        st.caption('订单在页面底部。')
                    elif chosen:
                        # The booking step lives in the foot-of-page dock, not
                        # inside this card: a form wedged between two trains
                        # pushed the rest of the board off screen.
                        st.button('当前已选择',key='choose_'+identity+'_'+str(index),disabled=True)
                        st.caption('在页面底部继续办理。')
                    elif st.button('选择此车次',key='choose_'+identity+'_'+str(index)):
                        select_trip(session,row,train)
                        from web import scroll_bridge
                        scroll_bridge.request('run','action_dock',scope=session.sid)
                        st.rerun()
                for item in reversed(list(iter_rows(getattr(session,'railway_queries',[]) if session else []))):
                    q=item.get('args',{})
                    if item.get('ok') and item.get('tool')=='railway_check_inventory' and q.get('trip_id')==train.get('trip_id') and all(q.get(k)==args.get(k) for k in ('service_date','origin_stop_id','destination_stop_id')):
                        inventory=item['result']
                        if inventory.get('status')=='SIMULATED_AVAILABLE' and type(inventory.get('available')) is int:
                            label={'SECOND':'二等座','FIRST':'一等座','BUSINESS':'商务座'}.get(q.get('seat_class'),'所选席别')
                            st.session_state['rail_inventory_'+identity+'_'+str(index)]=str(train.get('trip_short_name'))+' · '+label+' · 上次查询余票 '+str(inventory['available'])+' 张'
                        break
                key='stops_'+(session.sid if session else 'replay')+'_'+identity+'_'+str(index)
                opened=st.session_state.get(key+'_open',False)
                detail=st.session_state.get(key+'_data')
                unified=bool(session and getattr(session,'_unified_interaction',False))
                if not detail and unified:
                    detail=next((r for r in reversed(list(iter_rows(session.results))) if r.get('ok') and r.get('tool')=='railway_trip_stops'
                        and (r['result'].get('data') or {}).get('trip',{}).get('trip_id')==train['trip_id']
                        and str(r['result'].get('service_date','')).replace('-','')==str(args.get('service_date','')).replace('-','')),None)
                if session and st.button('收起经停' if opened else '查看经停',key=key,disabled=session.read_only):
                    lookup=dict(trip_id=train['trip_id'],service_date=args['service_date'])
                    accepted=True
                    if not opened and not detail and unified:
                        from web.railway_queries import submit
                        accepted=submit(session,'railway_trip_stops',lookup)
                    elif not opened and not detail:
                        from web.railway_defaults import prepare
                        from web.railway_queries import query
                        try:
                            service,ctx,effective=prepare(session)
                            detail=query(session,service,ctx,effective,'railway_trip_stops',lookup)
                            if detail['ok']:st.session_state[key+'_data']=detail
                            accepted=detail['ok']
                        except Exception:
                            accepted=False
                    if accepted:
                        st.session_state[key+'_open']=not opened
                        st.session_state[focus_key]=train['trip_id']
                        select_trip(session,row,train)
                        st.rerun()
                    st.warning(st.session_state.pop('feature_notice_'+session.sid,'经停信息暂不可读取，请稍后重试。'))
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
