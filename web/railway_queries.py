"""Original right rail queries; shared Registry, no model calls or fake Agent runs."""
from datetime import date,timedelta
import json,re,uuid
from web.railway_defaults import (DEMO_DESTINATION, DEMO_ORIGIN, DEMO_TRAIN, PREFERRED, classify,
                                  default_service_date, PAGE_LIMIT)
from web.result_rows import as_row, iter_rows
import streamlit as st
from target.v39.context import scope
from target.v39.registry import dispatch,service_scope
from target.execution_config import scope as effective_scope

ERRORS={'V39_TOOL_NOT_ALLOWED':'当前会话未开放此查询，请新建会话后重试。',
        'V39_CONFIG_MISMATCH':'配置已变化，请刷新后重新查询。',
        'INVALID_RAILWAY_ARGUMENTS':'查询条件不完整或格式不正确，请核对车站和日期。',
        'RAILWAY_INTERNAL_ERROR':'静态数据暂不可读取，请稍后重试；开发者工作空间保留诊断。'}


_TRIP_INTENT=('车票','票','车次','列车','高铁','动车','火车','余票','班次','有什么车','怎么走')
_UNSPECIFIED=('哪里','哪儿','什么地方','哪座城市')

# ---------------------------------------------------------------------------
# Natural-language route intake.
#
# A real customer sentence carries politeness, a name and a quantity around the
# two city names: 「我叫11，帮我买广州到深圳的票」.  The previous extractor ran a
# regex over a sentence that still had 「帮我买」 in front of the city, so it
# read the origin as 「帮我买广州」, the station lookup returned nothing, and the
# customer was told the request could not be understood.  The pair is now taken
# from the two Chinese runs that sit either side of 到/去/至/→ and the decorative
# words are trimmed off those runs; nothing is guessed beyond the sentence.
# ---------------------------------------------------------------------------
_ROUTE_PREFIX_NOISE=('帮我买','帮我订','帮忙买','帮忙订','然后','之后','顺便','那么','那就',
                     '帮我','帮忙','麻烦','请给我','请帮','请','给我','替我','我要','我想','想要',
                     '一张','两张','三张','四张','单程','往返','乘坐','坐','查询','查一下','查',
                     '看看','买','订','购','预订','从','我','想','要','再','就','的','了',
                     '下周','这周','本周','下个星期','下个月')
_ROUTE_SUFFIX_NOISE=('的高铁票','的火车票','的动车票','的车票','的汽车票','的票','车票','火车票',
                     '高铁票','动车票','票','车次','列车','火车','高铁','动车','余票','班次',
                     '二等座','一等座','商务座','座位','车次和','和余票','和','及','还有','座',
                     '多少钱','多久','多远','几点','什么时候','怎么走','怎么去','有什么',
                     '的','啊','呢','吧','了')
_DEST_MODIFIER=re.compile(
    r'^([\u4e00-\u9fa5]{2,8}?)(?=(?:的)?(?:高铁|动车|火车|列车|车次|车票|车|票|班次|余票|'
    r'二等座|一等座|商务座|座位|座|和|及|还有|多少钱|多久|多远|几点|什么时候|'
    r'怎么走|怎么去|有什么|的|啊|呢|吧|了)|$)')

# "2张广州到深圳" / "两张…": the quantity sits between the politeness and the
# city name, so it has to go before the city is read.
_QUANTITY=re.compile(r'^(?:\d+|[一二两三四五六七八九十]+)[张个位人]')
_CONNECTOR=re.compile(r'飞往|开往|到达|到|去|至|往|→|—|-')
_DATE_TOKEN=re.compile(r'\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}[日号]?|今天|今晚|明天|明早|明晚|'
                       r'后天|大后天|本?周[一二三四五六日天]|这周[一二三四五六日天]|'
                       r'下周[一二三四五六日天]|星期[一二三四五六日天]|下个月|本月|\d{1,2}[日号]')
_FILLER=re.compile(r'[\s，,。.！!？?、；;：:吧呀啊呢哦哈就那的好了吗嗯]+')
_WEEKDAY='一二三四五六日'


def strip_date_tokens(text):
    """The sentence with every date expression removed (city pair stays put)."""
    return _DATE_TOKEN.sub(' ',str(text or ''))


def resolve_day(text):
    """The day a customer means by 今天/明天/后天/周三/11月20日/2026-11-20."""
    t=str(text or '')
    today=default_service_date()
    m=re.search(r'\d{4}-\d{2}-\d{2}',t)
    if m:
        try:return date.fromisoformat(m.group(0))
        except ValueError:return None
    m=re.search(r'(\d{1,2})月(\d{1,2})[日号]?',t)
    if m:
        try:day=date(today.year,int(m.group(1)),int(m.group(2)))
        except ValueError:return None
        if day<today:
            try:day=date(today.year+1,int(m.group(1)),int(m.group(2)))
            except ValueError:return None
        return day
    if '大后天' in t:return today+timedelta(days=3)
    if '后天' in t:return today+timedelta(days=2)
    if any(w in t for w in ('明天','明早','明晚')):return today+timedelta(days=1)
    if any(w in t for w in ('今天','今晚')):return today
    m=re.search(r'(下|这|本)?(?:周|星期)([一二三四五六日天])',t)
    if m:
        target=_WEEKDAY.index('日' if m.group(2)=='天' else m.group(2))
        if m.group(1)=='下':
            next_monday=today+timedelta(days=7-today.weekday())
            return next_monday+timedelta(days=target)
        return today+timedelta(days=(target-today.weekday())%7)
    m=re.search(r'(\d{1,2})[日号]',t)
    if m:
        wanted=int(m.group(1))
        for month_offset in range(0,3):
            year=today.year+(today.month-1+month_offset)//12
            month=(today.month-1+month_offset)%12+1
            try:candidate=date(year,month,wanted)
            except ValueError:continue
            if candidate>=today:return candidate
    return None


def date_answer(text):
    """True when the message only adds a date ("明天", "11月20日", "明天的票")."""
    raw=str(text or '')
    if not raw.strip() or len(raw)>24 or not _DATE_TOKEN.search(_FILLER.sub('',raw)):return False
    rest=_FILLER.sub('',strip_date_tokens(raw))
    rest=re.sub(r'的车票|车票|车次|票|的','',rest)
    return not _FILLER.sub('',rest)


def _trim_origin(raw,digit_before=False):
    city=raw
    # "帮朋友买两张广州": throw away everything up to the buying verb first, so
    # the remaining run starts at the quantity (or the city itself).
    city=re.sub(r'^[^买订购]*[买订购]','',city) or city
    if digit_before and city[:1] in ('张','个','位','人'):
        city=city[1:]
    city=_QUANTITY.sub('',city)
    for _ in range(6):
        hit=next((w for w in _ROUTE_PREFIX_NOISE if len(city)>len(w) and city.startswith(w)),None)
        if not hit:break
        city=city[len(hit):]
    city=_QUANTITY.sub('',city)
    for word in ('出发','上车','走'):
        if len(city)>len(word) and city.endswith(word):city=city[:-len(word)]
    return city


def _trim_destination(raw):
    """The city at the START of the right-hand run; the rest is a modifier.

    Seat classes and 「车次和余票」 used to ride along into the destination, so
    the real station lookup received 「深圳的高铁二等座」 and found zero stops.
    The whole turn then fell through to an unrelated order answer.
    """
    city=str(raw or '')
    match=_DEST_MODIFIER.match(city)
    if match:return match.group(1)
    for _ in range(6):
        hit=next((w for w in _ROUTE_SUFFIX_NOISE if len(city)>len(w) and city.endswith(w)),None)
        if not hit:break
        city=city[:-len(hit)]
    return city


def route_hints(text):
    """(origin, destination) city names actually written in the sentence."""
    if not isinstance(text,str):return None
    t=strip_date_tokens(text).replace(' ','')
    for match in _CONNECTOR.finditer(t):
        left=t[:match.start()];right=t[match.end():]
        origin_run=re.search(r'([\u4e00-\u9fa5]+)$',left)
        destination_run=re.match(r'([\u4e00-\u9fa5]+)',right)
        if not origin_run or not destination_run:continue
        digit_before=bool(origin_run.start() and left[origin_run.start()-1].isdigit())
        origin=_trim_origin(origin_run.group(1),digit_before)[-8:]
        destination=_trim_destination(destination_run.group(1))[:8]
        if not (2<=len(origin)<=8 and 2<=len(destination)<=8):continue
        if origin==destination:continue
        if any(w in origin or w in destination for w in _UNSPECIFIED):continue
        if any(w in origin for w in ('票','班','次')) or any(w in destination for w in ('买','订','票')):continue
        return origin,destination
    return None


def _station_search_text(origin,destination):
    """Routing key for the offline planner; both cities are looked up for real."""
    return f'查询真实静态车站：{origin}、{destination}。展示候选站点供我选择。'


def _ask_key(session):return 'a_route_ask_'+str(getattr(session,'sid',''))


def pending_route_ask(session):
    """The city pair this page has already asked a date for (survives reruns)."""
    if session is None:return None
    try:ask=st.session_state.get(_ask_key(session))
    except Exception:return None
    return ask if isinstance(ask,dict) and ask.get('origin') and ask.get('destination') else None


def forget_route_ask(session):
    if session is None:return
    try:st.session_state.pop(_ask_key(session),None)
    except Exception:pass


def route_ask(session,text):
    """A city pair without a travel day: ask which day instead of refusing.

    Returns ``{'origin','destination','text'}`` or None.  The question is asked
    in the page (one tap answers it) and the answer re-enters the normal send
    path, so the station lookup, the trip board and the audit trail are the
    same ones a fully-worded request would use.
    """
    if not isinstance(text,str):return None
    t=text.strip()
    if not t or len(t)>120:return None
    if any(k in t for k in ('出发站编码','查询真实静态车站','分别查询真实静态车站','班次标识')):return None
    if re.search(r'(?:V39-|Q)[a-f0-9]{32}',t):return None
    if _TRAIN_NUMBER.search(t):return None
    if any(w in t for w in ('退票','退款','改签','取消','订单','支付','付款')):return None
    if any(w in t for w in _POLICY_WORDS) and re.search(r'[？?]|怎么|多少|规则|规定',t):return None
    if _DATE_TOKEN.search(t):return None
    pair=route_hints(t)
    if not pair:return None
    return dict(origin=pair[0],destination=pair[1],text=t)

# Short follow-up buttons / conversational continuations.  None of these match
# any route in the offline planner, so without an A-side intake they all fall
# through to the capability blurb at planner.py:110 (handover note 3.2 (3)).
_CONTROL_WORDS=('确认此','取消此','取消操作','取消模拟操作','不要','暂不','别买','别订','别付','查看技术细节')
_POLICY_WORDS=('政策','规则','规定','手续费','行李','费用','流程','截止时间','条件','边界','怎么算','怎么办理')
_ORDER_WORDS=('订单','支付','付款','退款','退票','改签','建单','下单','报价','出票','交易明细','订单状态')
_TRIP_WORDS=('行程','车次','经停','席别','余票','车票','高铁','火车','规划','比较','下一班','重试','查票','买票')

STATION_SHORTLIST=5
_MAIN_SUFFIX=('南','北','东','西')
# Stops that exist in the feed but are not what a traveller means by the city
# (metro-style, suburban, airport or intercity halts).  The raw tool result
# keeps every one of them; only the short list is filtered.
_MINOR_WORDS=('大学城','长隆','莲花山','机场','欢乐谷','世界之窗','科学城','金融城',
              '白云','坪山','松江','新塘')
# 演示口径：广州新塘属于城际通勤站，不是旅客说「广州」时指的车站。
# 只在车站选择短名单里剔除；静态库与工具结果原样保留。
_EXCLUDED_STATION_WORDS=('新塘',)
# Display ordering only (never used to pick a station): the terminal a
# traveller normally means when they say the city name.  Every city the demo
# offers needs an entry, otherwise its main station would not lead the list.
_DISPLAY_MAIN={'上海':'上海虹桥','杭州':'杭州东','北京':'北京南','广州':'广州南','深圳':'深圳北',
               '南京':'南京南','成都':'成都东','武汉':'武汉','长沙':'长沙南','西安':'西安北',
               '重庆':'重庆北','郑州':'郑州东','天津':'天津','苏州':'苏州','厦门':'厦门北',
               '合肥':'合肥南','济南':'济南西','青岛':'青岛北','沈阳':'沈阳北','昆明':'昆明南',
               '贵阳':'贵阳北','福州':'福州','南昌':'南昌西'}


def _city_hint(row):
    result=row.get('result') if isinstance(row.get('result'),dict) else {}
    params=result.get('query_parameters') or row.get('args') or {}
    return str(params.get('name') or '').strip()


def station_city_hint(row):
    """Public alias: the city keyword a station-search result was queried with."""
    return _city_hint(row)


def station_shortlist(candidates,city='',cap=STATION_SHORTLIST):
    """Only major passenger stations, exactly the set offered by the picker.

    The static feed returns every stop matching the keyword (10 for 广州, 6 for
    深圳, including 大学城 / 长隆 / 白云 / 机场 / 坪山).  A customer does not
    mean those when saying the city name, and a model that copies the whole
    feed into a markdown table buries the station they do mean.  The short
    list keeps the city's main terminal, the city-named station and the four
    direction stations, in that order.  Commuter and airport halts stay in the
    sealed tool result (and in the total count reported to the caller), never
    silently invented or deleted from the database.
    """
    seen=set();unique=[]
    for item in candidates or []:
        if not isinstance(item,dict) or not item.get('stop_id'):continue
        name=str(item.get('stop_name') or '')
        if not name or name in seen:continue
        if any(word in name for word in _EXCLUDED_STATION_WORDS):continue
        seen.add(name);unique.append(item)
    preferred=_DISPLAY_MAIN.get(city,'') or (PREFERRED.get(city,'') if city else '')
    def major(name):
        if not city:return True
        if preferred and name==preferred:return True
        if name==city:return True
        return name.startswith(city) and name[len(city):] in _MAIN_SUFFIX
    def rank(pair):
        index,item=pair;name=str(item.get('stop_name') or '')
        minor=any(w in name for w in _MINOR_WORDS)
        if preferred and name==preferred:return (0,index)
        if city and name==city:return (1,index)
        if city and name.startswith(city) and name[len(city):] in _MAIN_SUFFIX:return (2,index)
        if city and name.startswith(city) and not minor:return (3,index)
        return (4,index)
    ordered=[item for _,item in sorted(enumerate(unique),key=rank)]
    kept=[item for item in ordered if major(str(item.get('stop_name') or ''))]
    # A keyword that is not a city name (e.g. 长隆) must not clear every option.
    if not kept:kept=ordered
    return kept[:cap],len(unique)


def passenger_hint(text):
    """Passenger name stated in the request ("我的名字是 qq")."""
    if not isinstance(text,str):return ''
    m=re.search(r'(?:我的名字是|我的名字叫|我叫|乘客(?:是|为)?[：:]?|姓名[：:]?)\s*'
                r'([\u4e00-\u9fa5]{2,4}|[A-Za-z][A-Za-z0-9]{0,11})',text)
    return m.group(1) if m else ''



def _pending_order(session):
    """Read a real pending-payment order from the authoritative snapshot."""
    try:
        from web.business_state import current
        rail=(current(session).get('railway') or {})
        for o in rail.get('orders') or []:
            if isinstance(o,dict) and o.get('order_status')=='PENDING_PAYMENT' and o.get('order_id'):
                return o
    except Exception:
        pass
    return None


_TRAIN_NUMBER=re.compile(r'(?<![A-Za-z0-9])([GDCZTK]\d{1,6})(?![A-Za-z0-9])')


# "继续完成支付" is a payment continuation, not a policy question and not a
# train query.  The offline planner cannot produce a PAY proposal (its first
# step is always railway_get_order, whose payload already carries the
# CREATE_ORDER proposal_id, so it stops at "已生成操作确认卡" without calling
# railway_pay_order).  The page therefore creates the PAY card itself through
# the same trusted page-operation path used by 建单/退票.
_PAY_INTENT=('支付','付款','去付','结账','付钱')
# Single characters used to be on this list (e.g. 别 / 没有); they silently
# swallowed harmless sentences such as 「帮我支付」 and 「还没有付款」.  Only
# whole negative/question phrases are excluded now.
_PAY_NOT_INTENT=('退','改签','取消','手续费','政策','规则','规定','怎么','如何','为什么',
                 '？','?','不要','不用','不付','不支付','不想支付','别付','失败','方式',
                 '多少','什么时候','在哪','能不能','是否')


def payment_intent(text):
    """True only for a short, unqualified request to pay, not a question.

    Used by the send path so a payment continuation never falls through to the
    offline planner (which cannot produce a PAY proposal) and never leaves the
    misleading 「现在不能确认」 hint behind.
    """
    if not isinstance(text,str):return False
    t=text.strip()
    if not t or len(t)>60:return False
    if not any(w in t for w in _PAY_INTENT):return False
    return not any(w in t for w in _PAY_NOT_INTENT)


def payment_order(session,text):
    """The pending order a plain "continue paying" sentence refers to."""
    if session is None or getattr(session,'read_only',False):return None
    if not payment_intent(text):return None
    return _pending_order(session)


def open_payment_card(session,order,request_text=''):
    """Create the PAY confirmation card with a real tool call; never a blurb.

    Returns True when a card exists and the page must rerun (the card with the
    amount and the QR lives in the conversation「待确认铁路操作」card).
    Confirmation itself still happens on the page, so nothing is paid here.
    """
    if session is None or getattr(session,'read_only',False) or not isinstance(order,dict):return False
    order_id=str(order.get('order_id') or '')
    if not order_id:return False
    rail=(current_rail(session))
    existing=[p for p in (rail.get('pending_proposals') or [])
              if p.get('action')=='PAY' and str(p.get('order_id') or '')==order_id]
    if existing:
        st.info('这张订单已经有一张待确认的支付卡（'+str(existing[-1].get('proposal_id'))+
                '），请在页面核对金额后确认；没有重复生成。')
        return True
    total=order.get('total_fen')
    args={'order_id':order_id}
    if type(total) is int:args['expected_total_fen']=total
    try:
        from web.business_actions import invoke
        result=invoke(session,'railway_pay_order',args)
    except Exception as exc:
        detail=str(exc) if isinstance(exc,ValueError) else '页面业务暂不可用'
        st.warning('支付确认卡没有生成：'+detail+'；订单仍未支付，可以稍后再试。')
        return False
    receipts=getattr(session,'business_receipts',[])
    if receipts:
        receipts[-1].update(action='PAY',pay_request=str(request_text or ''),
                            pay_total_fen=total if type(total) is int else None)
    if isinstance(result,dict) and result.get('status')=='CONFIRMATION_REQUIRED':
        return True
    st.warning('支付确认卡没有生成；订单仍未支付，请核对订单状态后再试。')
    return False


# ---------------------------------------------------------------------------
# Post-payment aftercare: a paid order must stay actionable.  A page button (or
# a short natural-language request) creates a REAL V3.9 REFUND / CHANGE
# proposal through the trusted page-operation path; the customer still confirms
# it in 待确认铁路操作.  Nothing here executes a trade.
# ---------------------------------------------------------------------------
_AFTERCARE_NOT=('手续费','怎么','如何','规则','政策','费用','流程','条件','多少','吗','？','?',
                '不要','别','不退','查询','看看','能不能','可以吗')
_AFTERCARE_REFUND=('退票','退款','退了','不坐了')
_AFTERCARE_CHANGE=('改签','改到','换一班车','换个车次','换车次')


def aftercare_intent(text):
    """Return 'REFUND' / 'CHANGE' for a short, unqualified request, else ''."""
    if not isinstance(text,str):return ''
    t=text.strip()
    if not t or len(t)>24 or any(w in t for w in _AFTERCARE_NOT):return ''
    if any(w in t for w in _AFTERCARE_CHANGE):return 'CHANGE'
    if any(w in t for w in _AFTERCARE_REFUND):return 'REFUND'
    return ''


def paid_orders(session):
    """Committed V3.9 orders that can still be refunded or changed."""
    if session is None or getattr(session,'read_only',False):return []
    rail=current_rail(session)
    return [o for o in (rail.get('orders') or [])
            if isinstance(o,dict) and o.get('order_id')
            and o.get('order_status') in ('PAID','CHANGED')
            and o.get('payment_status')=='SUCCEEDED']


def _day_trains(session, order):
    """Every real departure on the order's own route and date (static timetable).

    The tool result in the session only holds one 50-row page, which made a
    whole day look like three trains.  The static dataset is read-only, so the
    page may read the full day directly and still show only real `trip_id`,
    real clock times and real stop ids.
    """
    static=getattr(getattr(session,'_v39_service',None),'static',None)
    key=(order.get('service_date'),order.get('origin_stop_id'),order.get('destination_stop_id'))
    if static is None or not all(key):return []
    cache=getattr(session,'_day_train_cache',None)
    if cache is None:
        cache={};session._day_train_cache=cache
    if key in cache:return cache[key]
    rows=[];cursor=None
    for _ in range(8):
        try:
            page=static.trips(key[0],key[1],key[2],limit=50,cursor=cursor)
        except (ValueError,TypeError,OSError):
            break
        data=page.get('data') or []
        rows.extend(t for t in data if isinstance(t,dict))
        cursor=page.get('next_cursor')
        if not cursor or not data:break
    cache[key]=rows
    return rows


def _clock(train):
    from datetime import datetime
    raw=str(train.get('departure_at') or '')
    try:return datetime.fromisoformat(raw)
    except ValueError:return None


def change_candidates(session, order, wanted_number=None, headway_minutes=60, limit=16):
    """Real alternative trains for a paid order.

    Prefer same-day G trains at least an hour away.  Demo routes often have only
    one such train, which used to make 改签 look broken; in that case look at
    the next three service days and allow D/C/G trains.  Every row still comes
    from the static timetable or a real query result, never a made-up trip_id.
    """
    wanted=str(wanted_number or '').upper()
    args=dict(service_date=order.get('service_date'),origin_stop_id=order.get('origin_stop_id'),
              destination_stop_id=order.get('destination_stop_id'))
    same_day=_day_trains(session,order)
    base=None
    for train in same_day:
        if str(train.get('trip_id'))==str(order.get('trip_id')):base=_clock(train);break
    def thin(rows, *, exclude_same_trip=True, use_headway=True):
        rows=[t for t in rows if isinstance(t,dict)]
        if exclude_same_trip:
            rows=[t for t in rows if str(t.get('trip_id'))!=str(order.get('trip_id'))]
        if wanted:
            rows=[t for t in rows if str(t.get('trip_short_name') or '').upper()==wanted] or rows
        rows.sort(key=lambda t:str(t.get('departure_at') or ''))
        if use_headway and base is not None:
            rows=[t for t in rows if _clock(t) is None
                  or abs((_clock(t)-base).total_seconds())/60>=headway_minutes]
        kept=[];last=None
        for train in rows:
            clock=_clock(train)
            if not use_headway or clock is None:
                kept.append(train)
            elif last is None or (clock-last).total_seconds()/60>=headway_minutes:
                kept.append(train);last=clock
            if len(kept)>=limit:break
        return kept
    strict=[t for t in same_day if str(t.get('trip_short_name') or '').upper().startswith('G')]
    kept=thin(strict)
    if kept:return kept,args
    # Same-day board empty: try the next three service days with all train types.
    raw_day=str(order.get('service_date') or '')
    try:base_day=date.fromisoformat(raw_day)
    except ValueError:base_day=None
    if base_day is not None:
        for offset in range(1,4):
            day=(base_day+timedelta(days=offset)).isoformat()
            probe=dict(order,service_date=day)
            rows=thin(_day_trains(session,probe),exclude_same_trip=False,use_headway=False)
            if rows:return rows,dict(args,service_date=day)
    # Last resort: a real prior query for the same route/date, without G-only filter.
    from web.result_rows import iter_rows
    rows=list(iter_rows(getattr(session,'results',[]) or []))
    rows+=list(iter_rows(getattr(session,'railway_queries',[]) or []))
    for raw in reversed(rows):
        if not isinstance(raw,dict) or raw.get('tool')!='railway_query_trips':continue
        result=raw.get('result') if isinstance(raw.get('result'),dict) else {}
        query=result.get('query_parameters') if isinstance(result.get('query_parameters'),dict) else (raw.get('args') or {})
        if not all(query.get(k)==order.get(k) for k in
                   ('service_date','origin_stop_id','destination_stop_id')):continue
        relaxed=thin(result.get('data') or [])
        if relaxed:return relaxed,args
    return [],args


def refund_terms(session, order, leg=None):
    """The P01 fee this order would pay for a refund right now.

    Same approved policy the refund confirmation card uses (5% above 48h, 10%
    from 24h to 48h, 20% below 24h, half-up on the current active fare
    snapshot).  Read-only: it never creates a proposal or moves money.
    """
    from datetime import datetime
    service=getattr(session,'_v39_service',None)
    leg=leg or journey(session,order)
    departure=str((leg or {}).get('departure_at') or '')
    if not departure or service is None:return None
    fares=[i['fare_fen'] for i in (order.get('items') or [])
           if isinstance(i,dict) and i.get('item_status','ACTIVE')=='ACTIVE' and type(i.get('fare_fen')) is int]
    if not fares:return None
    try:
        now=service.now()
        fees=service.policy.refund(fares,departure,now.isoformat())
    except (ValueError,TypeError,KeyError,AttributeError):
        return None
    seconds=(datetime.fromisoformat(departure)-now).total_seconds()
    return dict(rate_bp=5 if seconds>172800 else 10 if seconds>=86400 else 20,
                amount_fen=sum(f['amount_fen'] for f in fees),
                fee_fen=sum(f['fee_fen'] for f in fees),
                net_fen=sum(f['net_fen'] for f in fees))


def change_preview(session, order, train, args):
    """Real fare quote for the chosen target train: new fare and difference.

    Nothing is reserved or ordered here; ``railway_quote_fare`` and
    ``railway_check_inventory`` are the same read-only steps the booking flow
    uses, so the new fare, the difference and the remaining seats are facts.
    """
    if not isinstance(train,dict) or not train.get('trip_id'):return None
    seat=order.get('seat_class') or 'SECOND'
    count=order.get('active_item_count')
    if type(count) is not int:
        count=sum(1 for i in (order.get('items') or [])
                  if isinstance(i,dict) and i.get('item_status','ACTIVE')=='ACTIVE') or 1
    try:
        from web.business_actions import invoke
        quote=invoke(session,'railway_quote_fare',dict(
            trip_id=str(train['trip_id']),service_date=args.get('service_date'),
            origin_stop_id=args.get('origin_stop_id'),
            destination_stop_id=args.get('destination_stop_id'),
            seat_class=seat,passenger_count=count))
    except Exception:
        return None
    total=((quote or {}).get('quote') or {}).get('total_fen')
    if type(total) is not int:return None
    available=None
    try:
        inventory=invoke(session,'railway_check_inventory',dict(
            trip_id=str(train['trip_id']),service_date=args.get('service_date'),
            origin_stop_id=args.get('origin_stop_id'),
            destination_stop_id=args.get('destination_stop_id'),
            seat_class=seat,quantity=count))
        if isinstance(inventory,dict) and type(inventory.get('available')) is int:
            available=inventory['available']
    except Exception:
        available=None
    return dict(total_fen=total,passenger_count=count,seat_class=seat,available=available,
                difference_fen=total-int(order.get('total_fen') or 0))



def _proposal_for(session, action, order_id):
    rail=current_rail(session)
    return next((p for p in (rail.get('pending_proposals') or [])
                 if p.get('action')==action and str(p.get('order_id') or '')==str(order_id)),None)


def open_refund_card(session, order, request_text=''):
    """Create the real REFUND proposal. Returns (ok, proposal_id, message)."""
    oid=str((order or {}).get('order_id') or '')
    if not oid:return False,None,'订单信息不完整，请重新查询订单。'
    existing=_proposal_for(session,'REFUND',oid)
    if existing:
        return True,existing.get('proposal_id'),'已生成退票确认卡，请在主对话里查看确认卡并确认。'
    try:
        from web.business_actions import invoke
        result=invoke(session,'railway_refund_order',dict(order_id=oid,scope='FULL'))
    except Exception as exc:
        detail=str(exc) if isinstance(exc,ValueError) else '页面业务暂不可用'
        return False,None,'退票确认卡没有生成：'+detail+'；订单状态未改变。'
    if isinstance(result,dict) and result.get('status')=='CONFIRMATION_REQUIRED':
        return True,result.get('proposal_id'),'已生成退票确认卡，请在主对话里查看退款金额并确认。'
    return False,None,'退票确认卡没有生成，请核对订单状态后再试。'


def open_change_card(session, order, train, args, request_text=''):
    """Quote a real alternative train, then create the real CHANGE proposal."""
    oid=str((order or {}).get('order_id') or '')
    if not oid or not isinstance(train,dict) or not train.get('trip_id'):
        return False,None,'请先选定要改签到的车次。'
    trip_id=str(train['trip_id'])
    existing=_proposal_for(session,'CHANGE',oid)
    if existing:
        return True,existing.get('proposal_id'),'已生成改签确认卡，请在主对话里查看确认卡并确认。'
    seat=order.get('seat_class') or 'SECOND'
    day=args.get('service_date') or order.get('service_date')
    origin=args.get('origin_stop_id') or order.get('origin_stop_id')
    destination=args.get('destination_stop_id') or order.get('destination_stop_id')
    count=order.get('active_item_count')
    if type(count) is not int:
        count=sum(1 for i in (order.get('items') or [])
                  if isinstance(i,dict) and i.get('item_status','ACTIVE')=='ACTIVE') or 1
    fare_args=dict(trip_id=trip_id,service_date=day,origin_stop_id=origin,
                   destination_stop_id=destination,seat_class=seat,passenger_count=count)
    try:
        from web.business_actions import invoke
        quote=invoke(session,'railway_quote_fare',fare_args)
        quote_id=((quote or {}).get('quote') or {}).get('quote_id')
        if not quote_id:return False,None,'目标车次暂不可报价，请换一班再试。'
        result=invoke(session,'railway_change_order',dict(
            order_id=oid,target_quote_id=quote_id,target_trip_id=trip_id,
            target_service_date=day,target_origin_stop_id=origin,
            target_destination_stop_id=destination,target_seat_class=seat))
    except Exception as exc:
        detail=str(exc) if isinstance(exc,ValueError) else '页面业务暂不可用'
        return False,None,'改签确认卡没有生成：'+detail+'；订单状态未改变。'
    if isinstance(result,dict) and result.get('status')=='CONFIRMATION_REQUIRED':
        number=str(train.get('trip_short_name') or trip_id)
        return True,result.get('proposal_id'),'已生成改签到 '+number+' 的确认卡，请在主对话里查看差价并确认。'
    return False,None,'改签确认卡没有生成，请核对订单状态后再试。'


def _hhmm(value):
    raw=str(value or '')
    if not raw:return ''
    parts=raw.split(':')
    if len(parts)<2:return raw
    try:minutes=int(parts[0])*60+int(parts[1])
    except ValueError:return raw
    return f'{minutes//60%24:02d}:{minutes%60:02d}'


def _duration(start, end):
    def minutes(v):
        parts=str(v or '').split(':')
        if len(parts)<2:return None
        try:return int(parts[0])*60+int(parts[1])
        except ValueError:return None
    a,b=minutes(start),minutes(end)
    if a is None or b is None or b<=a:return ''
    delta=b-a
    hours,rest=divmod(delta,60)
    return (str(hours)+' 小时 '+str(rest)+' 分') if hours else (str(rest)+' 分')


def journey(session, order):
    """Real leg for the ordered trip: station names, clock times, duration.

    Everything comes from the static timetable the order was created against;
    missing pieces stay empty rather than being filled with guesses.
    """
    from datetime import date as _date
    static=getattr(getattr(session,'_v39_service',None),'static',None)
    train=str(order.get('trip_id') or '')
    origin=str(order.get('origin_stop_id') or '')
    destination=str(order.get('destination_stop_id') or '')
    day=str(order.get('service_date') or '')
    out=dict(train=train,origin=origin,destination=destination,depart='',arrive='',
             duration='',date=day,date_label=day,departure_at='')
    if static is not None and order.get('trip_id') and origin and destination and day:
        try:
            info=static.interval(str(order['trip_id']),day,origin,destination)
            out['train']=str((info.get('trip') or {}).get('trip_short_name') or train)
            out['depart']=_hhmm((info.get('origin') or {}).get('departure_time'))
            out['arrive']=_hhmm((info.get('destination') or {}).get('arrival_time'))
            out['duration']=_duration((info.get('origin') or {}).get('departure_time'),
                                      (info.get('destination') or {}).get('arrival_time'))
            out['departure_at']=str((info.get('origin') or {}).get('departure_at') or '')
        except (ValueError,TypeError,KeyError,AttributeError):
            pass
    if static is not None:
        for key,stop in (('origin',origin),('destination',destination)):
            try:
                found=(static.station(stop) or {}).get('data') or {}
                if found.get('stop_name'):out[key]=str(found['stop_name'])
            except (ValueError,TypeError,OSError):
                pass
    try:
        weekday='一二三四五六日'[_date.fromisoformat(day).weekday()]
        out['date_label']=day+' 周'+weekday
    except ValueError:
        pass
    return out


def current_rail(session):
    """Committed railway snapshot for the active session (never a cached copy)."""
    try:
        from web.business_state import current
        return (current(session).get('railway') or {})
    except Exception:
        return {}


def _railway_rows(session):
    if session is None:return []
    out=[]
    for raw in reversed(list(iter_rows([getattr(session,'results',[]),getattr(session,'railway_queries',[])]))):
        row=as_row(raw)
        if row:out.append(row)
    return out


def _context_trip(session,number):
    """A train the conversation already returned, with real stop codes."""
    for row in _railway_rows(session):
        if not row.get('ok') or row.get('tool')!='railway_query_trips':continue
        result=row.get('result') if isinstance(row.get('result'),dict) else {}
        params=result.get('query_parameters') or row.get('args') or {}
        if not (params.get('origin_stop_id') and params.get('destination_stop_id')):continue
        for train in result.get('data') or []:
            if isinstance(train,dict) and str(train.get('trip_short_name') or '')==str(number):
                return row,train,params
    return None


def _last_route(session):
    """Most recent real station pair, used instead of a hard-coded sample city."""
    for row in _railway_rows(session):
        if not row.get('ok') or row.get('tool')!='railway_query_trips':continue
        result=row.get('result') if isinstance(row.get('result'),dict) else {}
        params=result.get('query_parameters') or row.get('args') or {}
        if params.get('origin_stop_id') and params.get('destination_stop_id'):
            return str(params.get('service_date') or default_service_date().isoformat()),params['origin_stop_id'],params['destination_stop_id']
    return None


def route_text(day,origin_stop_id,destination_stop_id,session=None):
    """Routing key for the offline planner (B-owned): day + both stop codes."""
    names={}
    try:
        from web.railway_cards import names_for
        names=names_for(session) if session is not None else {}
    except Exception:
        names={}
    return (f'查询{day} {names.get(origin_stop_id,origin_stop_id)}到'
            f'{names.get(destination_stop_id,destination_stop_id)}的铁路车次；'
            f'出发站编码{origin_stop_id}，到达站编码{destination_stop_id}。')


def _followup_route(text,session):
    """Route an otherwise-unroutable sentence to a REAL backend tool call.

    The reply the customer then sees is produced by the backend from the tool
    result, not by a static blurb.  Writes still end in an in-conversation
    confirmation proposal; nothing is executed without the page confirmation.
    """
    t=text.strip()
    if not t:return text,''
    if any(w in t for w in _CONTROL_WORDS) and len(t)<24:return text,''
    # 1) Continue paying a real pending order -> get_order then pay_order proposal.
    if any(w in t for w in ('支付','付款')):
        order=_pending_order(session)
        if order:
            return '继续为订单 '+str(order['order_id'])+' 完成支付',''
    # 2) Policy / fee questions -> real policy retrieval.
    if any(w in t for w in _POLICY_WORDS):
        return '查询项目示例政策：'+t,''
    # 3) Order / transaction continuations -> real order query.
    if any(w in t for w in _ORDER_WORDS):
        return '查询我的订单',''
    # 4) Trip continuations -> re-query the route this conversation already
    #    used.  Falling back to a hard-coded sample city pair made the answer
    #    contradict the cards above it (handover note 2.3/2.5).
    if any(w in t for w in _TRIP_WORDS):
        route=_last_route(session)
        if route:
            day,origin,destination=route
            # "后天的车次有哪些" keeps the route and moves it to the day the
            # customer just named, instead of re-asking the old one.
            said=resolve_day(t)
            if said:day=said.isoformat()
            return route_text(day,origin,destination,session),day
        return text,''
    # 5) A bare date after a train board ("后天的呢") moves the same route to
    #    that day instead of starting over or falling back to a blurb.
    if date_answer(t):
        route=_last_route(session)
        if route:
            day=resolve_day(t)
            if day:
                _d,origin,destination=route
                return route_text(day.isoformat(),origin,destination,session),day.isoformat()
    return text,''


def normalize_chat_text(text,session=None):
    """A-side intake: turn a plain customer sentence into a real tool query.

    The offline planner (B-owned) only routes dated, station-code-shaped text;
    without this intake, ``我要买广州去深圳的车票`` produces **zero** tool calls
    and only a capability blurb (handover note 3.2 ③).  The user workspace
    rewrites such a sentence into a real ``railway_search_stations`` request so
    the backend actually queries, then offers an explicit stop_id choice in the
    conversation (see ``chat_station_picker``).  Stations are never guessed.

    ``session`` supplies the authoritative order snapshot: a short "continue
    paying" follow-up becomes a real get_order -> pay_order proposal instead of
    a capability blurb, so the reply the customer reads is generated by the
    backend from an actual tool result.  Any other unroutable sentence is
    handed to ``_followup_route`` the same way.

    Returns ``(agent_text, service_date)``; service_date is '' when the text was
    already routable and no rewrite happened.  The customer's original wording
    stays on the operation row and in the user bubble (conversation.py).
    """
    if not isinstance(text,str):return text,''
    t=text.strip()
    # Already routable: explicit station codes, order/quote ids, paging keys.
    if (any(k in t for k in ('出发站编码','查询真实静态车站','分别查询真实静态车站','班次标识')) or
        re.search(r'(?:V39-|Q)[a-f0-9]{32}',t)):
        # "买单张指定车次" carries the train number inside the routed text, so
        # the card list below can select exactly that train once it renders.
        if session is not None and '出发站编码' in t:
            carried=_TRAIN_NUMBER.search(t)
            if carried:session.pending_select_number=carried.group(1)
        return t,''
    # "帮我买 C7005，我的名字是 qq" names one concrete train.  Look it up in
    # this conversation's own results and continue on its real station pair,
    # instead of falling back to a sample city pair (handover note 2.3/2.5).
    number=_TRAIN_NUMBER.search(t)
    if number:
        # Only a date the customer actually said replaces the date on the card:
        # the card's own service_date is the one they were looking at.
        target=resolve_day(t)
        found=_context_trip(session,number.group(1))
        if found:
            _row,_train,params=found
            card_day=str(params.get('service_date') or default_service_date().isoformat())
            day=target.isoformat() if target else card_day
            if session is not None and day==card_day:
                session.pending_select_number=number.group(1)
            return route_text(day,params['origin_stop_id'],params['destination_stop_id'],session),day
        # Not seen yet: a real train-number lookup, then the customer can pick.
        day=(target or default_service_date()).isoformat()
        return f'查询{day} {number.group(1)}的真实静态车次。',day
    # A date answers the page's own question ("请问您想要哪天的车票？"): the city
    # pair is the one the customer already gave.  Refund / change wording keeps
    # its own route even when a date is mentioned.
    asking=pending_route_ask(session)
    said=resolve_day(t)
    if (asking and said and not route_hints(t)
            and not any(w in t for w in ('退','改签','订单','支付','付款'))):
        forget_route_ask(session)
        return _station_search_text(asking['origin'],asking['destination']),said.isoformat()
    # A named city pair is a trip request even when the customer left the date
    # out; the page asks for the day (route_ask) instead of refusing.  Refund /
    # change / fee wording is excluded so those keep their own route.
    pair=None if any(w in t for w in ('退票','退款','改签','手续费','政策','规则')) else route_hints(t)
    if pair:
        day=resolve_day(t) or default_service_date()
        return _station_search_text(pair[0],pair[1]),day.isoformat()
    if not any(w in t for w in _TRIP_INTENT):
        # A plain policy question must also reach a real tool instead of the
        # offline planner's high-risk-operation blurb.
        if (re.search(r'[？?]|多久|怎么|多少|能否|可以吗|费率|规则|规定',t) and
                any(w in t for w in ('锁座','退票','改签','行李','手续费','政策','退款','超重','支付时限'))):
            return '查询项目示例政策：'+t,''
        return _followup_route(t,session)
    # Trip wording without any recognisable city pair ("帮我买张票"): continue
    # the route this conversation is already on, if there is one.
    return _followup_route(t,session)


def resolve_train_number(session,row):
    """Turn a train-number lookup into a bookable route query, without asking.

    A number-only lookup tells us the train runs, not where it starts or ends.
    Its own stop list is a real tool result, so the next two steps (stops, then
    the route query with those two termini) run on data instead of a guess.
    """
    if session is None or getattr(session,'read_only',False):return False
    result=row.get('result') if isinstance(row.get('result'),dict) else {}
    params=result.get('query_parameters') or row.get('args') or {}
    number=str(params.get('train_no') or '')
    trains=[t for t in (result.get('data') or []) if isinstance(t,dict) and t.get('trip_id')]
    if not number or not trains:return False
    day=str(params.get('service_date') or default_service_date().isoformat())
    trip_id=trains[0]['trip_id']
    key='a_train_number_'+session.sid+'_'+str(trip_id)
    if st.session_state.get(key+'_done'):return False
    stops_row=next((r for r in _railway_rows(session) if r.get('ok') and r.get('tool')=='railway_trip_stops'
                    and str((((r.get('result') or {}).get('data') or {}).get('trip') or {}).get('trip_id'))==str(trip_id)),None)
    if stops_row is None:
        from web.interaction import busy
        if st.session_state.get(key) or busy(session):return False
        if not submit(session,'railway_trip_stops',dict(trip_id=trip_id,service_date=day)):return False
        st.session_state[key]=True
        st.rerun()
        return True
    stops=[s for s in (((stops_row.get('result') or {}).get('data') or {}).get('stops') or []) if isinstance(s,dict) and s.get('stop_id')]
    if len(stops)<2:return False
    from web.interaction import busy,enqueue
    if busy(session):return False
    # The train number rides inside the routed text so the intake can mark this
    # exact train for selection when the cards render.
    text=route_text(day,stops[0]['stop_id'],stops[-1]['stop_id'],session)
    text=text[:-1]+'；指定车次'+number+'。' if text.endswith('。') else text+'；指定车次'+number
    if not enqueue(session.sid,text,'railway:railway_query_trips'):return False
    st.session_state[key+'_done']=True
    st.rerun()
    return True


def chat_station_picker(session, rows_source=None):
    """In-conversation next step: pick explicit stop_ids, then query trips.

    `rows_source` is the CURRENT turn's tool batch.  Reading the whole session
    made a failed station lookup borrow a successful one from an older turn:
    after 「广州到深圳」 the picker offered 杭州东 → 广州南 under the newest
    message.  Only the latest turn may own this widget.
    A model proposal is not evidence of execution; the trip query below goes
    through the same unified send path, so the right rail shows the same
    run_id as the chat card.
    """
    if session is None or getattr(session,'read_only',False):return
    source=rows_source if rows_source is not None else getattr(session,'results',[])
    rows=[]
    railway_order=[]
    for raw in iter_rows(source):
        row=as_row(raw)
        if row and row.get('tool') in ('railway_search_stations','railway_query_trips'):
            railway_order.append(row.get('tool'))
        if (row and row.get('ok') and row.get('tool')=='railway_search_stations'
                and isinstance(row.get('result'),dict) and row['result'].get('data')):
            rows.append(row)
    if len(rows)<2:return
    # The picker is the *next step* only while the two station searches are the
    # latest railway evidence.  Once a train query has run, asking the customer
    # to pick stations again is a redundant step (client handover note 2.3).
    if railway_order[-2:]!=['railway_search_stations','railway_search_stations']:return
    origins=[x for x in rows[-2]['result']['data'] if isinstance(x,dict) and x.get('stop_id')]
    destinations=[x for x in rows[-1]['result']['data'] if isinstance(x,dict) and x.get('stop_id')]
    if not origins or not destinations:return
    day=st.session_state.get('a_trip_day_'+session.sid) or default_service_date().isoformat()
    short_o,_=station_shortlist(origins,_city_hint(rows[-2]))
    short_d,_=station_shortlist(destinations,_city_hint(rows[-1]))
    if not short_o or not short_d:return
    key='chat_stations_'+session.sid+'_'+str(rows[-1].get('id') or len(rows))
    if st.session_state.get(key+'_done'):return
    with st.container(border=True,key='chat_station_pick'):
        st.markdown('**继续：选择出发站与到达站**')
        st.caption('只列出主要车站，选好后我查这一天的车次。')
        fmt=lambda r:str(r.get('stop_name') or '未命名车站')
        left,right=st.columns(2)
        chosen_o=left.selectbox('出发站',short_o,format_func=fmt,key=key+'_o')
        chosen_d=right.selectbox('到达站',short_d,format_func=fmt,key=key+'_d')
        if st.button('按所选车站查询车次',key=key+'_go',width='stretch'):
            if not isinstance(chosen_o,dict) or not isinstance(chosen_d,dict):
                st.warning('请明确选择出发站与到达站。')
            elif chosen_o['stop_id']==chosen_d['stop_id']:
                st.warning('出发站和到达站不能相同，请重新选择。')
            elif submit(session,'railway_query_trips',dict(service_date=day,
                         origin_stop_id=chosen_o['stop_id'],destination_stop_id=chosen_d['stop_id'],
                         limit=PAGE_LIMIT)):
                st.session_state[key+'_done']=True
                st.rerun()
            else:
                st.warning(st.session_state.pop('feature_notice_'+session.sid,'查询尚未发送，请稍后再试。'))


def query_text(session,name,args):
    """Build the wording for one railway request.

    These phrases are routing keys for the offline planner (B-owned), including
    '查询真实静态车站：' and the station-code suffix.  Keep them verbatim until
    the integrator updates target/v39/planner.py together with this module.
    """
    from web.railway_cards import names_for
    names=names_for(session);day=args.get('service_date')
    if name=='railway_search_stations':text='查询真实静态车站：'+args['name']+'。'
    elif name=='railway_trip_stops':
        trains=[t for row in iter_rows(session.results) if row.get('tool')=='railway_query_trips' for t in (row.get('result') or {}).get('data',[])]
        number=next((t.get('trip_short_name') for t in trains if t.get('trip_id')==args['trip_id']),None)
        text=f'查询{number or "已选班次"}在{day}的完整经停站；班次标识{args["trip_id"]}。'
    elif args.get('train_no'):text=f'查询{day} {args["train_no"]}的真实静态车次。'
    else:text=f'查询{day} {names.get(args["origin_stop_id"],args["origin_stop_id"])}到{names.get(args["destination_stop_id"],args["destination_stop_id"])}的铁路车次；出发站编码{args["origin_stop_id"]}，到达站编码{args["destination_stop_id"]}。'
    if name!='railway_search_stations' and args.get('cursor') is not None:text+=f'从第{int(args["cursor"])+1}条开始，每页{args.get("limit",PAGE_LIMIT)}条。'
    return text


def submit(session,name,args):
    """User intent only; the current Agent chooses and executes authorized tools."""
    from web.interaction import enqueue
    return enqueue(session.sid,query_text(session,name,args),'railway:'+name)

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
    # Which turn produced this board.  Every board used to be painted after the
    # newest reply, so an older 170-service list looked like the answer to the
    # message the customer had just typed.  History has not been appended yet
    # while the tools run, so the length is exactly the index of the turn that
    # is being produced; boards from page buttons clamp to the newest turn.
    if isinstance(row,dict) and not isinstance(row.get('turn'),int):
        row['turn']=len(getattr(session,'history',[]) or [])
    session.railway_queries.append(row)
    from web.railway_followups import register
    register(session,row)

def result_card(row, session=None, latest=False):
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
        # Pagination lives in the card header (railway_cards.trips_view), so the
        # controls never end up hidden below the collapsed train list.
        trips_view(row,session,latest=latest)
        return
    if name=='railway_trip_stops':
        st.markdown('### 沿途经停')
        stops_view(result,(result.get('query_parameters') or row.get('args',{})).get('service_date'));return
    if name=='railway_search_stations':
        # The two-station intake is a step, not an answer: the picker (or the
        # automatic continuation) already shows these candidates, so repeating
        # a raw "车站查询" block per city is duplicated text in the transcript.
        if len([r for r in _railway_rows(session) if r.get('tool')=='railway_search_stations'])>1:return
        st.markdown('### 车站查询')
        candidates=[x for x in (result.get('data') or []) if isinstance(x,dict)]
        if not candidates:
            st.info('没有找到匹配车站，请调整名称。');return
        listed,total=station_shortlist(candidates,_city_hint(row))
        st.write('、'.join(str(x.get('stop_name') or '') for x in listed))
        if total>len(listed):st.caption('共 '+str(total)+' 个同名车站，这里只列主要客运站。')


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


def _live_board(rows):
    return next((r.get('id') for r in reversed(rows) if r.get('ok') and r.get('tool')=='railway_query_trips'),None)


def history(session,turn=None,orphans=False):
    """Boards of one turn (turn=N), or the unattached ones (orphans=True).

    A board is part of the exchange that produced it: painting them all at the
    foot of the transcript put an old train list below the newest answer.  A
    board whose turn is at or past the settled count came from a page button
    (翻页 / 返回车次列表) rather than a message, so it keeps the foot of the
    page.  The newest board stays live so its「选择此车次」still works.
    """
    rows=list(getattr(session,'railway_queries',[]) or [])
    live=_live_board(rows)
    settled=len(getattr(session,'history',[]) or [])
    def owned(row):
        value=row.get('turn') if isinstance(row,dict) else None
        return isinstance(value,int) and value<settled
    if orphans:rows=[r for r in rows if not owned(r)]
    else:rows=[r for r in rows if owned(r) and r['turn']==turn]
    for row in visible_rows(rows):
        with st.chat_message('assistant'):
            result_card(row,session,latest=bool(live) and row.get('id')==live)


def page_args(row):
    args={k:v for k,v in (row.get('args') or row['result'].get('query_parameters') or {}).items() if v is not None}
    args.setdefault('limit',row['result'].get('limit',PAGE_LIMIT))
    return args


def pagination(session,row):
    args=page_args(row)
    limit=row['result'].get('limit',PAGE_LIMIT);offset=int(args.get('cursor') or 0)
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


def board_for_leg(session, order):
    """True when this order's own leg already has a train board on screen.

    Returning to the list must not paint a second copy of it at the foot of the
    page: the board the customer came from is still there, so the page scrolls
    back to it instead.
    """
    if session is None or not isinstance(order,dict):return False
    wanted=[str(order.get(k) or '') for k in ('service_date','origin_stop_id','destination_stop_id')]
    if not all(wanted):return False
    for raw in iter_rows([getattr(session,'railway_queries',[]),getattr(session,'results',[])]):
        if not isinstance(raw,dict) or raw.get('tool')!='railway_query_trips' or not raw.get('ok'):continue
        result=raw.get('result') if isinstance(raw.get('result'),dict) else {}
        args=result.get('query_parameters') if isinstance(result.get('query_parameters'),dict) else (raw.get('args') or {})
        if [str(args.get(k) or '') for k in ('service_date','origin_stop_id','destination_stop_id')]==wanted:
            return True
    return False


def board_anchor(session):
    """Scroll anchor for the board last rendered on this session."""
    identity=st.session_state.get('board_last_'+str(getattr(session,'sid','')))
    return 'board_'+str(identity) if identity else ''


def back_to_trips(session, order):
    """Re-run this order's own leg when no board for it is on screen.

    The button used to route through the agent queue, which refuses every new
    message while a confirmation card is pending ("请先完成待确认的操作"), so it
    looked dead.  This is the same read-only page query the pager uses, and it
    only runs when the conversation has no board for this leg yet.
    """
    if session is None or getattr(session,'read_only',False):return False
    order=order if isinstance(order,dict) else {}
    args=dict(service_date=order.get('service_date'),
              origin_stop_id=order.get('origin_stop_id'),
              destination_stop_id=order.get('destination_stop_id'),limit=PAGE_LIMIT)
    if not all(args.get(k) for k in ('service_date','origin_stop_id','destination_stop_id')):
        return False
    from web.railway_defaults import prepare
    try:
        service,ctx,effective=prepare(session)
        row=query(session,service,ctx,effective,'railway_query_trips',args)
    except Exception:
        return False
    if not row.get('ok'):return False
    record(session,row)
    return True


def panel(session,service,ctx,effective):
    with st.expander('铁路查询',expanded=False):
        st.caption('通过当前Agent查询本地真实静态数据；在线模式会产生当前模型费用，结果进入聊天与运行记录。')
        key='rq_'+session.sid
        kind=st.radio('查询类型',['查车次','查车站','查经停站'],horizontal=True,key=key+'_kind')
        day=st.date_input('出行日期',value=default_service_date(),key=key+'_date')
        if kind=='查车站':
            name=st.text_input('站名关键词',key=key+'_station')
            if st.button('查询车站',key=key+'_station_go',disabled=session.read_only or not name.strip()):
                submit(session,'railway_search_stations',dict(name=name.strip(),limit=PAGE_LIMIT));st.rerun()
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
                        submit(session,'railway_query_trips',dict(service_date=day.isoformat(),origin_stop_id=x['stop_id'],destination_stop_id=y['stop_id'],limit=PAGE_LIMIT));st.rerun()
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