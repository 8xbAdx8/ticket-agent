"""Check one existing LangSmith run. Default preflight is offline; never POSTs."""
import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main(argv=None,*,transport=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--payload',type=Path,required=True,help='Frozen filtered payload, not a raw model/audit record')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--run',action='store_true',help='Explicitly authorize GET only; no upload or model request')
    parser.add_argument('--max-get-requests',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args(argv)
    started=False;result=None
    try:
        from target.api_config import bootstrap
        bootstrap()
        from target.observability import verify_existing,settings
        from target.diagnostics import digest
        identity=str(uuid.UUID(args.run_id))
        for path in (args.receipt,args.payload):
            if not path.resolve().is_relative_to(ROOT):raise ValueError('project_evidence_required')
        raw=args.receipt.read_text(encoding='utf-8-sig')
        try:items=[json.loads(raw)]
        except ValueError:items=[json.loads(line) for line in raw.splitlines() if line.strip()]
        receipt=next(r for r in reversed(items) if r.get('remote_run_id')==identity)
        payload=json.loads(args.payload.read_text(encoding='utf-8-sig'))
        key,endpoint,project,_=settings()
        compatible=(endpoint==receipt.get('endpoint') and project==receipt.get('project')
                    and digest(payload)==receipt.get('payload_sha256'))
        if not key or not compatible:
            print(json.dumps({'status':'not_configured' if not key else 'evidence_or_configuration_mismatch',
                              'http_requests':0,'post_requests':0,'generation_requests':0}));return 2
        if not args.run:
            print(json.dumps({'status':'ready_not_run','run_id':identity,'max_get_requests':args.max_get_requests,
                              'http_requests':0,'post_requests':0,'generation_requests':0}));return 0
        if not args.out:raise ValueError('new_isolated_output_directory_required')
        out=args.out.resolve();base=(ROOT/'artifacts/runtime').resolve()
        if not out.is_relative_to(base) or out==base:raise ValueError('isolated_output_required')
        out.mkdir(parents=True,exist_ok=False)
        started=True
        result=verify_existing(receipt,payload,consent=True,transport=transport,max_read_attempts=args.max_get_requests,trace_dir=out)
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result['remote_verified'] else 3 if result['remote_status']=='pending_verification' else 1
    except Exception:
        # File, configuration and parser errors can contain personal paths or secrets.
        if result is not None:
            result['result_file_saved']=False
            print(json.dumps(result,ensure_ascii=False));return 1
        print(json.dumps({'status':'request_outcome_unknown' if started else 'local_preflight_failed',
            'http_requests':None if started else 0,'post_requests':0,'generation_requests':0}))
        return 2


if __name__=='__main__':raise SystemExit(main())
