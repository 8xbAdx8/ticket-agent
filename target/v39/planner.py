"""Deterministic OFFLINE demonstration planner, not a real model provider.

Only proposes tools. Confirmation secrets and Service.confirm are inaccessible.
Ambiguous stations are returned for explicit selection, never guessed.
"""
import json,re,uuid
from datetime import date,datetime,timedelta,timezone
from target.v39.context import CURRENT


TRAIN_NUMBER = r'(?<![A-Za-z0-9])[GDCZTK]\d{1,6}(?![A-Za-z0-9])'
NEXT_PAGE = re.compile(r'^(?:请)?(?:帮我)?(?:继续)?(?:查(?:看|询)?|取|翻到|翻)?\s*(?:下一页|剩余车次|剩下的车次|翻页)(?:车次|列车)?[。！!\s]*$')
ROUTE_KEYS = ('service_date', 'origin_stop_id', 'destination_stop_id', 'train_no', 'seat_class')


def _last_route(history):
    """Use the most recent route attempt, including a failed one, in this thread."""
    for message in reversed(history):
        if message.get('role') == 'user' and len(set(re.findall(r'\d{4}-\d{2}-\d{2}', message['content']))) > 1:
            return {}, {}
        if message.get('role') != 'tool' or message.get('name') != 'railway_query_trips':
            continue
        payload = json.loads(message['content'])
        query = payload.get('query_parameters') or {}
        if query.get('origin_stop_id') and query.get('destination_stop_id') and not query.get('train_no'):
            return payload, {key: query[key] for key in ROUTE_KEYS if query.get(key) is not None}
        if payload.get('error'):
            return payload, {}
    return {}, {}


def _page_reply(payload):
    rows = payload['data']
    returned = payload['returned_count']
    total = payload['total_count']
    detail = '；'.join(
        f"{row.get('trip_short_name') or row['trip_id']} {row.get('departure_at', '')}→{row.get('arrival_at', '')}"
        for row in rows[:3]
    )
    continuation = ('，还有下一页' if payload['has_more'] else '，已到最后一页') if total else ''
    examples = f'。例如：{detail}' if detail else ''
    return (f"静态数据查询结果：{payload['status']}，共 {total} 班，本页返回 {returned} 班{continuation}"
            f'{examples}。静态时刻不代表实时开行、余票或官方票价。')


class RailwayDemoProvider:
    name='mock'
    last_usage={'prompt':0,'completion':0}
    mutations={}

    def chat(self,messages,tools):
        index=max(i for i,m in enumerate(messages) if m['role']=='user')
        text=messages[index]['content'].strip()
        today=datetime.now(timezone(timedelta(hours=8))).date()
        from target.v39.registry import SERVICE
        service=SERVICE.get()
        if service and getattr(service.clock,'simulation',False):today=service.now().astimezone(timezone(timedelta(hours=8))).date()
        for word,days in [('后天',2),('明天',1),('今天',0)]:text=text.replace(word,(today+timedelta(days=days)).isoformat())
        results=[m for m in messages[index+1:] if m['role']=='tool']
        payload=json.loads(results[-1]['content']) if results else None
        def reply(value):return dict(role='assistant',content=value,tool_calls=[])
        def call(name,args):return dict(role='assistant',content='',tool_calls=[dict(id=uuid.uuid4().hex,name=name,arguments=args)])
        owned_order=re.search(r'V39-[a-f0-9]{32}',text)
        if owned_order and re.match(r'查询(?:本人|我的)?订单',text):
            if not results:return call('railway_get_order',dict(order_id=owned_order[0]))
            if isinstance(payload,dict) and not payload.get('error'):
                from target.v39.read_model import passenger_summary
                return reply('订单 '+payload['order_id']+' 当前状态 '+payload['order_status']+'；模拟支付 '+payload['payment_status']+'；'+passenger_summary(payload)+'。此次仅查询，没有再次执行交易。')
        # UI integration exercises the same tools in offline mode. This is an
        # explicit deterministic planner, never evidence of Live model quality.
        if '订单' in text and re.search('我的|查看|查询',text) and not re.search(r'V39-[a-f0-9]{32}',text):
            if not results:return call('railway_get_order',{})
            return reply('已读取本人铁路模拟订单：'+str(len(payload) if isinstance(payload,list) else 1)+'笔。可在订单卡查看状态；尚未因此执行交易。')
        if re.search(r'政策|规则|行李|手续费|P\d{2}',text):
            if not results:return call('search_policy',dict(question=text))
            from target.providers import MockProvider
            return MockProvider(mutations={}).chat(messages,tools)
        day_match=re.search(r'\d{4}-\d{2}-\d{2}',text)
        number_match=re.search(TRAIN_NUMBER,text)
        history = messages[:index]
        previous, route = _last_route(history)
        # A conditional affirmative is still an explicit read-only request.
        tail = re.split(r'[？?]', text)[-1].strip()
        next_page = NEXT_PAGE.fullmatch(text) or (
            tail.startswith('如果还需要，') and NEXT_PAGE.fullmatch(tail.removeprefix('如果还需要，')))
        if next_page and not results:
            if not route or previous.get('status') != 'FOUND':
                return reply('请先成功查询出发站、到达站和日期，再查看下一页。')
            cursor = previous.get('next_cursor')
            if previous.get('has_more') is False:
                return reply('上次车次查询已到最后一页。')
            if (previous.get('has_more') is not True or not isinstance(cursor, str) or not cursor.isdigit()
                    or type(previous.get('limit')) is not int):
                return reply('上次查询没有可验证的下一页，请重新查询该线路。')
            return call('railway_query_trips', dict(route, cursor=cursor, limit=previous['limit']))
        origin_code = re.search(r'出发站编码\s*([A-Za-z0-9]+)', text)
        destination_code = re.search(r'到达站编码\s*([A-Za-z0-9]+)', text)
        if (not results and (origin_code or destination_code or '经停' in text or '比较' in text)
                and len(set(re.findall(r'\d{4}-\d{2}-\d{2}', text))) > 1):
            return reply('请确认一个出行日期，再查询静态车次。')
        if (day_match and route and previous.get('status') == 'FOUND' and type(previous.get('limit')) is int
                and re.fullmatch(r'(?:日期)?(?:改|换)(?:成|为|到)?\s*\d{4}-\d{2}-\d{2}[。！!\s]*', text) and not results):
            return call('railway_query_trips', dict(route, service_date=day_match[0], limit=previous['limit']))
        names = list(dict.fromkeys(re.findall(TRAIN_NUMBER, text)))
        comparison = re.match(r'^(?:请)?(?:帮我)?比较', text) and len(names) == 2
        explicit_day = day_match[0] if day_match else None
        lookup_day = explicit_day or route.get('service_date')
        if comparison and lookup_day:
            if len(results) < len(names):
                args = dict(route, service_date=lookup_day, train_no=names[len(results)], limit=20)
                return call('railway_query_trips', args)
            comparisons = [json.loads(item['content']) for item in results]
            if any(row.get('status') != 'FOUND' or row.get('total_count') != 1 for row in comparisons):
                return reply('当前条件下无法唯一确定这两趟车，请核对日期、区间和车次。')
            return reply('两趟车的静态时刻如下。' + '；'.join(
                f"{name} {row['data'][0]['departure_at']}→{row['data'][0]['arrival_at']}"
                for name, row in zip(names, comparisons)
            ) + '。')
        if text.startswith(('查询真实静态车站：','分别查询真实静态车站：')):
            requested=text.split('：',1)[1].split('。',1)[0].split('、')
            if len(results)<len(requested):return call('railway_search_stations',dict(name=requested[len(results)].strip()))
        if lookup_day and any(w in text for w in ('经停','停靠站')):
            tid=re.search(r'班次标识([A-Za-z0-9]+)',text)
            if not results:
                if tid:return call('railway_trip_stops',dict(trip_id=tid[1],service_date=lookup_day))
                if number_match:
                    args = route if not explicit_day else {}
                    return call('railway_query_trips',dict(args,service_date=lookup_day,train_no=number_match[0]))
            if results and results[-1]['name']=='railway_query_trips' and payload.get('total_count')==1:
                return call('railway_trip_stops',dict(trip_id=payload['data'][0]['trip_id'],service_date=lookup_day))
        elif day_match and number_match and not results:
            return call('railway_query_trips',dict(service_date=day_match[0],train_no=number_match[0],limit=20))
        if day_match and origin_code and destination_code and not results:
            offset=re.search(r'从第(\d+)条开始',text)
            return call('railway_query_trips',dict(service_date=day_match[0],origin_stop_id=origin_code[1],destination_stop_id=destination_code[1],limit=20,**({'cursor':str(int(offset[1])-1)} if offset else {})))
        if results:
            payload=json.loads(results[-1]['content'])
            if isinstance(payload,dict) and payload.get('error'):return reply('本次未完成：'+payload['error']+'。没有因此完成出票或扣款。')
            if isinstance(payload,dict) and payload.get('status')=='CONFIRMATION_REQUIRED' and payload.get('proposal_id'):
                return reply('已生成操作确认卡，请在页面核对后确认。本轮尚未完成该交易。')
            if results[-1]['name']=='railway_query_trips' and not any(w in text for w in ('经停','停靠站')):
                if isinstance(payload.get('data'),list) and {'total_count','returned_count','has_more'} <= payload.keys():
                    return reply(_page_reply(payload))
        if re.search('不要|暂不|别|如果|假设|能否|可以吗|怎么|如何|[？?]',text):
            if any(word in text for word in ('退票','退款','改签','手续费','政策')):
                return reply('D9 已批准方案B：改签后仍可退款；部分退款后可改签剩余 ACTIVE 乘客，也可继续退款。每名乘客最多一次成功退款，每订单最多一次成功改签。P01 以当前有效乘客价格快照为基数：>48小时5%，24至48小时10%，<24小时20%，整数分 half-up。以上仅为本地模拟规则，不代替真实铁路政策。')
            return reply('高风险操作需要明确指令和页面确认。可以查询车次、查看我的铁路订单，或在页面选择报价后建单。所有业务均为本地模拟。')
        if '订单' in text and re.search('我的|查看|查询',text) and not results:
            return call('railway_get_order',{})
        oid=re.search(r'V39-[a-f0-9]{32}',text)
        if oid and any(w in text for w in ('支付','退票','取消')):
            if not results:return call('railway_get_order',dict(order_id=oid[0]))
            if results[-1]['name']=='railway_get_order':
                if '退票' in text:return call('railway_refund_order',dict(order_id=oid[0],scope='FULL'))
                if '取消' in text:return call('railway_cancel_order',dict(order_id=oid[0]))
                return call('railway_pay_order',dict(order_id=oid[0],expected_total_fen=payload['total_fen']))
        qid=re.search(r'Q[a-f0-9]{32}',text)
        if qid and re.search('下单|建单|订票',text) and not results:
            names=re.search(r'乘客[：: ]*(.+)',text)
            if not names:return reply('请列出模拟乘客姓名，例如“为报价 Q… 下单，乘客：张三、李四”。')
            passengers=[x.strip() for x in re.split('[、,，]',names[1]) if x.strip()]
            return call('railway_create_order',dict(quote_id=qid[0],passengers=passengers,contact=CURRENT.get().owner_phone))
        if any(word in text for word in ('退票政策','退款政策','改签政策','手续费','退改签政策','退改规则')):
            return reply('D9 已批准方案B：改签后仍可退款；部分退款后可改签剩余 ACTIVE 乘客，也可继续退款。每名乘客最多一次成功退款，每订单最多一次成功改签。P01 以当前有效乘客价格快照为基数：>48小时5%，24至48小时10%，<24小时20%，整数分 half-up。以上仅为本地模拟规则，不代替真实铁路政策。')
        if any(word in text for word in ('经停','停靠站','中间站')):
            if results and isinstance(payload,dict) and isinstance(payload.get('data'),dict) and payload['data'].get('stops'):
                stops=payload['data']['stops']
                return reply('已读取真实静态经停：'+'；'.join(str(s['stop_name'])+' '+str(s.get('arrival_at') or s.get('departure_at') or '') for s in stops[:8])+'。静态时刻不代表实时开行。')
            return reply('请先查询具体车次，或直接使用“铁路查询与报价”面板查看经停站；不会猜测经停顺序。')
        match=re.search(r'(\d{4}-\d{2}-\d{2})\s*(.+?)(?:到|至)(.+?)(?:的?(?:车次|列车|火车|高铁)|(?:二等座|一等座|商务座)|[。！!]|$)',text)
        if match:
            day,origin,destination=match.groups()
            origin=re.sub(r'^(?:查询|查|从)\s*','',origin).strip();destination=destination.strip()
            date.fromisoformat(day)
            if not results:return call('railway_search_stations',dict(name=origin))
            stations=[json.loads(r['content']) for r in results if r['name']=='railway_search_stations']
            if any(len(r.get('data',[]))!=1 for r in stations):return reply('站点不存在或存在多个候选，请在铁路查询面板明确选择车站，避免猜测同名车站。')
            if len(stations)==1:return call('railway_search_stations',dict(name=destination))
            if len(results)==2:return call('railway_query_trips',dict(service_date=day,origin_stop_id=stations[0]['data'][0]['stop_id'],destination_stop_id=stations[1]['data'][0]['stop_id'],limit=20))
        if results:
            if isinstance(payload,list):return reply('已查询本人铁路模拟订单，共 '+str(len(payload))+' 笔。详情见订单列表。')
            if isinstance(payload,dict) and 'data' in payload:
                rows=payload['data'];n=len(rows) if isinstance(rows,list) else 1
                detail=''
                if isinstance(rows,list) and rows:
                    detail=' 例如：'+'；'.join(str(r.get('trip_short_name') or r.get('trip_id'))+' '+str(r.get('departure_at') or '')+'→'+str(r.get('arrival_at') or '') for r in rows[:3])+'。'
                return reply(f"静态数据查询结果：{payload.get('status')}，返回 {n} 条记录。{detail}静态时刻不代表实时开行、余票或官方票价，请在列表核对。")
            return reply('已读取实际工具结果。所有价格、库存及交易均为模拟，详情见面板。')
        return reply('铁路出行助手支持查询真实静态车站/车次/经停、咨询 D9 退改政策，以及本地模拟报价、建单、支付、改签和退款。交易必须由页面确认，模型不能自行确认。')
