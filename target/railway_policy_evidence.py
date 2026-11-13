"""Evidence selection for the current railway simulation policy."""
import os
import re

from target.rag_relevance import scope_requirements


_POLICY_IDS = re.compile(r'(?<![A-Za-z0-9])P\d{2}(?![A-Za-z0-9])', re.I)
_AFTER_DEPARTURE = re.compile(r'(?:发车|开车)后|错过.{0,5}(?:发车|开车)')
_REFUND_FEE = re.compile(r'退票手续费|退票.{0,10}(?:费率|扣多少)|(?:发车|开车)前.{0,18}退票')
_UNSUPPORTED_TIME_TRAVEL = re.compile(r'时光机|穿越时空|时间倒流')


def active():
    from target.v39.context import CURRENT
    from target.v39.policy import Policy

    context = CURRENT.get()
    if (not context or not context.enabled or context.execution_mode == 'baseline'
            or os.getenv('TICKET_FROZEN_RAG_EVIDENCE')):
        return False
    policy = Policy()
    return policy.approved and policy.profile == 'CHANGED_REFUND_P01'


def requirements(question):
    explicit = list(dict.fromkeys(value.upper() for value in _POLICY_IDS.findall(question)))
    required = list(explicit)
    if _AFTER_DEPARTURE.search(question):
        if _REFUND_FEE.search(question):
            required.extend(('P01', 'P03'))
        elif re.search(r'改签|退票|退款|改票', question):
            required.append('P03')
    unsupported = scope_requirements(question)['unsupported_attributes']
    if _UNSUPPORTED_TIME_TRAVEL.search(question):
        unsupported = [*unsupported, 'time_travel']
    return list(dict.fromkeys(required)), unsupported


def select(question, evidence, *, documents=(), k):
    """Retain raw candidates and prioritize requested, authoritative evidence."""
    required, unsupported = requirements(question)
    original_hits = evidence['hits']
    candidates = evidence.get('candidate_hits', original_hits)
    available = {row['doc_id']: row for row in candidates} if evidence['mode'] == 'keyword' else {}
    available.update({row['doc_id']: row for row in original_hits})
    if evidence['mode'] == 'keyword':
        # An explicit source lookup is grounded by corpus identity. Its score is
        # unknown unless the retrieval stage actually scored the same chunk.
        for row in documents:
            if row['doc_id'] in required:
                available.setdefault(row['doc_id'], {**row, 'score': None, 'match_basis': 'policy_id_lookup'})
    missing = [doc_id for doc_id in required if doc_id not in available]
    if len(required) > k:
        missing.extend(doc_id for doc_id in required[k:] if doc_id not in missing)
    if unsupported or missing:
        hits = []
    elif required:
        # A multi-policy answer must be built from all required evidence before
        # optional matches. This avoids unrelated general rules taking its slots.
        hits = [{**available[doc_id], 'rank': rank} for rank, doc_id in enumerate(required, 1)]
    else:
        hits = original_hits
    reason = ('unsupported_request' if unsupported else 'missing_required_evidence' if missing
              else 'sufficient_for_requested_scope' if hits else 'empty_retrieval')
    return {**evidence, 'hits': hits, 'candidate_hits': candidates,
            'answerability': dict(reason=reason, required_policy_ids=required, missing_policy_ids=missing,
                                  unsupported_attributes=unsupported, abstain=not hits)}


def public_answer(question, events):
    """Return a bounded fallback using only current-turn, executed policy receipts."""
    if not active():
        return None
    receipts = [row for row in events if row.get('tool') == 'search_policy'
                and row.get('ok') is True and row.get('executed') is True]
    if not receipts:
        return None
    # Mixed business turns retain the existing transaction reply and guards.
    if any(row.get('tool') != 'search_policy' and row.get('executed') is True
           for row in events if row.get('event') == 'tool_end' or 'result' in row):
        return None
    required, unsupported = requirements(question)
    matching = [row['result'] for row in receipts if row.get('args', {}).get('question') == question
                and isinstance(row.get('result'), dict)]
    hits = {hit['doc_id']: hit for result in matching for hit in result.get('hits', [])
            if hit.get('doc_id') and hit.get('content')}
    if unsupported or (matching and not hits) or (required and not set(required) <= hits.keys()):
        return '当前政策证据不足，无法确认这个问题。请补充具体的铁路场景或可核对的政策来源。'
    if len(required) < 2:
        return None
    sections = []
    for doc_id in required:
        hit = hits[doc_id]
        section = f"{hit['title']}（{doc_id}）\n{hit['content']}"
        if hit.get('policy_scope') == 'railway_simulation' and hit.get('original_policy_content'):
            section += f"\n示例政策原文：{hit['original_policy_content']}"
        sections.append(section)
    return '以下依据当前铁路模拟政策。\n\n' + '\n\n'.join(sections)
