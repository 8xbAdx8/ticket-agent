import subprocess,hashlib,json,shutil,sys
from pathlib import Path
root=Path.cwd().resolve();out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
def git(*args):return subprocess.check_output(['git','-c','core.quotepath=false',*args],cwd=root)
paths=set()
for args in (('diff','--name-only','-z'),('diff','--cached','--name-only','-z'),('ls-files','--others','--exclude-standard','-z')):
 paths.update(p.decode('utf-8') for p in git(*args).split(b'\0') if p)
paths.discard('scripts/v36_backup_snapshot.py')
manifest=[]
for rel in sorted(paths):
 src=root/rel
 if not src.is_file():manifest.append({'path':rel,'state':'missing_or_deleted'});continue
 dst=out/'files'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 digest=hashlib.sha256(dst.read_bytes()).hexdigest()
 if digest!=hashlib.sha256(src.read_bytes()).hexdigest():raise RuntimeError('backup_hash_mismatch')
 manifest.append({'path':rel,'sha256':digest,'size':src.stat().st_size})
(out/'manifest.json').write_text(json.dumps({'head':git('rev-parse','HEAD').decode().strip(),'branch':git('branch','--show-current').decode().strip(),'files':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
(out/'tracked.patch').write_bytes(git('diff','--binary'))
(out/'staged.patch').write_bytes(git('diff','--cached','--binary'))
print(json.dumps({'path':str(out),'files':len(manifest),'hashes_verified':True},ensure_ascii=False))
