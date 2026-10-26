"""Offline verification for a fresh extracted team ZIP; .git is not required.

Creates a NEW runtime directory, clears credentials, blocks non-loopback Python
network, copies Chroma inputs, and checks all shipped immutable file hashes.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from run_deepseek_review_offline import GUARD
from verify_v351_offline import isolated_rag_inputs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='New directory below artifacts/runtime')
    args = parser.parse_args()
    manifest_path = ROOT / '交接文件校验.json'
    if not manifest_path.is_file():
        parser.error('Run this command in a fresh extracted team package containing 交接文件校验.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    protected = manifest['files']
    missing_or_changed = [name for name, value in protected.items() if sha(ROOT / name) != value]
    if missing_or_changed:
        print(json.dumps({'status': 'failed', 'package_files_missing_or_changed': missing_or_changed}, ensure_ascii=False))
        return 1
    out = (args.out or ROOT / 'artifacts/runtime' / ('package-check-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])).resolve()
    if not out.is_relative_to(ROOT / 'artifacts/runtime') or out == ROOT / 'artifacts/runtime':
        parser.error('isolated output under artifacts/runtime required')
    out.mkdir(parents=True, exist_ok=False)
    guard = out / 'guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text(GUARD, encoding='utf-8')
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('AGENT_', 'DEEPSEEK_', 'DASHSCOPE_', 'RAG_', 'LANGCHAIN_', 'LANGSMITH_', 'TICKET_', 'V352_'))
           and not key.endswith(('_API_KEY', '_TOKEN')) and key not in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS')}
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONPATH=str(guard) + os.pathsep + str(ROOT),
               TICKET_DISABLE_LOCAL_SECRETS='1', TICKET_WEB_OFFLINE_ONLY='1', RAG_ALLOW_NETWORK='0',
               AGENT_PROVIDER='mock', AGENT_ENGINE='legacy', AGENT_MODEL='mock-offline', AGENT_RAG_MODE='',
               AGENT_USE_HTTP='0', AGENT_VECTOR_RAG='0', AGENT_MUTATIONS='{}', RAG_QUALITY_PROFILE='v351',
               AGENT_DB_PATH=str(out / 'unused.db'), AGENT_TRACE_DIR=str(out / 'unused-traces'),
               LANGCHAIN_TRACING_V2='false', LANGSMITH_TRACING='false',
               TICKET_OFFLINE_GUARD_LOG=str(out / 'blocked-network.jsonl'),
               GIT_CEILING_DIRECTORIES=str(ROOT.parent))
    env.update(isolated_rag_inputs(ROOT, out))
    runs = []

    def run(name, command, extra=None):
        proc = subprocess.run(command, cwd=ROOT, env=dict(env, **(extra or {})), capture_output=True,
                              text=True, encoding='utf-8', timeout=900)
        console = (proc.stdout + proc.stderr).replace(str(ROOT), '<package>').replace(str(Path.home()), '<user>')
        (out / (name + '.txt')).write_text(console, encoding='utf-8')
        runs.append({'name': name, 'exit_code': proc.returncode})
        print(json.dumps(runs[-1]), flush=True)
        return console

    console = run('pytest', [sys.executable, '-m', 'pytest', 'tests', '-q', '--disable-warnings',
                            '--junitxml', str(out / 'pytest.xml')],
                  {'V352_PROTOCOL_EVIDENCE_OUT': str(out / 'sdk-protocol')})
    run('mock_smoke', [sys.executable, 'scripts/smoke.py', '--output-dir', str(out / 'smoke')])
    run('retrieval48', [sys.executable, 'scripts/evaluate_v352_rag.py', '--out', str(out / 'retrieval48')])
    run('launcher_preflight', [sys.executable, 'scripts/launch_app.py', '--mode', 'offline', '--check-only'])
    suites = list(ET.parse(out / 'pytest.xml').getroot().iter('testsuite'))
    counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    changed = [name for name, value in protected.items() if sha(ROOT / name) != value]
    blocked = sum(len(p.read_text(encoding='utf-8').splitlines()) for p in out.rglob('*blocked*network*.jsonl'))
    passed = re.search(r'(\d+) passed', console)
    subtests = re.search(r'(\d+) subtests passed', console)
    retrieval_path = out / 'retrieval48/report.json'
    retrieval = json.loads(retrieval_path.read_text(encoding='utf-8')) if retrieval_path.exists() else {}
    complete_retrieval = retrieval.get('status') == 'completed' and retrieval.get('source_index_unchanged') is True
    report = {'schema': 'ticket-extracted-package-check/1',
              'status': 'passed' if all(r['exit_code'] == 0 for r in runs) and not changed and not blocked and complete_retrieval else 'failed',
              'source_commit': manifest['source_commit'], 'python_version': sys.version.split()[0],
              'pytest': {'passed': int(passed[1]) if passed else None, 'subtests_passed': int(subtests[1]) if subtests else 0, 'junit': counts},
              'runs': runs, 'retrieval48_completed': complete_retrieval,
              'retrieval48_metrics': {mode: {k: v for k, v in value.items() if k != 'rows'}
                                      for mode, value in retrieval.get('metrics', {}).get('all48', {}).items()},
              'protected_files': len(protected), 'changed_packaged_files': changed, 'blocked_network_attempts': blocked,
              'model_requests': 0, 'embedding_requests': 0, 'langsmith_requests': 0,
              'scope': 'A package verification with installed dependencies; not B formal evaluation or fresh pip installation',
              'report': out.relative_to(ROOT).as_posix() + '/report.json'}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
