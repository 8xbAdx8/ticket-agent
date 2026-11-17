"""Versioned, offline-only RAG benchmark; never calls a model or an HTTP client.

Retrieval, answer evidence and annotation quality are three different outcomes.
Cached real embeddings are accepted only with a compatible immutable index.
"""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import csv
import difflib
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data/rag1000/v1.1.1'
STORE = ROOT / 'artifacts/runtime/rag-benchmark'
QUOTAS = dict(normal_qa=250, paraphrase=180, multi_policy=120, no_answer=150,
              missing_conditions=80, conflict_version=80, prompt_injection=60,
              false_premise=50, numeric_boundary=30)
BEHAVIORS = ('answer', 'clarify', 'refuse', 'insufficient_evidence', 'explain_conflict', 'correct_premise')
LABELS = ('supported', 'contradicted', 'unsupported', 'indeterminate', 'not_applicable')
SEED = 20261029


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows briefly forbids rename while a reader has the old report open.
    # Retry ONLY this local atomic replacement, never a model/embedding call.
    for attempt in range(7):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 6:
                raise
            time.sleep(0.02 * 2**attempt)


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(question):
    text = re.sub(r'\s|[，。！？、,.!?；;：:"“”‘’（）()\[\]`]', '', question).lower()
    return re.sub(r'^(?:您好|你好|麻烦|请问|请|帮我|能不能|可以帮我)', '', text)


def load(data=DATA):
    data = Path(data)
    return ([json.loads(line) for line in (data / 'cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()],
            read(data / 'corpus.json'), read(data / 'manifest.json'))


def near_duplicates(cases, threshold=0.84):
    """Local character bigrams shortlist, then edit similarity; no embeddings."""
    normalized = [normalize(c['question']) for c in cases]
    grams = [{s[i:i+2] for i in range(len(s)-1)} for s in normalized]
    inverted = defaultdict(list)
    result = []
    for i, words in enumerate(grams):
        candidates = Counter(j for word in words for j in inverted[word])
        for j, common in candidates.items():
            if common / max(1, len(words | grams[j])) < 0.45:
                continue
            ratio = difflib.SequenceMatcher(None, normalized[i], normalized[j], autojunk=False).ratio()
            if ratio >= threshold:
                result.append({'left': cases[j]['case_id'], 'right': cases[i]['case_id'],
                               'similarity': round(ratio, 5), 'method': 'bigrams_then_edit_ratio',
                               'same_group': cases[j]['group_id'] == cases[i]['group_id'],
                               'same_split': cases[j].get('split') == cases[i].get('split')})
        for word in words:
            inverted[word].append(i)
    return result


def split_cases(cases, seed=SEED):
    """Keep intent and near-duplicate connected components intact; stratified greedy.

    Exact 700/150/150 is a target, not a reason to split a semantic family.
    """
    parent = {c['group_id']: c['group_id'] for c in cases}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    by_id = {c['case_id']: c for c in cases}
    for pair in near_duplicates(cases):
        a, b = find(by_id[pair['left']]['group_id']), find(by_id[pair['right']]['group_id'])
        parent[b] = a
    groups = defaultdict(list)
    for c in cases:
        c['group_id'] = find(c['group_id'])
        groups[c['group_id']].append(c)
    weights = {'development': 0.7, 'validation': 0.15, 'holdout': 0.15}
    totals = Counter((c['category'], c['difficulty']) for c in cases)
    counts, sizes = {s: Counter() for s in weights}, Counter()
    order = list(groups.values())
    random.Random(seed).shuffle(order)
    order.sort(key=len, reverse=True)
    for group in order:
        contribution = Counter((c['category'], c['difficulty']) for c in group)
        def cost(s):
            return sum(((counts[s][key] + n) ** 2 - counts[s][key] ** 2) /
                       max(1, totals[key] * weights[s]) for key, n in contribution.items()) + (
                           (sizes[s] + len(group)) ** 2 - sizes[s] ** 2) / max(1, len(cases) * weights[s])
        selected = min(weights, key=cost)
        for c in group:
            c['split'] = selected
        counts[selected].update(contribution)
        sizes[selected] += len(group)
    return dict(sizes)


def validate(cases, corpus, manifest=None, data=DATA):
    """Schema + exact evidence checks. Semantic authoring review stays explicit."""
    import jsonschema
    schema = read(Path(data) / 'schema.json')
    validator = jsonschema.Draft202012Validator(schema)
    docs = {d['doc_id']: d for d in corpus}
    errors, reviews, seen_ids, seen_questions, usable = [], [], set(), {}, []
    for index, c in enumerate(cases):
        cid = c.get('case_id', 'invalid-row-' + str(index)) if isinstance(c, dict) else 'invalid-row-' + str(index)
        problems = [e.json_path + ': ' + e.message for e in validator.iter_errors(c)]
        if problems:
            errors.append({'case_id': cid, 'errors': problems})
            continue
        usable.append(c)
        if c['provenance']['policy_version'] != sha(corpus):
            problems.append('provenance_corpus_hash_mismatch')
        if manifest and c['dataset_version'] != manifest.get('dataset_version'):
            problems.append('case_dataset_version_mismatch')
        if cid in seen_ids:
            problems.append('duplicate_case_id')
        seen_ids.add(cid)
        norm = normalize(c.get('question', ''))
        if not norm:
            problems.append('blank_normalized_question')
        if norm in seen_questions:
            problems.append('normalized_duplicate:' + seen_questions[norm])
        seen_questions[norm] = cid
        if re.search(r'TODO|占位|问题\d+$|待填写', c.get('question', ''), re.I):
            problems.append('placeholder_question')
        ids = c.get('expected_doc_ids', [])
        if (not isinstance(c.get('alternative_doc_ids', []), list) or
            any(not isinstance(d, str) for d in c.get('alternative_doc_ids', [])) or
            not isinstance(c.get('alternative_evidence', []), list) or
            any(not isinstance(e, dict) for e in c.get('alternative_evidence', []))):
            errors.append({'case_id': cid, 'errors': problems + ['invalid_alternative_evidence_schema']})
            continue
        referenced = ids + c.get('source_policy_ids', []) + c.get('expected_citations', []) + c.get('alternative_doc_ids', [])
        for doc_id in referenced:
            if doc_id not in docs:
                problems.append('unknown_document:' + doc_id)
        if c.get('answerable') and not ids:
            problems.append('answerable_without_support')
        if c.get('answerable') and not c.get('expected_answer_points'):
            problems.append('answerable_without_expected_facts')
        if not c.get('answerable') and c.get('expected_behavior') == 'answer':
            problems.append('unanswerable_but_answer_expected')
        if c.get('category') == 'no_answer' and (ids or not c.get('absence_reason')):
            problems.append('invalid_no_answer_annotation')
        if c.get('expected_behavior') == 'clarify' and not c.get('clarification_fields'):
            problems.append('clarification_without_missing_fields')
        evidence_ids = set()
        for e in c.get('required_evidence', []):
            doc = docs.get(e.get('doc_id'))
            if not doc or not e.get('quote') or e['quote'] not in doc['content'] or e.get('version') != doc['version']:
                problems.append('ungrounded_or_stale_evidence')
            else:
                evidence_ids.add(e['doc_id'])
        for point in c.get('expected_answer_points', []):
            if not any(point == e.get('quote') for e in c.get('required_evidence', [])):
                problems.append('answer_point_not_exactly_evidence_bound')
        if not set(ids) <= evidence_ids:
            problems.append('missing_required_document_evidence')
        for alternative in c.get('alternative_evidence', []):
            doc = docs.get(alternative.get('doc_id'))
            if not doc or not isinstance(alternative.get('quote'), str) or not alternative['quote'].strip() or alternative.get('quote') not in doc['content'] or alternative.get('version') != doc['version']:
                problems.append('ungrounded_alternative_evidence')
        if set(c.get('alternative_doc_ids', [])) != {e['doc_id'] for e in c.get('alternative_evidence', [])}:
            problems.append('alternative_source_without_evidence')
        if c.get('alternative_doc_ids') and len(ids) != 1:
            problems.append('alternatives_require_single_canonical_evidence_unit')
        if c.get('category') == 'multi_policy' and len(set(ids)) < 2:
            problems.append('multi_policy_requires_two_documents')
        if c.get('category') == 'prompt_injection' and (not c.get('attack') or not c.get('safety_assertions')):
            problems.append('attack_without_payload_or_safety_assertion')
        if not any(c.get(k) for k in ('retrieval_assertions', 'answer_assertions', 'safety_assertions')):
            problems.append('no_decision_rule')
        if problems:
            errors.append({'case_id': cid, 'errors': problems})
        elif c.get('provenance', {}).get('review_status') != 'verified':
            reviews.append({'case_id': cid, 'reason': c.get('review_reason', 'semantic_annotation_review_pending')})
    pairs = near_duplicates(usable)
    leaked = [p for p in pairs if not p['same_split']]
    grouped = defaultdict(set)
    for c in usable:
        grouped[c.get('group_id')].add(c.get('split'))
    leakage = [g for g, splits in grouped.items() if len(splits) > 1]
    invalid_ids = {e['case_id'] for e in errors}
    review_ids = {r['case_id'] for r in reviews}
    verified = [c for c in usable if c['case_id'] not in invalid_ids | review_ids]
    if manifest:
        for name, digest in manifest.get('files', {}).items():
            p = Path(data) / name
            if not p.is_file() or sha(p.read_bytes()) != digest:
                errors.append({'case_id': '__manifest__', 'errors': ['frozen_file_hash_mismatch:' + name]})
        for split in ('development', 'validation', 'holdout'):
            path = Path(data)/(split + '.json')
            if path.is_file() and set(read(path)['case_ids']) != {c['case_id'] for c in usable if c['split'] == split}:
                errors.append({'case_id': '__split__', 'errors': ['split_manifest_does_not_match_cases:' + split]})
    group_counts = Counter(c['group_id'] for c in usable)
    answer_reuse = defaultdict(list)
    for c in usable:
        if c['expected_answer_points']:
            answer_reuse[sha(c['expected_answer_points'])].append(c)
    return {'schema': 'ticket-rag-dataset-validation/1', 'candidate_count': len(cases),
            'verified_count': len(verified), 'needs_review_count': len(review_ids), 'invalid_count': len(invalid_ids),
            'categories': {cat: {'target': n, 'candidates': sum(c.get('category') == cat for c in usable),
                                'verified': sum(c['category'] == cat for c in verified),
                                'shortfall': max(0, n - sum(c['category'] == cat for c in verified))} for cat, n in QUOTAS.items()},
            'split_counts': dict(Counter(c.get('split') for c in usable)), 'intent_group_count': len(grouped),
            'near_duplicates': pairs, 'group_leakage': leakage, 'near_duplicate_leakage': leaked,
            'intent_overuse_candidates': [{'group_id': g, 'count': n} for g, n in group_counts.items() if n > 8],
            'reused_gold_candidates': [{'case_ids': [c['case_id'] for c in rows],
                'test_purposes': sorted({c['test_purpose'] for c in rows}),
                'same_intent_group': len({c['group_id'] for c in rows}) == 1}
                for rows in answer_reuse.values() if len(rows) > 1],
            'errors': errors, 'needs_review': reviews,
            'valid_structure': not errors and not leakage and not leaked,
            'complete_1000_verified': len(verified) == 1000 and not errors and not leakage and not leaked and
                all(sum(c['category'] == cat for c in verified) == n for cat, n in QUOTAS.items()),
            'review_limit': 'Exact quotations/schema validated locally; AI-authored semantics are not human B acceptance.'}


def retrieval_metrics(case, hits):
    """Macro document recall, not hit rate; MRR uses first relevant UNIQUE rank."""
    ids = list(dict.fromkeys(h['doc_id'] for h in hits))
    canonical = set(case['expected_doc_ids'])
    relevant = canonical | set(case.get('alternative_doc_ids', []))
    ranked = [i for i, d in enumerate(ids, 1) if d in relevant]
    positive = bool(relevant)
    return {'applicable': positive, 'relevant_count': len(relevant),
            **{f'recall_at_{k}': len(relevant.intersection(ids[:k])) / len(relevant) if positive else None for k in (1, 3, 5)},
            'mrr': (1 / ranked[0] if ranked else 0) if positive else None,
            'first_relevant_rank': ranked[0] if ranked else None,
            'evidence_complete_at_5': (bool(relevant.intersection(ids[:5])) if case.get('alternative_doc_ids') else
                                      canonical.issubset(ids[:5])) if positive else None,
            'multi_evidence_coverage_at_5': len(canonical.intersection(ids[:5])) / len(canonical) if len(canonical) > 1 else None,
            'no_answer_false_recall': bool(ids) if case['category'] == 'no_answer' else None,
            'retrieval_returned_documents': bool(ids), 'answer_correct': None}


def ratio(values):
    values = [v for v in values if v is not None]
    return {'value': sum(values) / len(values) if values else None, 'denominator': len(values)}


def summarize(rows):
    executed = [r for r in rows if r.get('execution_status') == 'completed']
    keys = ('recall_at_1', 'recall_at_3', 'recall_at_5', 'mrr', 'evidence_complete_at_5',
            'multi_evidence_coverage_at_5', 'no_answer_false_recall')
    def metrics(part):
        return {k: ratio(r['retrieval_metrics'][k] for r in part) for k in keys}
    assessments = [r['answer_assessment'] for r in rows if r.get('answer_assessment', {}).get('counts')]
    claim_counts = Counter({label: sum(a['counts'][label] for a in assessments) for label in LABELS})
    factual = sum(claim_counts[label] for label in LABELS if label != 'not_applicable')
    citation_n = sum(a['citation_id_precision_denominator'] for a in assessments)
    citation_correct = sum(a['citation_id_precision'] * a['citation_id_precision_denominator'] for a in assessments if a['citation_id_precision'] is not None)
    answer_metrics = {'claim_counts': dict(claim_counts), 'factual_denominator_including_unknown': factual,
        'supported_claim_ratio': claim_counts['supported']/factual if factual else None,
        'unsupported_claim_ratio': claim_counts['unsupported']/factual if factual else None,
        'contradiction_ratio': claim_counts['contradicted']/factual if factual else None,
        'citation_id_precision': citation_correct/citation_n if citation_n else None, 'citation_denominator': citation_n,
        'condition_literal_coverage': ratio(condition['status']=='supported' for a in assessments for condition in a['conditions']),
        'condition_semantic_completeness': None,
        'no_answer_refusal_correctness': ratio(r['answer_assessment'].get('refusal_correctness') for r in rows if r['category']=='no_answer'),
        'injection_resistance': ratio(r['answer_assessment'].get('injection_resistance') for r in rows if r['category']=='prompt_injection'),
        'origin_counts_claimed_not_authenticated': dict(Counter(a['origin'] for a in assessments))}
    return {'execution': dict(Counter(r['execution_status'] for r in rows)),
            'annotation_status': dict(Counter(r.get('annotation_status', 'unknown') for r in rows)),
            'metric_scope': 'exploratory_candidate_gold_not_B_acceptance',
            'verified_only_metrics': metrics([r for r in executed if r.get('annotation_status') == 'verified']),
            'retrieval_verdicts': dict(Counter(r.get('retrieval_verdict', 'not_evaluated') for r in rows)),
            'answer_verdicts': dict(Counter(r.get('answer_assessment', {}).get('verdict', 'not_evaluated') for r in rows)),
            'answer_metrics': answer_metrics,
            'metrics': metrics(executed),
            'by_category': {c: metrics([r for r in executed if r['category'] == c]) for c in sorted({r['category'] for r in rows})},
            'by_difficulty': {d: metrics([r for r in executed if r['difficulty'] == d]) for d in sorted({r['difficulty'] for r in rows})},
            'by_policy': {d: metrics([r for r in executed if d in r['source_policy_ids']]) for d in sorted({d for r in rows for d in r['source_policy_ids']})},
            'limits': ['Retrieval verdict is not answer faithfulness.', 'Unknown metrics are null, not zero.',
                       'Attack corpus overlays measure retrieval exposure only; resistance needs actual answers.']}


def assess_answer(case, hits, sample):
    """Import a saved response only if its question AND delivered context bind.

    Full semantics remain indeterminate unless exact/finite rules prove all atoms.
    Context SHA includes content, order, versions and scores as actually delivered.
    """
    reply = sample.get('raw_reply')
    context = sample.get('context')
    context_matches = (context == hits or sample.get('retrieval_sha256') == sha(hits) and
                       isinstance(context, list) and all(h in hits for h in context))
    if (sample.get('case_id') != case['case_id'] or sample.get('question') != case['question'] or
        not isinstance(reply, str) or not isinstance(context, list) or
        sample.get('context_sha256') != sha(context) or not context_matches or
        sample.get('origin') not in ('historical_real_api', 'offline_fixture', 'human_authored')):
        return {'verdict': 'INDETERMINATE', 'reason': 'answer_context_or_question_binding_failed'}
    from target.rag_faithfulness import check_answer
    check = check_answer(reply, context, question=case['question'], events=sample.get('tool_events', []))
    atomic = check['claim_audit']
    assertions = atomic['assertions']
    counts = Counter(a['verdict'] for a in assertions)
    citations = list(dict.fromkeys(re.findall(r'\bP\d+\b', reply)))
    allowed = {h['doc_id'] for h in context}
    condition_checks = [{'condition': s, 'status': 'supported' if s in reply else 'indeterminate',
                         'method': 'literal_presence_only_absence_is_not_semantic_failure'} for s in case['required_conditions']]
    forbidden = [s for s in case['forbidden_claims'] if s in reply]
    # A forbidden phrase inside a denial/quotation is not automatically an assertion.
    reviews = [{'phrase': s, 'reason': 'forbidden_phrase_requires_negation_and_attribution_review'} for s in forbidden]
    points = [{'point': p, 'status': 'supported' if p in reply else 'indeterminate',
               'method': 'literal_coverage_only'} for p in case['expected_answer_points']]
    failed = counts['contradicted'] + counts['unsupported'] > 0 or bool(check['findings'])
    citation_complete = (bool(set(citations).intersection(set(case['expected_citations']) | set(case.get('alternative_doc_ids', []))))
                         if case.get('alternative_doc_ids') else set(case['expected_citations']).issubset(citations))
    unknown = counts['indeterminate'] > 0 or bool(check['manual_review']) or bool(reviews) or any(
        r['status'] == 'indeterminate' for r in condition_checks + points) or not citation_complete or case['expected_behavior'] != 'answer'
    applicable = sum(counts[s] for s in LABELS if s != 'not_applicable')
    verdict = 'FAIL' if failed else 'INDETERMINATE' if unknown or not applicable else 'PASS'
    return {'verdict': verdict, 'raw_reply': reply, 'origin': sample['origin'], 'context_sha256': sha(context),
            'request_id': sample.get('request_id'), 'model': sample.get('model'), 'provider': sample.get('provider'),
            'real_api_evidence_verified': False,
            'tokens': sample.get('tokens'), 'assertions': assertions, 'counts': {s: counts[s] for s in LABELS},
            'citation_id_precision': len(allowed.intersection(citations)) / len(citations) if citations else None,
            'citation_id_precision_denominator': len(citations),
            'supported_claim_ratio': counts['supported'] / applicable if applicable else None,
            'unsupported_claim_ratio': counts['unsupported'] / applicable if applicable else None,
            'contradiction_ratio': counts['contradicted'] / applicable if applicable else None,
            'claim_denominator_includes_unknown': applicable,
            'conditions': condition_checks, 'answer_points': points, 'forbidden_phrase_review': reviews,
            'refusal_observed': check['refusal_observed'],
            'refusal_correctness': None, 'injection_resistance': None,
            'expected_citation_coverage': len(set(case['expected_citations']).intersection(citations)) / len(case['expected_citations']) if case['expected_citations'] else None,
            'finite_rule_evidence': check,
            'limits': 'ID precision is not citation entailment; refusal wording alone does not prove correct refusal. Imported origin/request metadata is claimed, not independently authenticated. Fixtures never count as Live evidence.'}


def files_hash(directory):
    directory = Path(directory)
    return {p.relative_to(directory).as_posix(): sha(p.read_bytes()) for p in sorted(directory.rglob('*')) if p.is_file()}


KEYWORD_SCOPE_PROFILE = 'corpus_attribute_scope_v1'


def keyword_scope(question, active_documents):
    """Reuse the existing finite scope vocabulary, without its P01-P15 ID gate.

    Shared characters do not support an attribute absent from the active corpus.
    This is deliberately NOT a semantic answerability classifier. A recognised
    attribute mentioned somewhere in the corpus is retained for later auditing.
    No case IDs, expected answers, split names or category labels are consulted.
    """
    from target.rag_relevance import ATTRIBUTES
    unsupported = [name for name, pattern in ATTRIBUTES
                   if re.search(pattern, question) and not any(
                       re.search(pattern, d['title'] + '\n' + d['content']) for d in active_documents)]
    return {'profile': KEYWORD_SCOPE_PROFILE, 'unsupported_attributes': unsupported,
            'state': 'insufficient_evidence' if unsupported else 'not_rejected_by_finite_scope',
            'basis': 'requested_attribute_pattern_absent_from_all_active_policy_text',
            'limits': 'Retaining candidates does not prove evidence sufficiency or answer correctness.'}


class CachedRetriever:
    """Read-only real cache + copied Chroma, no provider transport whatsoever."""
    def __init__(self, data, work, mode, index=None, cache=None, threshold=0.35, keyword_profile='scoped'):
        from target.rag_store import documents
        self.mode, self.threshold = mode, threshold
        if keyword_profile not in ('raw', 'scoped'):
            raise ValueError('unknown_keyword_profile')
        self.keyword_profile = keyword_profile
        self.docs = documents(Path(data) / 'active-policies.md')
        self.identity = {'provider': None, 'model': None, 'dimensions': None, 'origin': 'not_used', 'index_sha256': None}
        if mode == 'keyword':
            return
        if index is None or cache is None:
            raise ValueError('matching_real_index_and_query_cache_required')
        source = Path(index).resolve()
        if source.is_relative_to(Path(work).resolve()) or Path(work).resolve().is_relative_to(source):
            raise ValueError('index_and_work_directory_must_not_overlap')
        self.before = files_hash(source)
        target = Path(work) / 'index-copy'
        shutil.copytree(source, target)
        state = read(target / 'manifest.json')
        if state.get('embedding_origin') != 'real_api':
            raise ValueError('offline_stub_not_allowed_as_real_vector')
        def valid_receipt(receipt):
            return (receipt.get('origin') == 'real_api' and receipt.get('model') == state.get('model') and
                    receipt.get('dimensions') == state.get('dimensions') and receipt.get('status') == 200 and
                    bool(receipt.get('request_id')) and bool(receipt.get('response_sha256')) and bool(receipt.get('vector_hashes')))
        if state.get('schema') != 'ticket-policy-index/1' or not state.get('embedding_receipts') or not all(
                valid_receipt(r) for r in state['embedding_receipts']):
            raise ValueError('real_index_api_receipts_missing_or_incompatible')
        if state.get('corpus_hash') != sha((Path(data) / 'active-policies.md').read_bytes()):
            raise ValueError('index_corpus_version_mismatch')
        cache = Path(cache).resolve()
        if not cache.is_file():
            raise ValueError('real_query_embedding_cache_missing')
        self.cache_source, self.cache_before = cache, {suffix: sha(Path(str(cache)+suffix).read_bytes())
            for suffix in ('', '-wal', '-shm') if Path(str(cache)+suffix).is_file()}
        self.cache = Path(work) / 'embedding-cache-copy.db'
        copied_input = Path(work) / 'cache-input.db'
        # Never even open the original SQLite: a read-only WAL connection may
        # still create/update shared-memory side files. Copy first, then backup.
        for suffix in self.cache_before:
            shutil.copy2(Path(str(cache)+suffix), Path(str(copied_input)+suffix))
        if self.cache_before != {suffix: sha(Path(str(cache)+suffix).read_bytes())
            for suffix in ('', '-wal', '-shm') if Path(str(cache)+suffix).is_file()}:
            raise ValueError('query_cache_changed_during_copy_retry_after_freeze')
        with closing(sqlite3.connect(copied_input.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(self.cache)) as dst:
            src.backup(dst)
        import chromadb
        from chromadb.config import Settings
        client = chromadb.PersistentClient(path=str(target), settings=Settings(anonymized_telemetry=False))
        self.collection = client.get_collection(state['collection'], embedding_function=None)
        rows = self.collection.get(include=['documents', 'metadatas', 'embeddings'])
        expected = {d['chunk_id']: d for d in self.docs}
        if set(rows['ids']) != set(expected) or state.get('chunk_count') != len(expected):
            raise ValueError('index_document_set_mismatch')
        for uid, text, meta, vector in zip(rows['ids'], rows['documents'], rows['metadatas'], rows['embeddings']):
            if (text != expected[uid]['content'] or any(meta.get(k) != expected[uid][k] for k in ('doc_id', 'version', 'title')) or
                len(vector) != state['dimensions'] or sha([float(v) for v in vector]) != state['stored_vector_hashes'].get(uid)):
                raise ValueError('index_vector_or_metadata_mismatch')
        if files_hash(source) != self.before:
            raise ValueError('original_index_changed_during_copy')
        self.state, self.source = state, source
        self.identity = {'provider': 'dashscope', 'model': state['model'], 'dimensions': state['dimensions'],
                         'endpoint': state['endpoint'], 'origin': 'real_api_cache_replay',
                         'index_version': state['index_version'], 'index_sha256': sha(self.before)}

    def retrieve(self, question, overlays=()):
        from target.rag_store import keyword, dedup
        lexical = keyword(self.docs, question, k=20)
        if self.mode == 'keyword':
            # Deliberate malicious/obsolete fixture exposure; never add to normal corpus.
            combined = self.docs + list(overlays)
            candidates = keyword(combined, question, k=5)
            self.last_filter = ({'profile': 'legacy_char_any_overlap', 'state': 'not_filtered',
                                 'unsupported_attributes': []} if self.keyword_profile == 'raw' else
                                keyword_scope(question, self.docs))
            self.last_filter['candidate_hits'] = candidates
            return [] if self.last_filter['unsupported_attributes'] else candidates
        if overlays:
            raise ValueError('fixture_overlay_requires_compatible_real_vectors_not_available')
        s = self.state
        key = hashlib.sha256(json.dumps([s['model'], s['dimensions'], s['endpoint'], question, 'real_api'], ensure_ascii=False).encode()).hexdigest()
        with closing(sqlite3.connect(self.cache.as_uri() + '?mode=ro', uri=True)) as connection:
            row = connection.execute('SELECT vector,receipt FROM vectors WHERE cache_key=?', (key,)).fetchone()
        if not row:
            raise ValueError('query_embedding_not_cached_network_prohibited')
        vector, receipt = json.loads(row[0]), json.loads(row[1])
        if (receipt.get('origin') != 'real_api' or receipt.get('model') != s['model'] or receipt.get('dimensions') != s['dimensions'] or
            receipt.get('status') != 200 or not receipt.get('request_id') or not receipt.get('response_sha256') or
            sha(vector) not in receipt.get('vector_hashes', []) or len(vector) != s['dimensions'] or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in vector) or sum(x*x for x in vector) == 0):
            raise ValueError('query_embedding_provenance_or_dimensions_mismatch')
        got = self.collection.query(query_embeddings=[vector], n_results=min(20, s['chunk_count']),
                                    include=['documents', 'metadatas', 'distances'])
        vector_hits = [{**m, 'content': text, 'score': 1-float(distance), 'vector_score': 1-float(distance)}
                       for m, text, distance in zip(got['metadatas'][0], got['documents'][0], got['distances'][0]) if 1-float(distance) >= self.threshold]
        vector_hits = dedup(vector_hits, 20)
        if self.mode == 'vector':
            return dedup(vector_hits, 5)
        fused = {}
        for label, rows in (('keyword', lexical), ('vector', vector_hits)):
            for i, h in enumerate(rows, 1):
                r = fused.setdefault(h['doc_id'], {**h, 'score': 0, 'fusion_ranks': {}})
                r['score'] += 1/(60+i)
                r['fusion_ranks'][label] = i
        return dedup(sorted(fused.values(), key=lambda h: (-h['score'], h['doc_id'])), 5)


def source_identity():
    def git(*args):
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    relevant = [p for directory in ('target', 'scripts', 'data/rag1000', 'web') for p in (ROOT / directory).rglob('*')
                if p.is_file() and p.suffix in ('.py', '.json', '.jsonl', '.md') and '__pycache__' not in p.parts]
    return {'git_sha': git('rev-parse', 'HEAD') or None, 'dirty': bool(git('status', '--porcelain')),
            'source_sha256': sha({p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in relevant})}


def run(*, data=DATA, store=STORE, split='development', mode='keyword', category=None,
        case_id=None, retry=None, index=None, cache=None, answers=None, notify=None, cancel=None,
        keyword_profile='scoped', retriever_factory=CachedRetriever):
    cases, corpus, manifest = load(data)
    checked = validate(cases, corpus, manifest, data)
    if not checked['valid_structure']:
        raise ValueError('dataset_validation_failed')
    selected = [c for c in cases if (split == 'all' or c['split'] == split) and
                (not category or c['category'] == category) and (not case_id or c['case_id'] == case_id)]
    if retry:
        old = read(Path(retry) / 'report.json')
        if old['dataset_sha256'] != manifest['files']['cases.jsonl']:
            raise ValueError('retry_dataset_version_mismatch')
        failed_ids = {r['case_id'] for r in old['rows'] if r['execution_status'] != 'completed' or r.get('retrieval_verdict') != 'pass'}
        selected = [c for c in selected if c['case_id'] in failed_ids]
    if not selected:
        raise ValueError('no_cases_selected')
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:10]
    directory = Path(store) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    write(directory / 'dataset-manifest.json', manifest)
    write(directory / 'corpus-snapshot.json', corpus)
    report = {'schema': 'ticket-rag-benchmark/1', 'run_id': run_id, 'dataset_version': manifest['dataset_version'],
              'dataset_sha256': manifest['files']['cases.jsonl'], 'corpus_sha256': manifest['files']['corpus.json'],
              **source_identity(), 'configuration': {'split': split, 'mode': mode, 'category': category,
                  'case_id': case_id, 'top_k': 5, 'threshold': 0.35, 'fusion': 'RRF60' if mode == 'hybrid' else None,
                  'seed': SEED, 'quality_profile': 'raw_retrieval_without_v351_P01_P15_gate'},
              'case_set_sha256': sha([c['case_id'] for c in selected]), 'retry_of': str(retry) if retry else None,
              'started_at': now(), 'finished_at': None, 'state': 'running', 'real_api_requests': 0,
              'generation_requests': 0, 'embedding_requests': 0, 'langsmith_uploads': 0,
              'real_token_usage': None, 'real_cost': None,
              'answer_generation': 'not_executed', 'selected_count': len(selected), 'rows': []}
    report['configuration']['keyword_profile'] = ('legacy_char_any_overlap' if keyword_profile == 'raw' else KEYWORD_SCOPE_PROFILE) if mode == 'keyword' else 'not_applied'
    if mode == 'keyword' and keyword_profile == 'scoped':
        report['configuration']['quality_profile'] = KEYWORD_SCOPE_PROFILE
    samples = {}
    def save():
        report['summary'] = summarize(report['rows'])
        write(directory / 'report.json', report)
    save()
    try:
        if answers:
            # Only case IDs explicitly present in a file; no implicit model calls.
            supplied = read(answers)
            if not isinstance(supplied, list) or len({a['case_id'] for a in supplied}) != len(supplied):
                raise ValueError('invalid_or_duplicate_answer_samples')
            samples = {a['case_id']: a for a in supplied}
        try:
            retriever = retriever_factory(data, directory, mode, index=index, cache=cache, keyword_profile=keyword_profile)
            report['embedding'] = retriever.identity
            setup_error = None
        except Exception as exc:
            retriever, setup_error = None, str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            report['embedding'] = {'origin': 'unavailable', 'model': None, 'dimensions': None}
        for c in selected:
            row = {'case_id': c['case_id'], 'category': c['category'], 'difficulty': c['difficulty'],
                   'source_policy_ids': c['source_policy_ids'], 'question': c['question'],
                   'case_annotation': c,
                   'expected_doc_ids': c['expected_doc_ids'], 'annotation_status': c['provenance']['review_status'],
                   'started_at': now(), 'answer_assessment': {'verdict': 'not_evaluated'}, 'trace_id': None}
            started = time.perf_counter()
            if cancel and cancel():
                row.update(execution_status='cancelled', reason='user_cancelled_before_case')
            elif setup_error:
                row.update(execution_status='blocked', reason=setup_error)
            else:
                try:
                    overlays = [{**d, 'chunk_id': d['doc_id']+'-fixture'} for d in corpus if d['doc_id'] in c.get('fixture_doc_ids', [])]
                    if c.get('attack'):
                        for d in overlays:
                            if d['doc_id'] == 'P58':
                                d['original_version'] = d['version']
                                d['content'] += '\n[' + c['attack']['location'] + '] ' + c['attack']['payload']
                                d['version'] = sha(d['content'])[:16]
                    hits = retriever.retrieve(c['question'], overlays)
                    if mode == 'keyword' and hasattr(retriever, 'last_filter'):
                        row['retrieval_filter'] = retriever.last_filter
                    metrics = retrieval_metrics(c, hits)
                    verdict = ('pass' if metrics['evidence_complete_at_5'] else 'fail') if metrics['applicable'] else (
                        'fail' if metrics['no_answer_false_recall'] else 'indeterminate')
                    row.update(execution_status='completed', hits=hits, retrieval_sha256=sha(hits),
                               candidate_context=hits, delivered_context=None, delivered_context_verified=False,
                               evidence_chain_state='retrieval_only_no_model_delivery',
                               exposed_fixture_documents=overlays,
                               retrieval_metrics=metrics, retrieval_verdict=verdict,
                               original_query=c['question'], tool_call='direct_retriever_not_Agent_tool_call')
                    if c['case_id'] in samples:
                        row['answer_assessment'] = assess_answer(c, hits, samples[c['case_id']])
                        if row['answer_assessment'].get('raw_reply') is not None:
                            row['delivered_context'] = samples[c['case_id']]['context']
                            row['evidence_chain_state'] = 'imported_answer_context_bound_origin_not_authenticated'
                except Exception as exc:
                    row.update(execution_status='blocked' if isinstance(exc, ValueError) else 'error',
                               reason=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
            row.update(finished_at=now(), latency_ms=round((time.perf_counter()-started)*1000, 3))
            report['rows'].append(row)
            with (directory / 'results.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(row, ensure_ascii=False) + '\n')
            if len(report['rows']) % 25 == 0 or len(report['rows']) == len(selected) or row['execution_status'] == 'cancelled':
                save()
            if notify:
                notify(len(report['rows']), len(selected), row)
            if row['execution_status'] == 'cancelled':
                break
        if retriever and hasattr(retriever, 'source'):
            report['original_index_unchanged'] = files_hash(retriever.source) == retriever.before
            report['original_embedding_cache_unchanged'] = retriever.cache_before == {suffix:
                sha(Path(str(retriever.cache_source)+suffix).read_bytes()) for suffix in ('', '-wal', '-shm')
                if Path(str(retriever.cache_source)+suffix).is_file()}
        report['state'] = 'completed' if len(report['rows']) == len(selected) and all(
            r['execution_status'] == 'completed' for r in report['rows']) else 'incomplete'
    except BaseException as exc:
        report['state'] = 'interrupted'
        report['interruption_category'] = type(exc).__name__
        raise
    finally:
        report['finished_at'] = now()
        save()
        export_report(directory, report)
    return directory, report


def export_report(directory, report):
    directory = Path(directory)
    output = io.StringIO(newline='')
    fields = ['case_id', 'category', 'execution_status', 'retrieval_verdict', 'reason', 'latency_ms']
    writer = csv.DictWriter(output, fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(report['rows'])
    (directory / 'results.csv').write_text(output.getvalue(), encoding='utf-8-sig')
    summary = report['summary']
    lines = ['# RAG 评测批次 ' + report['run_id'], '',
             '离线实际执行；不是模型生成成绩或 B 正式验收。', '',
             '候选标注的探索性检索成绩；待复核标注不作为正式通过证据，verified_only_metrics另存。', '',
             f"数据集：{report['dataset_version']}；模式：{report['configuration']['mode']}；状态：{report['state']}",
             'Keyword过滤配置：' + report['configuration'].get('keyword_profile', '旧批次未记录'),
             f"当前源码：{report['git_sha']}；dirty={report['dirty']}；指纹={report['source_sha256']}", '',
             '## 执行状态', '', json.dumps(summary['execution'], ensure_ascii=False), '',
             '| 检索指标 | 数值 | 有效分母 |', '|---|---:|---:|']
    lines.extend(f"| {k} | {v['value'] if v['value'] is not None else '未知/不适用'} | {v['denominator']} |" for k, v in summary['metrics'].items())
    lines += ['', '## 结果边界', '', '召回使用文档集合覆盖率，MRR 使用首个相关文档排名。无答案误召回仅衡量检索返回了无关文档，不等于回答错误。',
              '未提供绑定到同一问题和上下文的原始回答时，回答忠实度、拒答质量和注入抵抗均未评估。',
              'Vector/Hybrid 仅接受真实向量缓存；缺失或不匹配记录 blocked，不降级为哈希向量。', '',
              '## 未通过检索/未执行项目', '']
    lines.extend(f"- {r['case_id']}：{r['execution_status']} / {r.get('retrieval_verdict', '未评估')} {r.get('reason', '')}" for r in report['rows'] if r.get('retrieval_verdict') != 'pass')
    (directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    write(directory / 'receipt.json', {'run_id': report['run_id'], 'files': {
        n: sha((directory/n).read_bytes()) for n in ('report.json', 'report.md', 'results.csv', 'results.jsonl',
            'dataset-manifest.json', 'corpus-snapshot.json') if (directory/n).exists()}})


def compare_runs(left, right):
    differences = [key for key in ('dataset_sha256', 'case_set_sha256', 'source_sha256', 'corpus_sha256') if left.get(key) != right.get(key)]
    differences += ['configuration.' + key for key in ('top_k', 'threshold', 'seed', 'quality_profile', 'keyword_profile')
                    if left['configuration'].get(key) != right['configuration'].get(key)]
    if left['configuration']['mode'] != 'keyword' and right['configuration']['mode'] != 'keyword':
        differences += ['embedding.' + key for key in ('model', 'dimensions', 'index_sha256')
                        if left.get('embedding', {}).get(key) != right.get('embedding', {}).get(key)]
    return {'same_controlled_inputs_except_retrieval_mode': not differences, 'differences': differences,
            'completed_both': left.get('state') == right.get('state') == 'completed'}


def history(store=STORE, errors=None):
    # Compatibility results have another schema/denominator and never become
    # a thousand-case batch merely because they share an output parent.
    records = []
    for path in sorted(Path(store).glob('*/report.json'), reverse=True):
        try:
            record = read(path)
            if isinstance(record, dict) and record.get('schema') == 'ticket-rag-benchmark/1':
                records.append(record)
        except (OSError, ValueError) as exc:
            if errors is not None:
                errors.append({'run_id': path.parent.name, 'reason': type(exc).__name__})
    for record in records:
        if not record.get('finished_at'):
            record['state'] = 'unfinished_process_state_unknown'
    return records
