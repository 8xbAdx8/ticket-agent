"""Original right rail queries; shared Registry, no model calls or fake Agent runs."""
from datetime import date
import json,uuid
from web.railway_defaults import DEMO_DESTINATION, DEMO_ORIGIN, DEMO_SERVICE_DATE, DEMO_TRAIN, classify
from web.result_rows import as_row, iter_rows
import streamlit as st
from target.v39.context import scope
from target.v39.registry import dispatch,service_scope
from target.execution_config import scope as effective_scope

ERRORS={'V39_TOOL_NOT_ALLOWED':'当前会话未开放此查询，请到开发者工作空间检查权限。',
        'V39_CONFIG_MISMATCH':'配置已变化，请刷新后重新查询。',
        'INVALID_RAILWAY_ARGUMENTS':'查询条件不完整或格式不正确，请核对车站和日期。',
        'RAILWAY_INTERNAL_ERROR':'静态数据暂不可读取，请稍后重试；开发者工作空间保留诊断。'}


def submit(session,name,args):
    """User intent only; the current Agent chooses and executes authorized tools."""
    from web.interaction import enqueue
    from web.railway_cards import names_for
    names=names_for(session);day=args.get('service_date')
    if name=='railway_search_stations':text='查询真实静态车站：'+args['name']+'。'
    elif name=='railway_trip_stops':
        trains=[t for row in iter_rows(session.results) if row.get('tool')=='railway_query_trips' for t in (row.get('result') or {}).get('data',[])]
        number=next((t.get('trip_short_name') for t in trains if t.get('trip_id')==args['trip_id']),None)
        text=f'查询{number or "已选班次"}在{day}的完整经停站；班次标识{args["trip_id"]}。'
    elif args.get('train_no'):text=f'查询{day} {args["train_no"]}的真实静态车次。'
    else:text=f'查询{day} {names.get(args["origin_stop_id"],args["origin_stop_id"])}到{names.get(args["destination_stop_id"],args["destination_stop_id"])}的铁路车次；出发站编码{args["origin_stop_id"]}，到达站编码{args["destination_stop_id"]}。'
    if name!='railway_search_stations' and args.get('cursor') is not None:text+=f'从第{int(args["cursor"])+1}条开始，每页{args.get("limit",20)}条。'
    return enqueue(session.sid,text,'railway:'+name)

def query(session,service,ctx,effective,name,args):
    if session.read_only:raise ValueError('HISTORY_READ_ONLY')
    if name not in ('railway_search_stations','railway_query_trips','railway_trip_stops'):raise ValueError('READ_QUERY_ONLY')
    try:
        with scope(ctx),service_scope(service),effective_scope(effective):result,ok,elapsed=dispatch(name,args)
        service.page_event(ctx,name,args,result,ok,elapsed)
    except Exception as exc:
        result={'error':'RAILWAY_INTERNAL_ERROR','simulation':True};ok=False
    return dict(id=uuid.uuid4().hex,source='page_query',tool=name,args=args,result=result,ok=ok)

def record(session,row):
    if not hasattr(session,'railway_queries'):session.railway_queries=[]
    session.railway_queries.append(row)
    from web.railway_followups import register
    register(session,row)

def result_card(row, session=None):
    from web.railway_cards import trips_view,stops_view
    row=as_row(row)
    if row is None:return
    result=row['result'];name=row['tool']
    if not isinstance(result,dict):
        st.warning('查询结果格式无法识别；未渲染卡片，请查看原始运行记录。');return
    status,message=classify(result,row['ok'])
    if not row['ok']:
        st.warning(message+'，请核对条件后重试。');return
    if name=='railway_query_trips':
        trips_view(row,session)
        if session:pagination(session,row)
        return
    if name=='railway_trip_stops':
        st.markdown('### 沿途经停')
        stops_view(result,(result.get('query_parameters') or row.get('args',{})).get('service_date'));return
    if name=='railway_search_stations':
        st.markdown('### 车站查询')
        for item in result.get('data') or []:st.write(item['stop_name'])
        if not result.get('data'):st.info('没有找到匹配车站，请调整名称。')


def visible_rows(rows):
    # Preserve raw history, suppress only helper steps in the default route query.
    output=[];routes={}
    for row in iter_rows(rows):
        if row['tool']=='railway_search_stations' and row.get('source')=='default_query':continue
        if row['tool'] not in ('railway_search_stations','railway_query_trips','railway_trip_stops'):continue
        if row['tool']=='railway_query_trips':
            args=dict(row.get('args') or row['result'].get('query_parameters') or {})
            args.pop('cursor',None)
            key=json.dumps(args,sort_keys=True)
            if key in routes:output[routes[key]]=row
            else:routes[key]=len(output);output.append(row)
        else:output.append(row)
    return output


def history(session):
    for row in visible_rows(getattr(session,'railway_queries',[])):
        with st.chat_message('assistant'):
            result_card(row,session)


def page_args(row):
    args={k:v for k,v in (row.get('args') or row['result'].get('query_parameters') or {}).items() if v is not None}
    args.setdefault('limit',row['result'].get('limit',20))
    return args


def pagination(session,row):
    args=page_args(row)
    limit=row['result'].get('limit',20);offset=int(args.get('cursor') or 0)
    key='page_'+session.sid+'_'+str(row.get('id') or uuid.uuid5(uuid.NAMESPACE_URL,str(row)).hex)
    left,right=st.columns(2)
    for col,label,cursor,disabled in [(left,'上一页',str(max(0,offset-limit)),offset==0),
        (right,'下一页',row['result'].get('next_cursor'),not row['result'].get('has_more'))]:
        if col.button(label,key=key+label,disabled=disabled or session.read_only):
            if getattr(session,'_unified_interaction',False):
                submit(session,row['tool'],dict(args,cursor=cursor));st.rerun()
            from web.railway_defaults import prepare
            try:
                service,ctx,effective=prepare(session)
                record(session,query(session,service,ctx,effective,row['tool'],dict(args,cursor=cursor)))
            except Exception:
                st.warning('翻页暂未完成，请稍后重试。');return
            st.rerun()


def panel(session,service,ctx,effective):
    with st.expander('铁路查询',expanded=False):
        st.caption('通过当前Agent查询本地真实静态数据；在线模式会产生当前模型费用，结果进入聊天与运行记录。')
        key='rq_'+session.sid
        kind=st.radio('查询类型',['查车次','查车站','查经停站'],horizontal=True,key=key+'_kind')
        day=st.date_input('出行日期',value=date.fromisoformat(DEMO_SERVICE_DATE),key=key+'_date')
        if kind=='查车站':
            name=st.text_input('站名关键词',key=key+'_station')
            if st.button('查询车站',key=key+'_station_go',disabled=session.read_only or not name.strip()):
                submit(session,'railway_search_stations',dict(name=name.strip(),limit=20));st.rerun()
        elif kind=='查车次':
            origin=st.text_input('出发站名称',value=DEMO_ORIGIN,key=key+'_from')
            destination=st.text_input('到达站名称',value=DEMO_DESTINATION,key=key+'_to')
            if st.button('搜索候选车站',key=key+'_find',disabled=session.read_only or not origin.strip() or not destination.strip()):
                from web.interaction import enqueue
                enqueue(session.sid,f'分别查询真实静态车站：{origin.strip()}、{destination.strip()}。展示候选站点供我选择，不订票。','railway:stations')
                st.rerun()
            stations=[r for r in iter_rows(session.results) if r.get('ok') and r.get('tool')=='railway_search_stations']
            a=next((r for r in reversed(stations) if any(t.get('stop_name','').startswith(origin.strip()) for t in r['result'].get('data',[]))),None)
            b=next((r for r in reversed(stations) if any(t.get('stop_name','').startswith(destination.strip()) for t in r['result'].get('data',[]))),None)
            if a and b:st.session_state[key+'_candidates']=(origin,destination,a,b)
            saved=st.session_state.get(key+'_candidates')
            if saved and saved[:2]==(origin,destination):
                a,b=saved[2:]
                if not a['ok'] or not b['ok']:st.warning('候选查询未完成，请检查当前权限或数据源。')
                elif not a['result']['data'] or not b['result']['data']:st.info('未找到匹配站点，请调整名称。')
                else:
                    fmt=lambda r:r['stop_name']+'（'+r['stop_id']+'）'
                    x=st.selectbox('选择出发站',a['result']['data'],format_func=fmt,key=key+'_origin')
                    y=st.selectbox('选择到达站',b['result']['data'],format_func=fmt,key=key+'_destination')
                    if st.button('查询静态车次',key=key+'_trains',disabled=session.read_only):
                        submit(session,'railway_query_trips',dict(service_date=day.isoformat(),origin_stop_id=x['stop_id'],destination_stop_id=y['stop_id'],limit=20));st.rerun()
        else:
            number=st.text_input('车次号',value=DEMO_TRAIN,key=key+'_train_no')
            if st.button('查找班次',key=key+'_lookup',disabled=session.read_only or not number.strip()):
                submit(session,'railway_query_trips',dict(service_date=day.isoformat(),train_no=number.strip(),limit=50));st.rerun()
            found=next((r for r in reversed(list(iter_rows(session.results))) if r.get('ok') and r.get('tool')=='railway_query_trips'
                and (r['result'].get('query_parameters') or {}).get('train_no')==number.strip()
                and (r['result'].get('query_parameters') or {}).get('service_date')==day.isoformat()),None)
            if found:st.session_state[key+'_trips']=(day.isoformat(),number,found)
            saved=st.session_state.get(key+'_trips')
            if saved and saved[:2]==(day.isoformat(),number):
                found=saved[2]
                if found['ok'] and found['result'].get('data'):
                    trip=st.selectbox('选择真实班次',found['result']['data'],format_func=lambda r:r['trip_short_name']+' / '+r['trip_id'],key=key+'_trip')
                    if st.button('查询经停站',key=key+'_stops',disabled=session.read_only):
                        submit(session,'railway_trip_stops',dict(trip_id=trip['trip_id'],service_date=day.isoformat()));st.rerun()
                else:st.info('没有找到该日期的静态班次，请核对车次和日期。')
        pages=getattr(session,'railway_queries',[])
        if pages:
            last=pages[-1];cursor=last['result'].get('next_cursor') if isinstance(last['result'],dict) else None
            if cursor and st.button('查询下一页',key=key+'_next',disabled=session.read_only):
                submit(session,last['tool'],dict(last['args'],cursor=cursor));st.rerun()
