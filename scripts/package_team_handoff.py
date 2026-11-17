"""Build a secret-checked handoff from committed Git blobs and a frozen cache ZIP.

No network, model calls, dependency installation or changes to existing runtime data.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CACHE_MANIFEST = 'docs/evidence/v352/cache-package.json'
HISTORICAL_DB = 'docs/evidence/deepseek/api-20261016-001224-2c3484/tickets.db'
TOKEN = re.compile(rb'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def safe_name(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name


def permitted(name):
    if not safe_name(name):
        return False
    parts = PurePosixPath(name).parts
    if any(p in ('.git', '__pycache__', '.pytest_cache', 'node_modules') or p.startswith('.venv') for p in parts):
        return False
    if name.startswith(('artifacts/runtime/', 'artifacts/deliverables/')):
        return False
    base = parts[-1].lower()
    if (base == '.env' or base.startswith('.env.')) and base != '.env.example':
        return False
    if base.endswith(('.zip', '.7z', '.pem', '.key', '.p12', '.pyc', '.log')):
        return False
    if base.endswith(('.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm')):
        return name == HISTORICAL_DB
    return True


def known_secrets():
    # Only compare in memory. Never return secret text in logs or reports.
    values = {v for k, v in os.environ.items() if k.endswith(('_API_KEY', '_TOKEN')) and len(v) >= 12}
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, index)
                    if name.endswith(('_API_KEY', '_TOKEN')) and isinstance(value, str) and len(value) >= 12:
                        values.add(value)
        except OSError:
            pass
    return {v.encode(encoding) for v in values for encoding in ('utf-8', 'utf-16-le')}


def scan(files):
    secrets = known_secrets()
    findings = []

    def inspect(name, data, depth=0):
        if any(value in data for value in secrets):
            findings.append({'path': name, 'reason': 'configured_credential'})
        if TOKEN.search(data) or re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', data):
            findings.append({'path': name, 'reason': 'credential_pattern'})
        if depth < 2 and data.startswith(b'PK\x03\x04'):
            with zipfile.ZipFile(io.BytesIO(data)) as inner:
                for member in inner.infolist():
                    if not member.is_dir():
                        inspect(name + '!' + member.filename, inner.read(member), depth + 1)

    for name, data in files.items():
        inspect(name, data)
    if findings:
        raise ValueError(json.dumps({'secret_scan': 'failed', 'findings': findings}, ensure_ascii=False))
    return {'status': 'passed', 'files': len(files), 'configured_credentials_checked': True,
            'nested_office_zip_checked': True, 'scope': 'known credentials, token patterns and private keys; image text is not OCR-scanned'}


def frozen_serialization(files):
    """Reproduce original frozen fixture bytes, using recorded hashes as authority.

    Earlier Windows evidence was frozen as CRLF before Git normalized its blobs.
    Only an LF/CRLF conversion whose hash equals the PREEXISTING manifest is
    accepted. Neither labels nor assertions nor original worktree files change.
    """
    base = 'web/datasets/b_v32_20261020/'
    expected = {base + name: spec['sha256']
                for name, spec in json.loads(files[base + 'manifest.json'])['files'].items()}
    old = json.loads(files['docs/evidence/v35/live/retrieval-evaluation/report.json'])
    expected['cases/rag_quality_v35.json'] = old['dataset_sha256']
    rows = json.loads(files['docs/evidence/v352/offline/authorized-final/retrieval/report.json'])
    expected.update({f'cases/rag_quality_v351_{split}.json': digest for split, digest in rows['input_sha256'].items()})
    receipt = []
    for name, digest in expected.items():
        original = files[name]
        if sha(original) == digest:
            continue
        lf = original.replace(b'\r\n', b'\n')
        match = next((data for data in (lf, lf.replace(b'\n', b'\r\n')) if sha(data) == digest), None)
        if match is None:
            raise ValueError('frozen_fixture_content_mismatch: ' + name)
        files[name] = match
        receipt.append({'path': name, 'git_blob_sha256': sha(original), 'frozen_sha256': digest,
                        'change': 'line_endings_only_matching_historical_manifest'})
    return receipt


def build(destination):
    if git('diff', '--name-only').strip() or git('diff', '--cached', '--name-only').strip():
        raise ValueError('commit_tracked_changes_before_packaging')
    head = git('rev-parse', 'HEAD').decode().strip()
    branch = git('branch', '--show-current').decode().strip()
    files = {}
    excluded = []
    # Windows core.autocrlf also affects git archive. Keep committed LF bytes,
    # especially the policy corpus hash bound to the immutable Chroma manifest.
    with zipfile.ZipFile(io.BytesIO(git('-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
                                       'archive', '--format=zip', 'HEAD'))) as snapshot:
        for member in snapshot.infolist():
            if member.is_dir():
                continue
            if not permitted(member.filename):
                excluded.append(member.filename)
                continue
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('symlink_in_source_snapshot')
            files[member.filename] = snapshot.read(member)
    serialization = frozen_serialization(files)
    manifest = json.loads(files[CACHE_MANIFEST])
    cache_zip = ROOT / manifest['path']
    raw = cache_zip.read_bytes()
    if sha(raw) != manifest['sha256']:
        raise ValueError('frozen_cache_archive_hash_mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as cached:
        # The frozen archive also carries two human-readable metadata files;
        # the team package supplies its own entry guide and file manifest.
        metadata = {'V352_真实缓存使用前必读.md', 'V352_真实缓存文件哈希.json'}
        if set(cached.namelist()) != set(manifest['files']) | metadata or cached.testzip():
            raise ValueError('frozen_cache_archive_members_mismatch')
        for name, expected in manifest['files'].items():
            data = cached.read(name)
            if not safe_name(name) or name in files or sha(data) != expected:
                raise ValueError('frozen_cache_member_mismatch')
            files[name] = data
    index = json.loads(files['artifacts/runtime/v35-rag/index/manifest.json'])
    if sha(files['data/policies.md']) != index['corpus_hash']:
        raise ValueError('packaged_policy_bytes_differ_from_frozen_index')
    version = {'schema': 'ticket-team-delivery/1', 'source_commit': head, 'source_branch': branch,
               'created_utc': datetime.now(timezone.utc).isoformat(), 'repository_metadata_included': False,
               'historically_tested_application_commit': '558a5cddea2dce4ed3437499f76aa8a7b5de52ff',
               'historical_pytest_passed': 595, 'historical_subtests_passed': 94,
               'frozen_cache_archive_sha256': manifest['sha256'], 'live_tools': ['query_tickets', 'search_policy'],
               'packaging_real_requests': 0, 'excluded_tracked_paths': excluded,
               'historical_synthetic_db_exception': HISTORICAL_DB,
               'frozen_file_serialization': serialization,
               'note': 'Package source ID is supplied here; ZIP is not a Git checkout. Historical evidence is not a new Live run.'}
    files['交付版本.json'] = json_bytes(version)
    safety = scan(files)
    file_hashes = {name: sha(data) for name, data in sorted(files.items())}
    files['交接文件校验.json'] = json_bytes({'schema': 'ticket-package-files/1', 'source_commit': head, 'files': file_hashes})
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d')
    output = destination / f'Ticket-Agent_团队交接包_{stamp}_{head[:8]}.zip'
    report_path = output.with_suffix('.contents.json')
    digest_path = output.with_suffix('.sha256.txt')
    if any(p.exists() for p in (output, report_path, digest_path)):
        raise ValueError('delivery_already_exists_do_not_overwrite')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            archive.writestr('ticket-agent/' + name, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise ValueError('delivery_zip_crc_failed')
    digest = sha(output.read_bytes())
    digest_path.write_text(digest + '  ' + output.name + '\n', encoding='utf-8')
    report = {'schema': 'ticket-package-check/1', 'status': 'passed', 'zip': output.name,
              'sha256': digest, 'bytes': output.stat().st_size, 'files': len(files), 'source_commit': head,
              'source_branch': branch, 'zip_crc': 'passed', 'secret_scan': safety,
              'frozen_cache_files': len(manifest['files']), 'policy_hash_matches_index': True,
              'frozen_fixture_line_endings_verified': len(serialization),
              'untracked_user_files_included': False, 'real_requests': 0,
              'extraction_verification': 'Run scripts/check_team_package.py in a fresh extracted folder; result is separate.'}
    report_path.write_bytes(json_bytes(report))
    print(json.dumps(report, ensure_ascii=False))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts/deliverables')
    args = parser.parse_args()
    destination = args.out.resolve()
    if not destination.is_relative_to(ROOT / 'artifacts/deliverables'):
        parser.error('output must be within artifacts/deliverables')
    build(destination)


if __name__ == '__main__':
    main()
