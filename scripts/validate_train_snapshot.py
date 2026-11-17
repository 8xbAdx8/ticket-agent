"""Validate a user-supplied local file; never query any network endpoint."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from target.train_snapshot import validate,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);p.add_argument('--sha256');args=p.parse_args()
    try:
        if args.file.stat().st_size>8_000_000:raise ValueError('快照超限')
        raw=args.file.read_bytes();data=validate(raw);h=sha(raw)
        if args.sha256 and args.sha256!=h:raise ValueError('SHA256不匹配')
        print(json.dumps({'status':'VALID_STRUCTURE','sha256':h,'classification':data['classification'],'source_verified_independently':False,'trains':len(data['trains'])},ensure_ascii=False));return 0
    except (ValueError,OSError):print(json.dumps({'status':'INVALID_SNAPSHOT'},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
