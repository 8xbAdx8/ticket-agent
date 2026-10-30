"""Offline RAG benchmark CLI, separate from the original 30/48-case evaluator."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from target import rag_benchmark as benchmark


def compatibility(store):
    """Old 48 cases, their own old corpus and denominator; never merged into v1."""
    from target.rag_store import documents, keyword
    manifest = benchmark.load()[2]
    rows = []
    for name, expected_hash in manifest['legacy_48_compatibility_files'].items():
        path = ROOT / name
        if benchmark.sha(path.read_bytes()) != expected_hash:
            raise ValueError('legacy_48_changed:' + name)
        for c in benchmark.read(path)['cases']:
            hits = keyword(documents(ROOT / 'data/policies.md'), c['question'], 5)
            item = {'expected_doc_ids': c['expected_doc_ids'], 'category': 'normal_qa' if c['expected_doc_ids'] else 'no_answer'}
            rows.append({'case_id': c['id'], 'question': c['question'], 'source_file': name, 'hits': hits,
                         'metrics': benchmark.retrieval_metrics(item, hits)})
    directory = Path(store) / ('legacy48-' + benchmark.uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    report = {'dataset': 'historical_48_compatibility_not_new_1000', 'real_api_requests': 0,
              'rows': rows, 'count': len(rows), 'corpus_sha256': benchmark.sha((ROOT/'data/policies.md').read_bytes()),
              'metrics': {key: benchmark.ratio(r['metrics'][key] for r in rows) for key in (
                  'recall_at_1', 'recall_at_3', 'recall_at_5', 'mrr', 'no_answer_false_recall')}}
    benchmark.write(directory / 'report.json', report)
    return directory, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('validate')
    check.add_argument('--out', type=Path)
    execute = sub.add_parser('run')
    execute.add_argument('--split', choices=['development', 'validation', 'holdout', 'all'], default='development')
    execute.add_argument('--mode', choices=['keyword', 'vector', 'hybrid'], default='keyword')
    execute.add_argument('--keyword-profile', choices=['raw', 'scoped'], default='scoped',
                         help='raw preserves pre-fix results; scoped checks existing finite corpus attribute scope')
    execute.add_argument('--category', choices=list(benchmark.QUOTAS))
    execute.add_argument('--case-id')
    execute.add_argument('--retry-run', type=Path)
    execute.add_argument('--index', type=Path, help='Existing compatible REAL index, copied before opening')
    execute.add_argument('--cache', type=Path, help='Existing real query embeddings, copied before reading')
    execute.add_argument('--answers', type=Path, help='JSON list: saved answers bound to exact question/context hashes')
    execute.add_argument('--out', type=Path, default=benchmark.STORE)
    show = sub.add_parser('report')
    show.add_argument('--run-id', required=True)
    show.add_argument('--store', type=Path, default=benchmark.STORE)
    old = sub.add_parser('compatibility')
    old.add_argument('--out', type=Path, default=benchmark.STORE)
    args = parser.parse_args()
    if args.command == 'validate':
        c, d, m = benchmark.load()
        result = benchmark.validate(c, d, m)
        if args.out:
            if args.out.exists():
                raise ValueError('validation_output_already_exists')
            benchmark.write(args.out, result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('near_duplicates', 'needs_review')}, ensure_ascii=False))
        return 0 if result['valid_structure'] else 1
    if args.command == 'run':
        directory, report = benchmark.run(split=args.split, mode=args.mode, category=args.category,
            case_id=args.case_id, retry=args.retry_run, index=args.index, cache=args.cache,
            answers=args.answers, store=args.out, keyword_profile=args.keyword_profile)
        print(json.dumps({'directory': str(directory), 'state': report['state'],
            **{k: v for k, v in report['summary'].items() if not k.startswith('by_')}}, ensure_ascii=False))
        return 0 if report['state'] == 'completed' else 2
    if args.command == 'compatibility':
        directory, report = compatibility(args.out)
        print(json.dumps({'directory': str(directory), 'count': report['count'], 'metrics': report['metrics']}, ensure_ascii=False))
        return 0
    if Path(args.run_id).name != args.run_id or args.run_id in ('.', '..'):
        raise ValueError('invalid_run_id')
    path = args.store / args.run_id
    report = benchmark.read(path / 'report.json')
    print((path / 'report.md').read_text(encoding='utf-8'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
