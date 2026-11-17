"""Pure, conservative policy UI projections and offline follow-up suggestions.

No file access, model invocation or business calls. A hit is not proof that a
reply is faithful. Missing metadata and delivery evidence stay unknown.
"""
import re


STATUS_LABELS = {
    'not_searched': '尚未检索',
    'searching': '正在检索知识库',
    'retrieved': '已返回文档，支持性尚未验证',
    'insufficient_evidence': '检索完成，但没有足够证据',
    'failed': '知识库检索失败',
}


def _audit_bound(audit, session_id, run_id):
    if not isinstance(audit, dict) or audit.get('trace_id') != run_id:
        return False
    return (audit.get('public_trace') or {}).get('session_id') == session_id


def _bound(row, session_id, run_id, trusted_audit=False):
    if not isinstance(row, dict) or not run_id or not session_id:
        return False
    row_run = row.get('run_id') or row.get('trace_id')
    if row_run != run_id:
        return False
    sid = row.get('session_id')
    return sid == session_id or sid is None and trusted_audit


def _hit_identity(hit):
    # Similar titles or a shared ID alone cannot prove the same policy content.
    return tuple(hit.get(k) for k in ('doc_id', 'title', 'version', 'source', 'content'))


def _same_hit(left, right):
    return (isinstance(left, dict) and isinstance(right, dict) and
            bool(left.get('doc_id')) and bool(left.get('content')) and
            _hit_identity(left) == _hit_identity(right))


def _execution_hits(audit, trusted):
    if not trusted:
        return {}
    rows = list(audit.get('framework_events') or [])
    rows += list((audit.get('fault_report') or {}).get('executions') or [])
    by_call = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('tool') != 'search_policy' or row.get('ok') is not True:
            continue
        if row.get('executed') is not True or not row.get('call_id'):
            continue
        result = row.get('result')
        if isinstance(result, dict) and isinstance(result.get('hits'), list):
            by_call[row['call_id']] = result['hits']
    return by_call


def policy_view(session_id, run_id, events=(), rag_records=(), audit=None):
    """Project one run only; old unbound rows never borrow a current session.

    Event order is the producer's saved order. It is not a fabricated clock or
    a reconstructed real-time timeline. RAG sidecars enrich event evidence; they
    are a fallback for status only when no retrieval event was recorded.
    """
    trusted = _audit_bound(audit, session_id, run_id)
    selected = [e for e in events if _bound(e, session_id, run_id, trusted)]
    records = [r for r in rag_records if _bound(r, session_id, run_id, trusted) and
               r.get('schema') != 'ticket-rag-answer/1']
    state, reason, evidence, event_ids = 'not_searched', None, [], []
    has_rag_event = False

    def add_documents(hits, *, retrieval_id=None, mode=None, event_id=None,
                      call_id=None, location=None):
        if not isinstance(hits, list):
            return
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            identical = [r for r in evidence if _hit_identity(r) == _hit_identity(hit) and
                         r.get('score') == hit.get('score') and r.get('rank') == hit.get('rank') and
                         (mode is None or r.get('mode') is None or r.get('mode') == mode) and
                         (retrieval_id is None or r.get('retrieval_id') is None or r.get('retrieval_id') == retrieval_id)]
            if identical:
                row = identical[-1]
                if mode is not None:
                    row['mode'] = mode
                if retrieval_id is not None:
                    row['retrieval_id'] = retrieval_id
                if call_id is not None:
                    row['call_id'] = call_id
            else:
                row = {k: hit.get(k) for k in ('doc_id', 'title', 'version', 'score', 'rank', 'content', 'source')}
                row.update(mode=mode, retrieval_id=retrieval_id, call_id=call_id,
                           run_id=run_id, trace_id=run_id, event_ids=[], evidence_locations=[],
                           entered_context=None, support_status='尚未验证')
                evidence.append(row)
            if event_id and event_id not in row['event_ids']:
                row['event_ids'].append(event_id)
            if location and location not in row['evidence_locations']:
                row['evidence_locations'].append(location)

    for i, event in enumerate(selected):
        kind, status = event.get('event_type'), event.get('status')
        if kind in ('rag_start', 'rag_result', 'rag_error') or event.get('tool') == 'search_policy':
            if event.get('event_id'):
                event_ids.append(event['event_id'])
        if kind == 'rag_start' or kind == 'tool_start' and event.get('tool') == 'search_policy':
            state, has_rag_event = 'searching', True
        elif kind == 'rag_error':
            state, has_rag_event = 'failed', True
            reason = event.get('error_category') or event.get('error')
        elif kind == 'rag_result' and status not in ('failed', 'blocked'):
            has_rag_event = True
            hits = event.get('documents') if isinstance(event.get('documents'), list) else event.get('hits')
            state = 'retrieved' if hits else 'insufficient_evidence'
            add_documents(hits, retrieval_id=event.get('retrieval_id'), mode=event.get('mode'),
                          event_id=event.get('event_id'), call_id=event.get('call_id'),
                          location=f'run_events[{i}]')
        elif kind == 'tool_result' and event.get('tool') == 'search_policy':
            has_rag_event = True
            if status in ('failed', 'blocked'):
                output = event.get('output')
                state, reason = 'failed', output.get('error') if isinstance(output, dict) else None
            elif status == 'succeeded' and event.get('executed') is True:
                result = event.get('output')
                if isinstance(result, dict) and isinstance(result.get('hits'), list):
                    state = 'retrieved' if result['hits'] else 'insufficient_evidence'
                    add_documents(result['hits'], event_id=event.get('event_id'), call_id=event.get('call_id'),
                                  location=f'run_events[{i}].output')

    for i, record in enumerate(records):
        if record.get('status') == 'retrieved':
            add_documents(record.get('hits'), retrieval_id=record.get('retrieval_id'), mode=record.get('mode'),
                          call_id=record.get('call_id'), location=f'rag_records[{i}]')
        if not has_rag_event:
            if record.get('status') == 'failed':
                state, reason = 'failed', record.get('error_category')
            elif record.get('status') == 'retrieved':
                state = 'retrieved' if record.get('hits') else 'insufficient_evidence'

    executed = _execution_hits(audit or {}, trusted)
    requests = [e for e in selected if e.get('event_type') == 'tool_result_in_model_request' and
                isinstance(e.get('documents'), list) and e.get('call_id') in executed]
    for row in evidence:
        for request in requests:
            if row['call_id'] is not None and row['call_id'] != request['call_id']:
                continue
            if (any(_same_hit(row, h) for h in request['documents']) and
                    any(_same_hit(row, h) for h in executed[request['call_id']])):
                row['entered_context'] = True
                if request.get('event_id') and request['event_id'] not in row['event_ids']:
                    row['event_ids'].append(request['event_id'])
                break
    return {'status': state, 'status_label': STATUS_LABELS[state], 'count': len(evidence),
            'evidence': evidence, 'reason': reason, 'run_id': run_id, 'session_id': session_id,
            'event_ids': list(dict.fromkeys(event_ids)),
            'support_status': '尚未验证', 'has_recorded_retrieval': state != 'not_searched'}


def _normal(text):
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', str(text).lower())


# Each recommendation is enabled only by explicit facts in a returned document.
# The topic key also suppresses a semantically equivalent question already asked.
FOLLOW_UPS = (
    ('refund_tiers', ('退票', '手续费'), '退票手续费怎样随退票时间变化？', r'退票.*(?:手续费|费率)'),
    ('changed_refund', ('改签', '不退'), '已经改签的车票还能退票吗？', r'改签.*(?:退|退款)|退.*改签'),
    ('voucher_refund', ('报销凭证', '退票'), '已领取报销凭证的车票退票有什么限制？', r'(?:凭证|报销).*(?:退|退款)|退.*(?:凭证|报销)'),
    ('lock_duration', ('锁座', '有效期'), '锁座的有效期有多长？', r'锁座.*(?:多久|多长|有效期|时限|支付)'),
    ('lock_expiry', ('过期', '释放库存'), '锁座到期仍未支付，库存如何处理？', r'(?:到期|过期|超时).*(?:库存|释放)|库存.*(?:到期|过期|超时)'),
    ('passenger_list', ('锁座', '乘客列表'), '下单乘客名单需要与锁座名单一致吗？', r'(?:名单|列表|乘客).*(?:一致|相同|顺序)'),
    ('duplicate_pay', ('重复支付', '不重复', '库存'), '重复支付会重复扣减库存吗？', r'重复.*(?:支付|付款|库存|扣款)'),
    ('change_count', ('改签', '一次'), '每张车票允许改签几次？', r'改签.*(?:几次|次数|多少次|一回)'),
    ('change_advance', ('48', '预售期'), '提前较久改签，可以选择哪些车次？', r'改签.*(?:预售期|提前较久|提前两天|48|四十八)'),
    ('change_today', ('改签', '24:00'), '临近发车改签，目标车次的时间范围是什么？', r'(?:改签|换票).*(?:时间范围|当天|当日|临近|以内)'),
    ('baggage_weight', ('成人', '儿童', '千克'), '成人和儿童的免费行李重量分别是多少？', r'(?:成人|儿童).*(?:行李|重量|千克|公斤)|行李.*(?:免费|额度|重量)'),
    ('baggage_size', ('长宽高', '厘米'), '单件行李的尺寸上限是什么？', r'(?:行李|箱子|单件).*(?:尺寸|长宽高)|尺寸.*(?:行李|箱子)'),
    ('baggage_fee', ('超重', '每千克'), '行李超重部分如何计费？', r'(?:行李|超重).*(?:费|钱|元|计费)'),
    ('voucher_window', ('乘车之日起', '180'), '报销凭证的打印期限从何时开始计算？', r'(?:凭证|报销).*(?:期限|多久|何时|时间|天|日)'),
    ('voucher_once', ('报销凭证', '一次'), '报销凭证可以重复打印吗？', r'(?:凭证|报销).*(?:重复|几次|一次|补打)'),
    ('voucher_place', ('报销凭证', '窗口', '自助机'), '可以在哪些地方打印报销凭证？', r'(?:凭证|报销).*(?:哪里|地点|地方|窗口|自助机)'),
    ('cancel_unpaid', ('未支付订单', '不收取手续费'), '未支付订单取消是否收取手续费？', r'(?:未付|没付|待付).*取消|取消.*(?:未付|没付|待付)'),
    ('cancel_pay', ('取消', '不可支付'), '已经取消的订单还能支付吗？', r'取消.*(?:支付|付款)'),
    ('cancel_inventory', ('库存', '不得再次释放'), '已取消订单能再次释放库存吗？', r'(?:取消|退款).*(?:库存|释放)'),
    ('student_seat', ('学生', '二等座'), '学生票优惠适用于哪些席别？', r'学生.*(?:席别|座|舱)'),
    ('student_route', ('学生', '家庭居住地', '学校所在地'), '学生票优惠对出行线路有什么要求？', r'学生.*(?:路线|线路|学校|居住地)'),
    ('student_count', ('学生', '每年', '4'), '学生票每年可使用几次优惠？', r'学生.*(?:次数|几次|多少次|几回)'),
    ('child_free', ('1.2', '6', '免票'), '儿童免票需要同时满足哪些条件？', r'(?:儿童|孩子|小孩).*(?:免票|免费|不买票)'),
    ('child_seat', ('儿童票', '一等座', '商务座'), '一等座和商务座支持儿童票优惠吗？', r'(?:儿童|孩子).*(?:一等|商务)|(?:一等|商务).*儿童'),
    ('child_price', ('儿童票', '二等座', '50%'), '儿童二等座优惠按什么票价比例计算？', r'(?:儿童|孩子).*(?:价格|票价|比例|折|半价)'),
)


def followup_questions(question, reply, hits, asked=(), limit=3):
    """Deterministic, evidence-bound suggestions; never an extra model request.

    Suggestions are recommendations, not tool calls or proof that the answer is
    supported. Unsupported topics, empty evidence and already-discussed facets
    are omitted rather than padded with an ungrounded question.
    """
    if not isinstance(reply, str) or not reply.strip() or not isinstance(hits, (list, tuple)):
        return []
    if limit not in (2, 3) or re.match(r'\s*(?:请求未完成|工具执行失败|模型调用未完成|达到最大执行步数)', reply):
        return []
    prior = [str(question), *(str(s) for s in asked)]
    normalized = {_normal(s) for s in prior}
    families = {
        'refund': r'退票|退款|退费|手续费', 'lock': r'锁座|占座|支付|付款|下单|名单',
        'change': r'改签|改票|换票|误车', 'baggage': r'行李|箱子|携带|超重',
        'voucher': r'报销|凭证|打印', 'cancel': r'取消|撤销|订单',
        'student': r'学生', 'child': r'儿童|孩子|小孩|周岁',
    }
    topics = {key for key, pattern in families.items() if re.search(pattern, str(question))}
    if not topics:
        topics = {key for key, pattern in families.items() if re.search(pattern, reply)}
    output = []
    for key, anchors, recommendation, same_topic in FOLLOW_UPS:
        family = ('refund' if key in ('refund_tiers', 'changed_refund', 'voucher_refund') else
                  'lock' if key in ('lock_duration', 'lock_expiry', 'passenger_list', 'duplicate_pay') else
                  key.split('_', 1)[0])
        if key == 'changed_refund' and 'change' in topics:
            family = 'change'
        if family not in topics:
            continue
        if _normal(recommendation) in normalized or any(re.search(same_topic, s) for s in prior):
            continue
        supported = any(isinstance(hit, dict) and hit.get('doc_id') and hit.get('content') and
                        all(anchor in hit['content'] for anchor in anchors) for hit in hits)
        if supported and recommendation not in output:
            output.append(recommendation)
        if len(output) >= limit:
            break
    return output if len(output) >= 2 else []
