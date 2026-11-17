"""python -m prototypes.railway_static.cli: independent offline entry point."""
import argparse,json
from .models import envelope
from .importer import import_dataset
from .query import Dataset

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    p=sub.add_parser('import');p.add_argument('--db',required=True)
    for name,args in [('info',[]),('stations',['name']),('station',['stop_id']),('trains',['date']),('trip',['trip_id','date']),('direct',['from_id','to_id','date'])]:
        p=sub.add_parser(name);p.add_argument('--db',required=True)
        for arg in args:p.add_argument(arg)
    a=parser.parse_args(argv)
    try:
        if a.operation=='import':result=envelope('IMPORTED',import_dataset(a.db))
        else:
            with Dataset(a.db) as d:
                fn=getattr(d,a.operation)
                keys={'info':[],'stations':['name'],'station':['stop_id'],'trains':['date'],'trip':['trip_id','date'],'direct':['from_id','to_id','date']}[a.operation]
                result=fn(*(getattr(a,k) for k in keys))
    except (ValueError,OSError) as exc:result=envelope('INVALID_QUERY',[],error=str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['status']=='INVALID_QUERY' else 0

if __name__=='__main__':raise SystemExit(main())
