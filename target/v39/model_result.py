"""Lossless fact projection for model context; full results stay in the Trace."""
import json
import copy

ROW_FIELDS={'trip_id','trip_short_name','trip_headsign','stop_id','stop_name','arrival_at',
            'departure_at','arrival_time','departure_time','raw_stop_sequence','position',
            'sequence_index','shape_status','origin_stop_id','destination_stop_id','stop_lat','stop_lon'}

def project(name,result):
    if name not in ('railway_search_stations','railway_query_trips','railway_trip_stops') or not isinstance(result,dict):return result
    output=dict(result)
    def row(value):return {k:v for k,v in value.items() if k in ROW_FIELDS} if isinstance(value,dict) else value
    if isinstance(result.get('data'),list):output['data']=[row(v) for v in result['data']]
    elif isinstance(result.get('data'),dict) and 'stops' in result['data']:
        output['data']=dict(result['data'],stops=[row(v) for v in result['data']['stops']])
    return output

def retrieve(values,call_id,trip_id):
    """Lookup only in this Agent thread's original messages; never cross sessions."""
    from langchain_core.messages import ToolMessage
    for message in values:
        if isinstance(message,ToolMessage) and message.tool_call_id==call_id and message.name=='railway_query_trips':
            data=json.loads(message.content)
            return next((copy.deepcopy(row) for row in data.get('data',[]) if row.get('trip_id')==trip_id),None)
    return None


def messages(values):
    """Copy old ToolMessages too, without mutating saved conversation history."""
    from langchain_core.messages import ToolMessage,HumanMessage,AIMessage
    import re
    from target.v39.query_facts import collect,summary
    last_user=max((i for i,m in enumerate(values) if isinstance(m,HumanMessage)),default=-1)
    intent=' '.join(str(m.content) for m in values[last_user:] if isinstance(m,HumanMessage))
    requested=set(re.findall(r'(?<![A-Za-z0-9])[GDCZTKYS]\d{1,6}(?![A-Za-z0-9])',intent))
    if not requested and not re.search(r'查询.*(?:到|至)|换.*(?:路线|目的)|出发站|到达站|出行日期',intent):
        for prior in reversed(values[:last_user]):
            if isinstance(prior,HumanMessage):
                candidates=re.findall(r'(?<![A-Za-z0-9])[GDCZTKYS]\d{1,6}(?![A-Za-z0-9])',str(prior.content))
                if candidates:requested=set(candidates);break
    events=[];args={}
    for m in values:
        if isinstance(m,AIMessage):args.update({c['id']:c.get('args',{}) for c in m.tool_calls})
        if isinstance(m,ToolMessage) and m.name=='railway_query_trips':
            try:events.append(dict(event='tool_end',tool=m.name,ok=True,executed=True,call_id=m.tool_call_id,args=args.get(m.tool_call_id,{}),result=json.loads(m.content)))
            except (ValueError,TypeError):pass
    facts=summary(collect(events))
    # Keep recent turns verbatim; older prose is summarized for the model only.
    # Tool payloads remain governed by the projection below and Trace is unchanged.
    human_indices=[i for i,m in enumerate(values) if isinstance(m,HumanMessage)]
    history_cutoff=human_indices[-3] if len(human_indices)>=3 else 0
    rows=[]
    for index,message in enumerate(values):
        if isinstance(message,ToolMessage) and message.name in ('railway_search_stations','railway_query_trips','railway_trip_stops'):
            try:
                original=json.loads(message.content)
                output=project(message.name,original)
                # The Trace keeps all rows.  For model context, a large current
                # page is represented by the same first three cards the user
                # sees; totals/next_cursor remain authoritative and unchanged.
                if message.name=='railway_query_trips' and len(output.get('data') or [])>20:
                    output['data']=output['data'][:3]
                    output['shown_count']=3
                    output['projection_note']='仅投影前3条到模型上下文；完整50/50/9结果保留在Trace与页面事件中。'
                if index<last_user:
                    output={k:v for k,v in output.items() if k!='data'}
                    output.update(history_summary=True,archive_call_id=message.tool_call_id,
                        omitted_records_require_lookup=True,
                        lookup_instruction='未保留的车次不得推测；需要细节时使用railway_query_trips按train_no及日期重新查询。')
                    if message.name=='railway_query_trips':
                        selected=[r for r in original.get('data',[]) if r.get('trip_short_name') in requested]
                        output['selected_records']=project(message.name,dict(data=selected))['data']
                elif message.name=='railway_query_trips' and facts:
                    output['deterministic_query_facts']=facts
                message=message.model_copy(update={'content':json.dumps(output,ensure_ascii=False)})
            except (TypeError,ValueError):pass
        if isinstance(message,AIMessage) and index<history_cutoff and len(str(message.content))>420:
            message=message.model_copy(update={'content':str(message.content)[:420]+'\n\n[历史回答已压缩；原始内容保留在 Trace]'})
        rows.append(message)
    return rows


def legacy_messages(values):
    """Retain the original Legacy dictionaries; adapt copies via the same governor."""
    from langchain_core.messages import AIMessage,HumanMessage,ToolMessage
    if not any(m.get('role')=='tool' and m.get('name','').startswith('railway_') for m in values):return values
    adapted=[];indices=[]
    for i,m in enumerate(values):
        role=m.get('role')
        if role=='user':value=HumanMessage(content=m.get('content') or '')
        elif role=='assistant':
            calls=[dict(id=c['id'],name=c['name'],args=c['arguments']) for c in m.get('tool_calls') or []]
            value=AIMessage(content=m.get('content') or '',tool_calls=calls)
        elif role=='tool':value=ToolMessage(content=m.get('content') or '',name=m.get('name'),tool_call_id=m['tool_call_id'])
        else:continue
        adapted.append(value);indices.append(i)
    governed=messages(adapted);output=copy.deepcopy(values)
    for i,m in zip(indices,governed):
        if output[i]['role']=='tool':output[i]['content']=m.content
    return output
