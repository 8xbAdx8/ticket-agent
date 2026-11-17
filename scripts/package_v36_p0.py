"""补齐 V3.6 交接包的离线回归依赖；不覆盖原包或运行数据。"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.package_team_handoff import scan

SOURCE = ROOT / 'artifacts/deliverables/Ticket-Agent-V3.6-团队交接包-20261028.zip'
SOURCE_SHA256 = '068e8235d69a92a187d346e74fc39eb6adec5db8ea4d73499b06da50d21e205d'
EVIDENCE = (
    'docs/evidence/live-web-repair-20261026/user-manual-deepseek-query.json',
    'docs/evidence/v35/live/generation-result.json',
    'docs/evidence/v352/live/paired-report-resumed.json',
    'docs/evidence/v32/20261018-negation-fix/report.json',
    'docs/evidence/v352/live/retrieval48/report.json',
    'docs/evidence/v35/live/retrieval-evaluation/report.json',
    'docs/evidence/v352/prepared/frozen.json',
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build(output):
    source = SOURCE.read_bytes()
    if digest(source) != SOURCE_SHA256:
        raise ValueError('original package hash mismatch')
    manifest = json.loads((ROOT / 'docs/evidence/v352/cache-package.json').read_text(encoding='utf-8'))
    cache = (ROOT / manifest['path']).read_bytes()
    if digest(cache) != manifest['sha256']:
        raise ValueError('historical cache archive hash mismatch')
    additions = {name: (ROOT / name).read_bytes() for name in EVIDENCE}
    with zipfile.ZipFile(io.BytesIO(cache)) as z:
        for name, expected in manifest['files'].items():
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
                raise ValueError('unsafe cache path')
            raw = z.read(name)
            if digest(raw) != expected:
                raise ValueError('historical cache file hash mismatch: ' + name)
            additions[name] = raw
    # Scan the historical text evidence before including it. Binary Chroma files
    # are separately hash-verified against the historical manifest.
    scan({name: additions[name] for name in EVIDENCE})
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as out:
        existing = set(original.namelist())
        for item in original.infolist():
            out.writestr(item, original.read(item))
        for name, data in additions.items():
            target = 'ticket-agent/' + name
            if target in existing:
                raise ValueError('refuse to overwrite existing archive member: ' + target)
            out.writestr(target, data)
        receipt = {'source_package_sha256': SOURCE_SHA256, 'evidence': {n: digest(additions[n]) for n in EVIDENCE},
                   'cache_files': manifest['files'], 'network_requests': 0}
        out.writestr('ticket-agent/P0_补充证据校验.json', json.dumps(receipt, ensure_ascii=False, indent=2))
        out.writestr('ticket-agent/P0_复测说明.txt', '''V3.6 P0 离线复测包\n本包在原 V3.6 精简包基础上补入指定历史证据和校验过的冻结 RAG 索引及缓存。原包说明中“未包含历史证据”的表述仅适用于原包。历史证据不是本次成绩，转发前需审查其内容。\nWindows 新机器：在本目录执行 py -3.12 -m venv .venv-v35，然后 .\\.venv-v35\\Scripts\\python.exe -m pip install -r requirements-v35-lock.txt。离线测试前清空模型密钥环境变量并关闭 LangSmith；执行 .\\.venv-v35\\Scripts\\python.exe -m pytest tests -q。建议使用网络隔离环境，避免意外联网。\n不要把此包解压覆盖现有项目、数据库、索引或历史证据。\n''')
    with zipfile.ZipFile(output) as z:
        if z.testzip():
            raise ValueError('zip CRC failed')
    print('created:', output)
    print('sha256:', digest(output.read_bytes()))


if __name__ == '__main__':
    target = ROOT / 'artifacts/deliverables/Ticket-Agent-V3.6-P0-离线复测包-20261029-v2.zip'
    build(target)
