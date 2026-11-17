"""Restore the two release payloads before running the offline evaluator."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import hashlib
import json
import msvcrt
import os
import shutil
import sys
import tarfile
import tempfile
import time

import zstandard

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'ticket-agent'
PAYLOAD = ROOT / 'payload'
RUNTIME = PROJECT / '.venv-v35'
RUNTIME_MARKER = '.ticket-agent-release.json'
CHUNK_SIZE = 1024 * 1024

def sha256(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()

def say(message):
    print(message, flush=True)

def verified_payload(entry):
    path = PAYLOAD / entry['file']
    if path.stat().st_size != entry['compressed_bytes'] or sha256(path) != entry['compressed_sha256']:
        raise ValueError(f'交付文件校验失败 / Payload verification failed: {path.name}')
    return path

@contextmanager
def release_lock():
    with (ROOT / '.setup.lock').open('a+b') as handle:
        say('正在检查本地运行环境 / Checking local runtime...')
        deadline = time.monotonic() + 120
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('另一个启动窗口尚未完成准备，请稍后重试 / Another setup is still running.')
                time.sleep(0.25)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

def restore_runtime(entry):
    marker = RUNTIME / RUNTIME_MARKER
    version = entry['compressed_sha256']
    if RUNTIME.exists():
        if (marker.is_file() and marker.read_text(encoding='utf-8') == version
                and (RUNTIME / 'Scripts' / 'python.exe').is_file()
                and (RUNTIME / 'Scripts' / 'python312.dll').is_file()):
            return
        raise ValueError('已有不匹配的 Python 目录，请将本 ZIP 解压到空目录 / Extract this ZIP into an empty folder.')

    say('首次启动，正在展开内置 Python 与依赖 / Unpacking Python and dependencies...')
    compressed = verified_payload(entry)
    staging = Path(tempfile.mkdtemp(prefix='.r-', dir=PROJECT)).resolve()
    if staging.parent != PROJECT.resolve() or not staging.name.startswith('.r-'):
        raise ValueError('临时目录路径校验失败 / Invalid temporary directory.')
    files = total = 0
    seen = set()
    try:
        with compressed.open('rb') as stream, zstandard.ZstdDecompressor().stream_reader(stream) as decoded:
            with tarfile.open(fileobj=decoded, mode='r|', bufsize=CHUNK_SIZE) as archive:
                for member in archive:
                    relative = PurePosixPath(member.name)
                    parts = relative.parts
                    windows_name = member.name.casefold()
                    if (not member.isfile() or relative.is_absolute() or not parts
                            or any(part in {'.', '..'} or ':' in part or '\\' in part for part in parts)
                            or windows_name in seen):
                        raise ValueError('内置 Python 文件路径不合法 / Invalid runtime member.')
                    seen.add(windows_name)
                    files += 1
                    total += member.size
                    if files > entry['files'] or total > entry['bytes']:
                        raise ValueError('内置 Python 文件超出清单 / Runtime exceeds its manifest.')
                    out = staging.joinpath(*parts)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, out.open('xb') as target:
                        shutil.copyfileobj(source, target, CHUNK_SIZE)
        if (files, total) != (entry['files'], entry['bytes']):
            raise ValueError('内置 Python 文件缺失 / Runtime is incomplete.')
        (staging / RUNTIME_MARKER).write_text(version, encoding='utf-8')
        staging.rename(RUNTIME)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

def restore_database(entry):
    target = ROOT / entry['path']
    if target.is_file() and target.stat().st_size == entry['bytes'] and sha256(target) == entry['sha256']:
        return
    if target.exists():
        raise ValueError('此处已有校验不符的铁路库，请将 ZIP 解压到空目录 / Existing railway data failed verification.')
    say('正在恢复完整铁路静态库 / Restoring railway data...')
    compressed = verified_payload(entry)
    target.parent.mkdir(exist_ok=True, parents=True)
    digest = hashlib.sha256()
    bytes_written = 0
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.db-', delete=False) as output:
        file = Path(output.name)
        try:
            with compressed.open('rb') as stream, zstandard.ZstdDecompressor().stream_reader(stream) as decoded:
                while block := decoded.read(CHUNK_SIZE):
                    bytes_written += len(block)
                    if bytes_written > entry['bytes']:
                        raise ValueError('铁路库体积超出清单 / Railway data exceeds its manifest.')
                    digest.update(block)
                    output.write(block)
            if bytes_written != entry['bytes'] or digest.hexdigest() != entry['sha256']:
                raise ValueError('铁路库 SHA-256 校验失败 / Railway data verification failed.')
            output.close()
            file.rename(target)
        finally:
            output.close()
            file.unlink(missing_ok=True)

def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors='replace')
    index = json.loads((PAYLOAD / 'index.json').read_text(encoding='utf-8'))
    if index['format'] != 1 or not PROJECT.is_dir():
        raise ValueError('交付目录不完整 / Incomplete release directory.')
    with release_lock():
        needed = 0
        if not RUNTIME.exists():
            needed += index['runtime']['bytes']
        if not (ROOT / index['railway']['path']).exists():
            needed += index['railway']['bytes']
        if needed and shutil.disk_usage(ROOT).free < needed + 16 * CHUNK_SIZE:
            raise OSError('磁盘可用空间不足。首次启动请准备至少 2 GB / Allow 2 GB of free disk space.')
        restore_runtime(index['runtime'])
        restore_database(index['railway'])
    say('运行环境就绪 / Local runtime is ready.')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError, zstandard.ZstdError) as error:
        print(f'启动准备失败 / Setup failed: {error}', file=sys.stderr)
        raise SystemExit(1)

