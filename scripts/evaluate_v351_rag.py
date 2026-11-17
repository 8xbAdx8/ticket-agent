"""Offline-only V3.5.1 retrieval evaluation; no keys, SDKs, HTTP or index writes.

Original thirty queries replay already published real vectors. New development and
holdout questions have no paid query vectors: only keyword/guard is evaluated.
Threshold selection reads development labels only, then persists an immutable
selection before the holdout is parsed or scored. No model refusal is inferred
from a retrieval rejection.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MODES = ('keyword', 'vector', 'hybrid')
MIN_KEYWORD_GRID = (0.0, 0.5, 1.0)
VECTOR_WEIGHT = 0.7
VECTOR_THRESHOLD = 0.35
TOP_K = 3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def frozen_keyword(chunks, question):
    """Reproduce the original V3.5 scorer; this is a frozen evaluator baseline."""
    def tokenize(text):
        return [c for c in text if '\u4e00' <= c <= '\u9fff'] + re.findall(r'[a-zA-Z0-9]+', text)
    terms = set(tokenize(question))
    hits = []
    for chunk in chunks:
        words = tokenize(chunk['title'] + chunk['content'])
        score = sum(word in terms for word in words) / math.sqrt(len(words)) if words else 0
        if score > 0:
            hits.append({**chunk, 'score': score, 'keyword_score': score})
    hits.sort(key=lambda hit: (-hit['score'], hit['chunk_id']))
    return ranked(hits)


def ranked(hits):
    seen = set()
    out = []
    for hit in hits:
        if hit['doc_id'] not in seen:
            seen.add(hit['doc_id'])
            out.append({**hit, 'rank': len(out) + 1})
    return out


def cosine(a, b):
    norm_a = math.sqrt(sum(float(x) ** 2 for x in a))
    norm_b = math.sqrt(sum(float(x) ** 2 for x in b))
    if len(a) != len(b) or not norm_a or not norm_b:
        raise ValueError('invalid_published_vectors')
    return sum(float(x) * float(y) for x, y in zip(a, b)) / (norm_a * norm_b)


def frozen_vector(chunks, query, vectors):
    hits = []
    for chunk in chunks:
        score = cosine(query, vectors[chunk['chunk_id']])
        if score >= VECTOR_THRESHOLD:
            hits.append({**chunk, 'score': score, 'vector_score': score})
    return ranked(sorted(hits, key=lambda hit: (-hit['score'], hit['doc_id'])))


def metrics(cases, results):
    from target.rag_quality import retrieval_metrics
    return retrieval_metrics(cases, results, TOP_K)


def summary_metrics(value):
    return {key: child for key, child in value.items() if key != 'rows'}


def decide(result):
    return {
        'retrieval_refusal_decision': 'refuse_due_to_no_evidence' if not result.get('hits') else 'evidence_available_review_support',
        'model_refusal': 'not_run',
        'basis': 'Retrieval evidence presence only; no model generation or semantic success inferred',
    }


def compare_rows(cases, before, after, mode, split):
    rows = []
    for case in cases:
        identity = case['id']
        old = before[identity]
        new = after[identity]
        expected = set(case['expected_doc_ids'])
        old_ids = [h['doc_id'] for h in old.get('hits', [])[:TOP_K]]
        new_ids = [h['doc_id'] for h in new.get('hits', [])[:TOP_K]]
        rows.append({
            'case_id': identity, 'split': split, 'mode': mode,
            'question': case['question'], 'scenario': case.get('scenario'),
            'expected_doc_ids': case['expected_doc_ids'], 'label_reason': case.get('reason'),
            'before': copy.deepcopy(old), 'after': copy.deepcopy(new),
            'before_recall_at_k': len(expected.intersection(old_ids)) / len(expected) if expected else None,
            'after_recall_at_k': len(expected.intersection(new_ids)) / len(expected) if expected else None,
            'before_no_answer_false_recall': bool(old_ids) if not expected else None,
            'after_no_answer_false_recall': bool(new_ids) if not expected else None,
            'decision': decide(new),
            'judgement_basis': 'Fixed expected doc IDs; nonempty retrieval for a no-answer case is false recall; ranks/scores and guard reasons are retained.',
        })
    return rows


def keyword_split(cases, chunks, minimum):
    from target.rag_relevance import apply_quality
    before, after = {}, {}
    for case in cases:
        lexical = frozen_keyword(chunks, case['question'])
        before[case['id']] = {'mode': 'keyword', 'hits': lexical[:TOP_K]}
        after[case['id']] = apply_quality(case['question'], copy.deepcopy(lexical), [], 'keyword',
                                         k=TOP_K, min_keyword_score=minimum, vector_weight=VECTOR_WEIGHT)
    return before, after


def new_split_report(cases, chunks, minimum, split):
    before, after = keyword_split(cases, chunks, minimum)
    unsupported = {mode: {
        'status': 'not_run', 'reason': 'No genuine query embeddings exist for this new split. No synthetic vectors substituted.',
        'cases': len(cases), 'recall_at_k': None, 'mrr': None, 'no_answer_false_recall_rate': None,
    } for mode in ('vector', 'hybrid')}
    return {
        'split': split, 'status': 'executed_keyword_only', 'minimum_keyword_score': minimum,
        'keyword': {'before': metrics(cases, before), 'after': metrics(cases, after)},
        **unsupported, 'rows': compare_rows(cases, before, after, 'keyword', split),
        'generated_answers': 0, 'model_refusal_rate': None,
        'scope': 'Offline lexical/guard decision quality only; no new real-vector or model-generation result.',
    }


def evaluate_original(chunks, minimum, original, query_vectors, exported):
    from target.rag_quality import query_text
    from target.rag_relevance import apply_quality
    cases = original['cases']
    qmap = {q['case_id']: q for q in query_vectors['queries']}
    vectors = {c['chunk_id']: c['embedding'] for c in exported['chunks']}
    original_report = read(ROOT / 'docs/evidence/v35/live/retrieval-evaluation/report.json')
    after = {mode: {} for mode in MODES}
    cosine_errors = []
    for case in cases:
        question = query_text(case)
        if question != qmap[case['id']]['embedding_query']:
            raise ValueError('published_query_text_mismatch')
        lexical = frozen_keyword(chunks, question)
        vector_hits = frozen_vector(chunks, qmap[case['id']]['vector'], vectors)
        for mode in MODES:
            after[mode][case['id']] = apply_quality(question, copy.deepcopy(lexical), copy.deepcopy(vector_hits), mode,
                                                  k=TOP_K, min_keyword_score=minimum, vector_weight=VECTOR_WEIGHT)
        for hit in original_report['results']['vector'][case['id']]['hits']:
            recomputed = next(h['score'] for h in vector_hits if h['doc_id'] == hit['doc_id'])
            cosine_errors.append(abs(hit['score'] - recomputed))
    report = {'status': 'offline_replay_of_published_real_vectors', 'split': 'fixed_v35_regression',
              'cases': len(cases), 'minimum_keyword_score': minimum, 'metrics': {}, 'rows': [],
              'index_version': exported['index_version'], 'embedding_origin': 'published_real_api_vectors',
              'scope': 'Cached real-vector replay is not a new Live run; after-ranking uses current V3.5.1 rules.',
              'generation_requests': 0, 'embedding_requests': 0, 'model_refusal_rate': None,
              'max_cosine_reconstruction_error': max(cosine_errors, default=None)}
    for mode in MODES:
        before = original_report['results'][mode]
        old = metrics(cases, before)
        for key in ('recall_at_k', 'mrr', 'no_answer_false_recall_rate'):
            if not math.isclose(old[key], original_report['metrics'][mode][key], abs_tol=1e-12):
                raise ValueError('historical_metric_reconstruction_mismatch')
        report['metrics'][mode] = {'before': old, 'after': metrics(cases, after[mode])}
        report['rows'].extend(compare_rows(cases, before, after[mode], mode, 'fixed_v35_regression'))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='Brand-new directory under artifacts/runtime')
    parser.add_argument('--development-only', action='store_true', help='Freeze selection without parsing/evaluating holdout')
    args = parser.parse_args(argv)
    out = args.out.resolve()
    runtime = (ROOT / 'artifacts/runtime').resolve()
    if not out.is_relative_to(runtime) or out == runtime or out.exists():
        raise ValueError('new_isolated_runtime_output_required')
    out.mkdir(parents=True, exist_ok=False)
    dev_path = ROOT / 'cases/rag_quality_v351_development.json'
    policy_path = ROOT / 'data/policies.md'
    original_path = ROOT / 'cases/rag_quality_v35.json'
    original_report_path = ROOT / 'docs/evidence/v35/live/retrieval-evaluation/report.json'
    queries_path = ROOT / 'docs/evidence/v35/live/retrieval-evaluation/query_vectors.json'
    vectors_path = ROOT / 'docs/evidence/v35/real-index-export.json'
    # Do not import EmbeddingProvider, bootstrap, Chroma or any model SDK here.
    from target.rag_store import documents
    chunks = documents(policy_path)
    dev = read(dev_path)
    if dev.get('split') != 'development' or not dev.get('frozen_before_tuning'):
        raise ValueError('frozen_development_split_required')
    if not any(c['expected_doc_ids'] for c in dev['cases']) or not any(not c['expected_doc_ids'] for c in dev['cases']):
        raise ValueError('development_positive_and_negative_controls_required')
    trial_reports = {minimum: new_split_report(dev['cases'], chunks, minimum, 'development')
                     for minimum in MIN_KEYWORD_GRID}
    def objective(minimum):
        value = trial_reports[minimum]['keyword']['after']
        return (-value['recall_at_k'], value['no_answer_false_recall_rate'], minimum)
    selected = min(MIN_KEYWORD_GRID, key=objective)
    selection = {
        'schema': 'ticket-v351-frozen-selection/1', 'selection_split': 'development_only',
        'objective': 'Maximize positive Recall@3, then minimize no-answer false recall, then choose the smallest threshold.',
        'grid': list(MIN_KEYWORD_GRID), 'selected_min_keyword_score': selected,
        'vector_weight_fixed_not_tuned': VECTOR_WEIGHT, 'top_k': TOP_K, 'vector_threshold_unchanged': VECTOR_THRESHOLD,
        'development_sha256': sha(dev_path), 'policy_sha256': sha(policy_path),
        'algorithm_sha256': {name: sha(ROOT / name) for name in
                             ('target/rag_relevance.py', 'target/rag_store.py', 'scripts/evaluate_v351_rag.py')},
        'holdout_read_or_scored_during_selection': False,
        'trials': [{'minimum': minimum, 'before': summary_metrics(trial_reports[minimum]['keyword']['before']),
                    'after': summary_metrics(trial_reports[minimum]['keyword']['after'])} for minimum in MIN_KEYWORD_GRID],
    }
    selection_path = out / 'selection.json'
    write_new(selection_path, selection)
    selection_hash = sha(selection_path)
    write_new(out / 'development.json', {'selected': selected, 'trials': {str(k): v for k, v in trial_reports.items()}})
    original = read(original_path)
    query_vectors, exported = read(queries_path), read(vectors_path)
    if query_vectors.get('origin') != 'real_api' or not exported.get('verified_against_persisted_chroma'):
        raise ValueError('published_real_vector_provenance_required')
    original_result = evaluate_original(chunks, selected, original, query_vectors, exported)
    write_new(out / 'original30.json', original_result)
    holdout = None
    inputs = (dev_path, policy_path, original_path, original_report_path, queries_path, vectors_path)
    if not args.development_only:
        # Exclusive marker written after immutable selection, before opening holdout.
        write_new(out / 'holdout-attempt.json', {'selection_sha256': selection_hash,
                  'scope': 'One held-out evaluation in this evidence directory, without retuning', 'model_requests': 0})
        holdout_path = ROOT / 'cases/rag_quality_v351_holdout.json'
        held = read(holdout_path)
        if held.get('split') != 'holdout' or not held.get('frozen_before_tuning'):
            raise ValueError('frozen_holdout_split_required')
        if {c['id'] for c in dev['cases']} & {c['id'] for c in held['cases']}:
            raise ValueError('development_holdout_ids_overlap')
        holdout = new_split_report(held['cases'], chunks, selected, 'holdout')
        write_new(out / 'holdout.json', holdout)
        inputs += (holdout_path,)
    if sha(selection_path) != selection_hash:
        raise ValueError('selection_changed_after_freeze')
    summary = {
        'schema': 'ticket-v351-offline-quality/1', 'status': 'executed',
        'source_head': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        'selected_min_keyword_score': selected, 'selection_sha256': selection_hash,
        'algorithm_sha256': selection['algorithm_sha256'],
        'input_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs},
        'fixed30': {mode: {stage: summary_metrics(value) for stage, value in pair.items()}
                    for mode, pair in original_result['metrics'].items()},
        'development': {stage: summary_metrics(value) for stage, value in trial_reports[selected]['keyword'].items()},
        'holdout': {stage: summary_metrics(value) for stage, value in holdout['keyword'].items()} if holdout else {'status': 'not_run'},
        'new_split_vector_and_hybrid': 'not_run_no_genuine_query_vectors',
        'real_generation_requests': 0, 'real_embedding_requests': 0, 'langsmith_requests': 0,
        'token_usage': None, 'new_remote_api_cost': 0, 'cost_basis': 'No remote API requests in this offline evaluator',
        'model_refusal_rate': None,
        'limits': ['Retrieval refusal decisions are not observed model refusals.',
                   'Original30 real-vector replay is offline evidence, not a post-fix Live run.',
                   'New split vector/hybrid metrics are unknown until separately authorized real query embeddings exist.',
                   'Hand-authored A holdout is independently split but is not B blinded formal acceptance.'],
    }
    write_new(out / 'summary.json', summary)
    with (out / 'rows.jsonl').open('x', encoding='utf-8', newline='\n') as handle:
        all_rows = original_result['rows'] + trial_reports[selected]['rows'] + (holdout['rows'] if holdout else [])
        for row in all_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'category': type(exc).__name__,
                          'real_generation_requests': 0, 'real_embedding_requests': 0}))
        raise SystemExit(1)
