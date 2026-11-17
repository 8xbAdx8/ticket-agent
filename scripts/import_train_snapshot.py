"""Explicit append-only local import. No collection, login or API calls."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from target.train_snapshot import import_snapshot

def main():
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);p.add_argument('--destination',type=Path,default=Path(__file__).resolve().parents[1]/'data/real');p.add_argument('--evidence',type=Path);p.add_argument('--acknowledge-source-rights',action='store_true');a=p.parse_args()
    try:
        path,receipt=import_snapshot(a.file,a.destination,evidence=a.evidence,acknowledge_rights=a.acknowledge_source_rights)
        print(json.dumps({'status':'IMPORTED_LOCAL_FILE','path':str(path),'receipt':receipt},ensure_ascii=False));return 0
    except (ValueError,OSError):print(json.dumps({'status':'IMPORT_REJECTED'},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
