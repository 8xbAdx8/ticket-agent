"""本地安全扫描：工作区、归档、Git 历史；仅报告位置，不输出匹配内容。"""
import argparse
import json
import os
import re
import subprocess
import urllib.parse
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
TOKEN=re.compile(rb'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b')
PRIVATE=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=\r\n]{32,}-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')


def scan(save=True):
    known=[v.encode() for k,v in os.environ.items() if (k.endswith('_API_KEY') or k.endswith('_TOKEN')) and len(v)>=12]
    def hit(data):
        return bool(TOKEN.search(data) or PRIVATE.search(data) or any(s in data for s in known))
    issues=[];items=0;skipped_large=[];local_secret_stores=[]
    tracked={p for p in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0') if p}
    for path in ROOT.rglob('*'):
        if not path.is_file(): continue
        relative=path.relative_to(ROOT)
        if any(part in {'.git','.venv','.venv-v3','.venv-deepseek','__pycache__','.pytest_cache'} for part in relative.parts):continue
        name=relative.as_posix()
        if path.stat().st_size>15_000_000:
            skipped_large.append(name);continue
        is_secret_store=path.name.startswith('.env') or path.suffix.lower() in ('.key','.pem')
        if is_secret_store:
            ignored=subprocess.run(['git','check-ignore','-q',name],cwd=ROOT).returncode==0
            local_secret_stores.append({'path':name,'tracked':name in tracked,'ignored':ignored})
            if not ignored or name in tracked: issues.append({'path':name,'kind':'secret_store_not_safely_excluded'})
        entries=[]
        if path.suffix.lower() in ('.zip','.docx'):
            try:
                with zipfile.ZipFile(path) as archive:
                    entries=[(i.filename,archive.read(i)) for i in archive.infolist() if not i.is_dir() and i.file_size<=4_000_000]
            except zipfile.BadZipFile:
                issues.append({'path':name,'kind':'archive_unreadable'})
        else:entries=[('',path.read_bytes())]
        for inner,data in entries:
            items+=1
            if hit(data) and not (is_secret_store and name not in tracked and ignored):
                issues.append({'path':name,'archive_entry':inner,'kind':'credential_pattern_or_environment_value'})
    objects=subprocess.check_output(['git','rev-list','--objects','--all'],cwd=ROOT).decode('utf-8').splitlines()
    process=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    history=[];blobs=0
    try:
        for line in objects:
            identity=line.split(' ',1)[0]
            process.stdin.write((identity+'\n').encode());process.stdin.flush()
            fields=process.stdout.readline().decode().split()
            if len(fields)!=3:continue
            data=process.stdout.read(int(fields[2]));process.stdout.read(1)
            if fields[1]!='blob':continue
            blobs+=1
            if hit(data):history.append(identity)
    finally:
        process.stdin.close();process.wait()
    raw_url=subprocess.check_output(['git','config','--get','remote.origin.url'],cwd=ROOT,text=True).strip()
    parsed=urllib.parse.urlsplit(raw_url)
    embedded=bool(parsed.username or parsed.password)
    if embedded:issues.append({'kind':'remote_contains_embedded_credentials'})
    report={'status':'passed' if not issues and not history and not skipped_large else 'needs_review',
        'scope':'workspace and one-level ZIP/DOCX entries, plus all reachable Git blobs; credential patterns/current environment values',
        'head_before_scan':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'working_tree_items_scanned':items,'git_history_blobs_scanned':blobs,
        'credential_findings':issues,'history_credential_findings':history,
        'local_secret_stores':local_secret_stores,'files_over_size_limit':skipped_large,
        'remote_host':parsed.hostname,'remote_path':parsed.path,'remote_embedded_credentials':embedded,
        'scanner_literal_note':'Ignored old package_handoff.py contains only private-key marker comparison literals, not a PEM body; no key text reported.',
        'limits':'Pattern scanning is not a mathematical proof of absence; credential stores/Codex authentication are not read.'}
    if save:
        out=ROOT/'docs/evidence/deepseek/review-20261016/security_scan.json'
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','working_tree_items_scanned','git_history_blobs_scanned','credential_findings','history_credential_findings','local_secret_stores','files_over_size_limit')},ensure_ascii=False))
    if report['status']!='passed':raise SystemExit(1)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-save',action='store_true')
    scan(not parser.parse_args().no_save)
