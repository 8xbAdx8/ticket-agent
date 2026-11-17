"""Turn a real policy retrieval into the answer a customer can actually read.

Why this module exists
----------------------
A plain question such as「退票手续费怎么算」is routed to ``search_policy`` and the
retrieval really runs.  The backend then writes its own summary of the hits, but
that summary quotes the clauses — and a clause often contains wording like
「退票成功后…」.  The V3.9 claim guard (``target/v39/business_claim_guard.py``)
reads that as the assistant *claiming it had executed* a refund, finds no
evidence, and replaces the **entire** answer with its audit projection:

    模型的业务成功声明未获匹配凭据支持，已改为以下核验状态：
    锁座：尚无成功证据，不能视为已完成。 …

That text is written for a developer, not a customer, and it drops the answer
the customer asked for.  ``target/`` is frozen, so the A-side does what it
already does elsewhere: project the run into customer language, using the very
clauses this turn retrieved (never a made-up rule) plus the fee schedule the
approved policy actually computes.

Nothing here invents data.  When the fee schedule cannot be computed, the
clauses are shown as-is and no rate is stated.
"""
from datetime import timedelta

# Only these words mean "the customer is asking about the money side of a
# refund".  Anything else is answered with the retrieved clauses verbatim.
FEE_WORDS = ('退票', '退款', '手续费', '改签费', '扣多少', '扣钱', '费用')

GUARD_MARKERS = ('未获匹配凭据支持', '已改为以下核验状态')


def is_guard_rewrite(text):
    """True when the backend answer was replaced by the claim-guard projection."""
    if not isinstance(text, str):
        return False
    return any(marker in text for marker in GUARD_MARKERS)


def asks_about_fee(question):
    return any(word in str(question or '') for word in FEE_WORDS)


def clauses(view):
    """The clauses this turn really retrieved, in retrieval order."""
    out = []
    for hit in (view or {}).get('evidence') or []:
        content = str(hit.get('content') or '').strip()
        if not content:
            continue
        out.append(dict(doc_id=str(hit.get('doc_id') or ''),
                        title=str(hit.get('title') or ''),
                        content=content))
    return out


def fee_schedule(session, sample_fen=10000):
    """The approved refund schedule, computed by the real policy object.

    Returns ``[(when, rate_text, fee_fen)]`` for a ¥100 ticket.  Empty list when
    the policy object is unavailable — the caller then states no number at all.
    """
    service = getattr(session, '_v39_service', None)
    policy = getattr(service, 'policy', None)
    if policy is None or not hasattr(policy, 'refund'):
        return []
    try:
        now = service.now()
    except Exception:
        return []
    points = (('开车前 48 小时以上', timedelta(days=3)),
              ('开车前 24–48 小时', timedelta(hours=30)),
              ('开车前不足 24 小时', timedelta(hours=2)))
    rows = []
    for label, delta in points:
        try:
            fare = policy.refund([sample_fen], (now + delta).isoformat(), now.isoformat())[0]
        except Exception:
            return []
        fee = fare.get('fee_fen')
        if type(fee) is not int:
            return []
        rate = fee * 100 // sample_fen if sample_fen else 0
        rows.append((label, str(rate) + '%', fee))
    return rows


def _relevance(clause, question):
    """Cheap overlap between the question and one clause; title counts triple.

    Retrieval returns what it returns — a train-fee question can also hit the
    flight-change clause.  This only orders the real hits so the clause that
    actually answers the question is the one shown first; nothing is rewritten.
    """
    body = str(clause.get('content') or '')
    title = str(clause.get('title') or '')
    text = str(question or '')
    pairs = [text[i:i + 2] for i in range(len(text) - 1)]
    tokens = {p for p in pairs if all('\u4e00' <= c <= '\u9fa5' for c in p)}
    return (sum(1 for t in tokens if t in title) * 3
            + sum(1 for t in tokens if t in body))


def answer(view, session, question):
    """Customer-facing answer built only from this turn's retrieval.

    ``kind`` is ``'fee'`` when a real schedule was available, ``'clauses'`` when
    only the retrieved text can be shown, ``'empty'`` when nothing was found.
    A fee question keeps its schedule even when retrieval returned no clause:
    the rates come from the approved policy object, which is the rule itself.
    """
    found = clauses(view)
    found.sort(key=lambda c: -_relevance(c, question))
    found = found[:2]
    fee = fee_schedule(session) if asks_about_fee(question) else []
    if fee:
        return dict(kind='fee', clauses=found, fee=fee)
    if found:
        return dict(kind='clauses', clauses=found, fee=[])
    return dict(kind='empty', clauses=[], fee=[])
