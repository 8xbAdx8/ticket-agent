"""Bounded ticket-field validation; no API calls, inference, or reply rewriting."""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re

FIELDS = ('train_no','from_city','to_city','date','depart','arrive','seat_type','price','seats_left')
IDENTITY = ('train_no','date','from_city','to_city','seat_type','kind')
TRAIN = r'(?<![A-Za-z0-9])(?:[GDCZTKYS]\d{1,6}|[A-Z]{2}\d{3,6})(?![A-Za-z0-9])'
TIME = r'(?<![\d:])(\d{1,2}:\d{2})(?![\d:])'
SEAT = r'二等座|一等座|商务座|经济舱|公务舱'
DENIAL = r'未查到|没有查到|未找到|不存在|未返回|不在.{0,8}结果|没有匹配|无匹配|查无|不是|并非|不为'
UNCERTAIN = r'可能|也许|大概|大约|假设|如果|例如|举例|未确认|无法确认|是否|请问|(?:约|至少|不超过|低至)\s*[¥￥]?\d|元起|[?？]'
TYPES = dict(zip(FIELDS,('train_identity','route','route','date','departure_time','arrival_time','seat_type','price','inventory')))
LABELS = {
 'train_no':('train_no','车次','车次号','航班号'),
 'from_city':('from_city','出发地','出发城市','始发地','始发站'),
 'to_city':('to_city','目的地','到达地','到达城市','终点站'),
 'date':('date','日期','出行日期','乘车日期'),
 'depart':('depart','出发','发车','开车','出发时间','发车时间'),
 'arrive':('arrive','到达','抵达','到达时间'),
 'seat_type':('seat_type','席别','座席','座位类型'),
 'price':('price','票价','价格'),
 'seats_left':('seats_left','余票','剩余票数','剩余座位')}


def failure_notice(category):
    return {'reply_tool_mismatch':'模型生成结果与工具数据不一致，已拦截该回答；请查看工具结果与字段级证据。',
            'reply_data_indeterminate':'模型回答中的票务数据无法可靠核验，已停止展示该回答；请查看工具结果。'}.get(category)


def normalize(field,value):
    value=str(value).strip().strip('*`').strip()
    if field in ('depart','arrive'):
        m=re.fullmatch(r'(\d{1,2}):(\d{2})',value)
        if not m or int(m[1])>23 or int(m[2])>59:raise ValueError('invalid_time')
        return f'{int(m[1]):02}:{m[2]}'
    if field=='date':
        m=re.fullmatch(r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})日?',value)
        if not m:raise ValueError('absolute_date_required')
        return date(*map(int,m.groups())).isoformat()
    if field in ('price','seats_left'):
        value=re.sub(r'^[¥￥]\s*|\s*(?:元(?:/人)?|张|个座位)$','',value)
        if field=='seats_left' and re.fullmatch(r'0(?:\.0+)?\s*[（(]\s*(?:全部)?售罄\s*[）)]',value):return 0
        if field=='seats_left' and value in ('售罄','无票','无余票'):return 0
        if field=='seats_left' and value=='有票':return 'positive_stock'
        if not re.fullmatch(r'\d+(?:\.\d+)?',value):raise ValueError('exact_number_required')
        number=Decimal(value)
        if field=='seats_left':
            if number!=int(number):raise ValueError('integer_inventory_required')
            return int(number)
        return str(number.normalize())
    return value


def _authority(events):
    # Select the latest query namespace. A preceding legacy Fixture query must
    # not become the authority for a later real GTFS answer in the same turn.
    static=[(i,e) for i,e in enumerate(events or []) if isinstance(e,dict) and e.get('event')=='tool_end'
            and e.get('tool')=='railway_query_trips' and e.get('ok') is True
            and isinstance(e.get('result'),dict) and isinstance(e['result'].get('data'),list)]
    legacy=max((i for i,e in enumerate(events or []) if isinstance(e,dict) and e.get('event')=='tool_end'
                and e.get('tool')=='query_tickets' and e.get('ok') is True),default=-1)
    if static and static[-1][0]>legacy:
        from target.v39.query_facts import collect
        facts=collect(events)
        i,e=static[-1];result=e['result'];args=e.get('args',{})
        stations={}
        for v in events[:i]:
            if isinstance(v,dict) and v.get('event')=='tool_end' and v.get('tool')=='railway_search_stations' and v.get('ok') is True:
                stations.update({r['stop_id']:r['stop_name'] for r in v.get('result',{}).get('data',[])})
        rows=[]
        for item in facts['records']:
            record=item['record'];source=item['source'];args=source['args']
            values={'train_no':record.get('trip_short_name'),'date':args.get('service_date')}
            for field,name in (('depart','departure_at'),('arrive','arrival_at')):
                if record.get(name):values[field]=record[name][11:16]
            for field,name in (('from_city','origin_stop_id'),('to_city','destination_stop_id')):
                if args.get(name) in stations:values[field]=stations[args[name]]
            rows.append(dict(values={k:v for k,v in values.items() if v is not None},source=source))
        return rows,[dict(event_index=i,rows=len(rows),call_id=e.get('call_id'),args=args,complete=facts['complete'],pages=facts['pages'],issues=facts['issues'])]
    rows,queries=[],[]
    for i,e in enumerate(events or []):
        if not isinstance(e,dict) or e.get('event')!='tool_end' or e.get('tool')!='query_tickets':continue
        if e.get('ok') is not True or e.get('executed') is False:continue
        result=e.get('result')
        if not isinstance(result,dict) or not isinstance(result.get('trains'),list) or result.get('error'):continue
        if any(not isinstance(r,dict) or not r.get('train_no') for r in result['trains']):continue
        queries.append({'event_index':i,'rows':len(result['trains']),'call_id':e.get('call_id'),'args':e.get('args',{})})
        for row in result['trains']:
            if not isinstance(row,dict) or not row.get('train_no'):continue
            values={}
            for f in (*FIELDS,'kind'):
                if row.get(f) is not None:
                    try:
                        value=normalize(f,row[f])
                        if f!='seats_left' or type(value) is int:values[f]=value
                    except (ValueError,InvalidOperation):pass
            rows.append({'values':values,'source':{'event_index':i,'call_id':e.get('call_id'),'args':e.get('args',{})}})
    return rows,queries


def _prose(text):
    found=[]
    def add(f,v):
        if (f,v) not in found:found.append((f,v))
    for f in ('depart','arrive'):
        label='|'.join(sorted(LABELS[f],key=len,reverse=True))
        for m in re.finditer(r'(?:'+label+r')[：:=]?\s*'+TIME,text):add(f,m[1])
        for m in re.finditer(TIME+r'\s*(?:'+label+r')',text):add(f,m[1])
    for m in re.finditer(r'\d{4}[-年]\d{1,2}[-月]\d{1,2}日?',text):add('date',m[0])
    for f in ('from_city','to_city','seat_type','price','seats_left'):
        labels='|'.join(sorted(LABELS[f],key=len,reverse=True))
        value=(r'[¥￥]?\s*[+-]?\d+(?:\.\d+)?\s*(?:元(?:/人)?|张)?' if f in ('price','seats_left') else r'[^\s，,。；;:：=|]+')
        for m in re.finditer(r'(?:'+labels+r')(?:为|是)?[：:=]?\s*('+value+')',text):add(f,m[1].strip())
    for m in re.finditer(r'[¥￥]\s*\d+(?:\.\d+)?',text):add('price',m[0])
    for m in re.finditer(SEAT,text):add('seat_type',m[0])
    for f in ('date','depart','arrive','price','seats_left'):
        if not any(k==f for k,_ in found):
            labels='|'.join(sorted(LABELS[f],key=len,reverse=True))
            for m in re.finditer(r'(?:'+labels+r')[：:=]\s*([^，,。；;\s]+)',text):add(f,m[1])
    for f,label in (('depart','出发|发车|开车'),('arrive','到达|抵达')):
        if not any(k==f for k,_ in found):
            for m in re.finditer(r'(?:'+label+r')(?!地|城市)\s*([0-9一二三四五六七八九十]+点[^，,。；;\s]*)',text):add(f,m[1])
    if re.search(r'售罄|无余票|没有余票|已无票',text):add('seats_left','0')
    elif re.search(r'有余票|有票',text):add('seats_left','有票')
    route=r'(?:^|[\s，,：:（(）)])([\u4e00-\u9fff]{2,6})(?:→|->|到|至)([\u4e00-\u9fff]{2,6}?)(?=高铁|火车|航班|机票|飞机|的|[，,。\s(（]|$)'
    for m in re.finditer(route,text):
        # "以下为查询到的班次" contains 到, but is not a city route.
        if any(word in m[1]+m[2] for word in ('查询','车次','班次','以下','的','支持','结果','根据')):continue
        add('from_city',m[1]);add('to_city',m[2])
    return found


def _header(cell):
    cell=cell.strip().strip('*`').strip()
    for f,labels in LABELS.items():
        if cell in labels:return f
    if '票价' in cell:return 'price'
    return None


def _parse(reply):
    records,ignored,unresolved,denials=[],[],[],[]
    context,header,pending=[],None,None
    for number,original in enumerate((reply or '').splitlines(),1):
        text=original.strip().replace('**','')
        if not text:pending=None;continue
        if text.startswith('>'):
            ignored.append({'line':number,'text':original,'reason':'quoted_block'});continue
        def quotation(m):
            prefix=text[:m.start()]
            # A later asserted result must not inherit an earlier user attribution.
            if re.search(r'查到|查询结果|显示|结果为|车次为|班次为',prefix):return m[0][1:-1]
            if re.search(r'用户|[您你](?:刚才|之前)?(?:说|发的|输入(?:的)?|提到的)|原话|引用',prefix):
                ignored.append({'line':number,'text':m[0],'reason':'user_quotation'})
                return ''
            quoted=m[0][1:-1]
            if not re.search(TRAIN,quoted) and not _prose(quoted):
                ignored.append({'line':number,'text':m[0],'reason':'non_ticket_quotation'})
                return ''
            if (re.search(r'(?:比如|例如|示例|[（(]如)\s*$',prefix)
                    and not re.search(TRAIN+'|'+TIME+r'|[¥￥]|\d+\s*(?:元|张)',quoted)):
                ignored.append({'line':number,'text':m[0],'reason':'sample_query_quotation'})
                return ''
            unresolved.append({'line':number,'text':m[0],'reason':'unattributed_quotation'})
            return ''
        masked=re.sub(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"',quotation,text)
        text=masked
        if '|' in text:
            cells=[c.strip().strip('*`') for c in text.strip('|').split('|')]
            fields=[_header(c) for c in cells]
            if 'train_no' in fields:
                header=fields
                for c in cells:
                    seat=re.search(SEAT,c)
                    if seat:context=[(f,v) for f,v in context if f!='seat_type']+[('seat_type',seat[0])]
                pending=None;continue
            if all(re.fullmatch(r'[:\- ]*',c) for c in cells):continue
            if header and len(cells)==len(header):
                claims=[(f,c) for f,c in zip(header,cells) if f and c]
                train_cells=[v for f,v in claims if f=='train_no']
                if len(train_cells)==1 and '/' in train_cells[0]:
                    parts=[part.strip() for part in train_cells[0].split('/')]
                    if len(parts)<2 or len(set(parts))!=len(parts) or not all(re.fullmatch(TRAIN,part) for part in parts):
                        unresolved.append({'line':number,'text':original,'reason':'ambiguous_grouped_train_identity'});continue
                    for train in parts:
                        separate=[(f,train if f=='train_no' else v) for f,v in claims]
                        records.append({'line':number,'text':original,'claims':separate,'context':list(context),'format':'table_group'})
                else:
                    records.append({'line':number,'text':original,'claims':claims,'context':list(context),'format':'table'})
                continue
            if re.search(TRAIN,text):
                unresolved.append({'line':number,'text':original,'reason':'unrecognised_table'});continue
        for clause in re.split(r'[。！？；;]|但是|而是|但(?=实际|查询|查到)|[，,](?=\s*(?:可能|也许))|(?<=[，,])(?=实际|查到|查询结果显示|\s*[GDCZTKYS]\d)',text):
            ids=list(dict.fromkeys(re.findall(TRAIN,clause)))
            scoped_denial=re.fullmatch(r'\s*(?:查询结果|本次查询结果)(?:里|中)?没有\s*('+TRAIN+r')(?:\s*(?:这个车次|车次))?\s*[，,]?\s*',clause)
            if scoped_denial:
                denials.append({'line':number,'text':clause,'predicate':'train_absent_from_query_result','train_no':scoped_denial[1]})
                pending=None;continue
            continuation=re.fullmatch(r'\s*(?:因此|所以)查不到\s*('+TRAIN+r')(?:\s*(?:这个车次|车次))?\s*',clause)
            if continuation:
                if any(d.get('predicate')=='train_absent_from_query_result' and d.get('train_no')==continuation[1] for d in denials):
                    ignored.append({'line':number,'text':clause,'reason':'repeated_scoped_denial'})
                else:
                    unresolved.append({'line':number,'text':clause,'reason':'negative_train_scope_unknown'})
                pending=None;continue
            if re.match(r'^\s*(?:用户(?:刚才|之前|刚刚)?(?:说|提到|询问|输入|问)|[您你](?:刚才|之前|刚刚)?(?:说|提到|问)|原话)',clause):
                ignored.append({'line':number,'text':clause,'reason':'user_attribution'});continue
            if re.search(DENIAL,clause):
                ignored.append({'line':number,'text':clause,'reason':'negative_assertion'})
                if re.search(r'政策|知识库',clause) and (ids or re.search(r'车次|班次|余票|票价|席别|售罄|'+SEAT,clause)):
                    unresolved.append({'line':number,'text':clause,'reason':'mixed_policy_and_ticket_claim'})
                elif not ids and re.search(r'未查到|没有查到|没有匹配|无匹配',clause):
                    denials.append({'line':number,'text':clause,'predicate':'policy_empty_result' if re.search(r'政策|知识库',clause) else None})
                continue
            future_offer=re.fullmatch(
                r'\s*(?:如果|若|如需).{0,45}(?:告诉我|提供|补充).{0,30}'
                r'(?:我(?:可以|会|帮您|帮你)|可以)(?:为您|为你)?(?:查询|查看|查找)'
                r'(?:车次|班次|余票|票价)(?:[与和、/](?:车次|班次|余票|票价))*\s*',clause)
            # Asking for missing information before a possible future lookup
            # does not assert that any ticket is currently available.
            stock_question_offer=re.fullmatch(
                r'\s*(?:如果您愿意|如果你愿意)[，,]\s*(?:可以)?(?:告诉我|提供|补充)'
                r'(?:以下信息|行程信息)[，,]\s*我(?:先)?帮(?:您|你)(?:模拟)?'
                r'(?:查|查询)(?:一下)?有没有余票(?:[，,]供(?:您|你)参考)?[：:]?\s*',clause)
            purchase_advice=re.fullmatch(
                r'\s*(?:如果|若)(?:您|你)想(?:购买|订购)(?:明天|后天|今天)?'
                r'(?:[（(]\d{4}-\d{2}-\d{2}[）)])?'
                r'[\u4e00-\u9fff]{1,8}到[\u4e00-\u9fff]{1,8}的'
                r'(?:高铁|火车|机票|航班)(?:二等座|一等座|商务座|经济舱|头等舱)?'
                r'[，,]\s*建议通过\s*12306\s*官方\s*App\s*或网站办理\s*',clause, re.I)
            concrete=re.search(TRAIN+r'|\d|[¥￥]|[一二三四五六七八九十两百千万]+\s*(?:张|元|趟|分钟|小时|天)'
                               r'|有票|有余票|售罄|(?:已|已经|成功|完成).{0,12}(?:查询|锁座|下单|支付|取消)',clause)
            if stock_question_offer:
                ignored.append({'line':number,'text':clause,'reason':'future_query_offer'});continue
            if purchase_advice and not re.search(TRAIN+r'|有票|有余票|售罄|票价|已(?:经)?(?:购买|下单|支付)',clause):
                ignored.append({'line':number,'text':clause,'reason':'conditional_purchase_advice'});continue
            if future_offer and not concrete:
                ignored.append({'line':number,'text':clause,'reason':'future_query_offer'});continue
            # A similar offer with an extra statement must not disappear from
            # validation just because its wording starts with a condition.
            if concrete and re.search(r'(?:如果|若|如需).{0,80}(?:告诉我|提供|补充).{0,50}(?:查询|查看|查找)',clause):
                unresolved.append({'line':number,'text':clause,'reason':'future_offer_mixed_with_claim'})
            # A request for the user's next query is not a claim about ticket data.
            # Keep any concrete identity/number or asserted availability in normal validation.
            if (re.search(r'(?:如果|如需|若|需要|请).{0,60}(?:告诉我|告知我|提供|补充|指定|输入)',clause)
                    and not ids and not re.search(r'\d|[¥￥]|[一二三四五六七八九十百千万两]+\s*(?:元|分钟|小时|张|天)',clause)
                    and not re.search(r'查到|查得|查询结果|显示|有票|余票|票价|价格|库存|售罄|(?:出发|到达)(?:时间|时刻)?(?:为|是)',clause)):
                ignored.append({'line':number,'text':clause,'reason':'non_factual_follow_up'});continue
            # A date offered as an example while requesting missing input is
            # not a claim about a query result. Other concrete facts in the
            # same clause still require validation.
            without_example=re.sub(r'(?:例如|比如)\s*\d{4}[-年]\d{1,2}[-月]\d{1,2}日?', '', clause)
            remaining_claims=_prose(without_example)
            if (without_example!=clause and not ids
                    and re.search(r'(?:请(?:您)?(?:提供|补充|告知|输入)|需要.{0,16}补充)',clause)
                    and all(f=='date' and not re.search(r'\d|[¥￥]',v) for f,v in remaining_claims)):
                ignored.append({'line':number,'text':clause,'reason':'clarification_date_example'});continue
            # Only a count explicitly referring to already listed rows and one
            # seat type can be associated with a specific query result.
            aggregate=re.fullmatch(r'\s*([一二三四五六七八九十两1-9]\d?)趟车('+SEAT+r')都(?:有余票|有票)\s*',clause)
            if aggregate:
                count={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}.get(aggregate[1])
                if count is None and aggregate[1].isdigit():count=int(aggregate[1])
                seen=list(dict.fromkeys(v for rec in records for f,v in rec['claims'] if f=='train_no'))
                denials.append({'line':number,'text':clause,'predicate':'counted_all_available',
                                'count':count,'seat_type':aggregate[2],'listed_trains':seen})
                continue
            pairs=_prose(clause)
            if re.search(UNCERTAIN,clause) and (ids or pairs):
                unresolved.append({'line':number,'text':clause,'reason':'non_assertive_or_uncertain'});continue
            if len(ids)>1:unresolved.append({'line':number,'text':clause,'reason':'multiple_train_scope'})
            elif len(ids)==1:
                pending={'line':number,'text':original,'claims':[('train_no',ids[0]),*pairs],'context':list(context),'format':'prose'}
                records.append(pending)
            elif pairs:
                if pending is not None:
                    pending['claims'].extend(p for p in pairs if p not in pending['claims']);pending['text']+='\n'+original
                else:
                    availability=any(f=='seats_left' and v=='有票' for f,v in pairs)
                    if availability and re.search(r'均|全部|所有',clause):
                        denials.append({'line':number,'text':clause,'predicate':'all_available'})
                        pairs=[(f,v) for f,v in pairs if f!='seats_left']
                    elif availability and re.search(r'如下|以下',clause):
                        # Qualifies the following rows. Their explicit counts are checked separately.
                        ignored.append({'line':number,'text':clause,'reason':'list_availability_qualifier'})
                        pairs=[(f,v) for f,v in pairs if f!='seats_left']
                    shared=[(f,v) for f,v in pairs if f in IDENTITY];keys={f for f,_ in shared}
                    context=[(f,v) for f,v in context if f not in keys]+shared
                    if any(f not in IDENTITY for f,_ in pairs):
                        unresolved.append({'line':number,'text':clause,'reason':'unscoped_factual_claim'})
    return records,ignored,unresolved,denials


def check(reply,events):
    rows,queries=_authority(events)
    policy_queries=[e for e in (events or []) if isinstance(e,dict) and e.get('event')=='tool_end'
                    and e.get('tool')=='search_policy' and e.get('ok') is True and e.get('executed') is True
                    and isinstance(e.get('result'),dict) and isinstance(e['result'].get('hits'),list)]
    records,ignored,unresolved,denials=_parse(reply)
    findings,checks=[],[]
    def uncertain(record,reason,**extra):
        unresolved.append({**{k:record[k] for k in ('line','text')},'reason':reason,**extra})
    def fail(record,field,claimed,values,error_type=None,sources=None):
        findings.append({'train_no':dict(record['claims']).get('train_no'),'field':field,'claimed':claimed,
          'tool_value':values[0] if len(values)==1 else None,'tool_values':values,
          'error_type':error_type or TYPES.get(field,'record_identity')+'_mismatch',
          'line':record['line'],'text':record['text'],'authority_sources':sources or []})
    for record in records:
        own={f for f,_ in record['claims']}
        claims=record['claims']+[(f,v) for f,v in record['context'] if f not in own]
        parsed=[]
        for f,v in claims:
            try:
                pair=(f,normalize(f,v))
                if pair not in parsed:parsed.append(pair)
            except (ValueError,InvalidOperation):uncertain(record,'unsupported_or_invalid_value',field=f,claimed=v)
        identity={f:v for f,v in parsed if f in IDENTITY}
        if any(len({v for k,v in parsed if k==f})>1 for f in IDENTITY):
            uncertain(record,'conflicting_claimed_identity');continue
        train=identity.get('train_no')
        if not train:uncertain(record,'train_identity_required');continue
        candidates=[r for r in rows if r['values'].get('train_no')==train]
        if not queries:uncertain(record,'no_successful_authority');continue
        if not candidates:
            fail(record,'train_no',train,sorted({r['values']['train_no'] for r in rows}),'unreturned_train',queries);continue
        exact=[r for r in candidates if all(r['values'].get(f)==v for f,v in identity.items())]
        selected=exact or candidates
        if len({json.dumps(r['values'],sort_keys=True,ensure_ascii=False) for r in selected})!=1:
            if not exact and all(all(f in r['values'] for f in identity) for r in candidates):
                fail(record,'identity',identity,[r['values'] for r in candidates],'record_identity_mismatch',[r['source'] for r in candidates])
            else:uncertain(record,'ambiguous_business_identity_or_conflicting_snapshots',candidates=[r['values'] for r in selected])
            continue
        authority=selected[0]['values']  # All selected values equal: never match by list position.
        sources=[r['source'] for r in selected]
        for f,v in parsed:
            if f not in authority:uncertain(record,'authority_field_missing',field=f);continue
            matched=(authority[f]>0 if f=='seats_left' and v=='positive_stock' else v==authority[f])
            checks.append({'train_no':train,'identity':{k:authority[k] for k in IDENTITY if k in authority},
                           'field':f,'claimed':v,'tool_value':authority[f],'matched':matched,
                           'comparison':'greater_than_zero' if f=='seats_left' and v=='positive_stock' else 'equal',
                           'line':record['line'],'authority_sources':sources})
            if not matched:fail(record,f,v,[authority[f]],sources=sources)
    for denial in denials:
        if denial.get('predicate')=='policy_empty_result':
            if len(policy_queries)!=1 or policy_queries[0]['result']['hits']:
                uncertain(denial,'policy_empty_result_scope_unknown')
            else:
                checks.append({'field':'policy_search_result','claimed':'no_hits','matched':True,
                               'comparison':'policy_tool_returned_no_hits','line':denial['line'],
                               'authority_sources':[{'call_id':policy_queries[0].get('call_id')}]})
        elif denial.get('predicate')=='train_absent_from_query_result':
            if len(queries)!=1 or queries[0].get('complete') is False:
                uncertain(denial,'negative_train_scope_unknown')
            else:
                ids=sorted({r['values']['train_no'] for r in rows})
                matched=denial['train_no'] not in ids
                checks.append({'field':'train_no','claimed':denial['train_no'],'matched':matched,
                               'comparison':'train_absent_from_query_result','line':denial['line'],
                               'authority_sources':queries})
                if not matched:fail({'claims':[],**denial},'train_no',denial['train_no'],ids,'negative_train_mismatch',queries)
        elif denial.get('predicate')=='counted_all_available':
            ids=denial['listed_trains']; seat=denial['seat_type']
            selected=[[r for r in rows if r['values'].get('train_no')==train and r['values'].get('seat_type')==seat] for train in ids]
            if len(queries)!=1 or len(ids)!=denial['count'] or not ids or any(len(items)!=1 for items in selected):
                uncertain(denial,'counted_availability_scope_unknown')
            elif any('seats_left' not in items[0]['values'] for items in selected):
                uncertain(denial,'availability_authority_missing')
            else:
                values=[items[0]['values']['seats_left'] for items in selected]
                sources=[items[0]['source'] for items in selected]
                matched=all(value>0 for value in values)
                checks.append({'field':'seats_left','claimed':'counted_all_available','matched':matched,
                               'comparison':'counted_all_available','line':denial['line'],
                               'train_nos':ids,'tool_values':values,'authority_sources':sources})
                if not matched:fail({'claims':[],**denial},'seats_left','counted_all_available',values,'availability_mismatch',sources)
        elif denial.get('predicate')=='all_available':
            if len(queries)!=1 or any('seats_left' not in r['values'] for r in rows):
                uncertain(denial,'availability_scope_unknown')
            elif rows and all(r['values']['seats_left']>0 for r in rows):
                checks.append({'field':'seats_left','claimed':'all_available','matched':True,'line':denial['line']})
            else:fail({'claims':[],**denial},'seats_left','all_available',[r['values'].get('seats_left') for r in rows],'availability_mismatch')
        elif len(queries)!=1:uncertain(denial,'empty_result_scope_unknown')
        elif queries[0]['rows']:
            fail({'claims':[],**denial},'train_no','no_matching_trains',sorted({r['values']['train_no'] for r in rows}),'empty_result_contradiction')
        else:checks.append({'field':'train_no','claimed':'no_matching_trains','matched':True,'line':denial['line']})
    if any(q.get('complete') is False for q in queries):
        unresolved.append(dict(reason='incomplete_pagination',pages=queries[0].get('pages'),issues=queries[0].get('issues'),unresolved_candidate_findings=findings))
        findings=[]
    status='failed' if findings else 'indeterminate' if unresolved else 'checked_fields_match' if checks else 'not_verified'
    return {'schema':'reply-consistency/2','status':status,
      'verdict':'inconsistent' if findings else 'indeterminate' if unresolved or not checks else 'consistent_for_checked_fields',
      'checked_fields':sum(c['field']!='train_no' for c in checks),'identity_checks':sum(c['field']=='train_no' for c in checks),
      'findings':findings,'field_checks':checks,'indeterminate':unresolved,'ignored':ignored,'authority_queries':queries,
      'scope':'Explicit ticket fields in labelled prose/tables; not full natural-language or business accuracy'}
