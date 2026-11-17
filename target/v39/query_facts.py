"""Read-only, provenance-preserving collection of one logical railway query."""
import json
from datetime import datetime


def query_key(args):
    return json.dumps({k:v for k,v in args.items() if k not in ('cursor','limit') and v is not None},sort_keys=True,ensure_ascii=False)


def collect(events):
    attempts={};latest=None
    for index,e in enumerate(events or []):
        if not isinstance(e,dict) or e.get('event')!='tool_end' or e.get('tool')!='railway_query_trips' or e.get('ok') is not True or e.get('executed') is False:continue
        result=e.get('result');args=e.get('args') or {}
        if not isinstance(result,dict) or not isinstance(result.get('data'),list):continue
        key=query_key(args)
        try:offset=int(args.get('cursor') or 0)
        except (ValueError,TypeError):offset=-1
        current=attempts.get(key)
        if current is None or (offset==0 and current['terminal']):
            current=dict(key=key,pages=[],terminal=False);attempts[key]=current
        source=dict(event_index=index,call_id=e.get('call_id'),page_cursor=args.get('cursor'),args=args,dataset_version=result.get('dataset_version'),database_sha256=result.get('database_sha256'),source_sha256=result.get('source_sha256'))
        current['pages'].append(dict(offset=offset,result=result,source=source))
        current['terminal']=result.get('has_more') is False and result.get('next_cursor') is None
        latest=current
    if latest is None:return None
    pages=latest['pages'];issues=[];rows=[];seen={};expected=0;totals=set();identities=set();cursors=set()
    for page in pages:
        result=page['result'];offset=page['offset'];items=result['data']
        identities.add((result.get('dataset_version'),result.get('database_sha256'),result.get('source_sha256')))
        total=result.get('total_count');returned=result.get('returned_count')
        if type(total) is not int or type(returned) is not int:issues.append('missing_count_metadata')
        else:totals.add(total)
        if offset in cursors:issues.append('duplicate_page')
        cursors.add(offset)
        if offset!=expected:issues.append('cursor_chain_gap')
        if returned is not None and returned!=len(items):issues.append('returned_count_mismatch')
        more=result.get('has_more');next_cursor=result.get('next_cursor')
        if more is True:
            if not items:issues.append('empty_continuation')
            try:expected_next=int(next_cursor)
            except (ValueError,TypeError):expected_next=-1
            if expected_next!=offset+len(items):issues.append('invalid_next_cursor')
            expected=expected_next
        else:
            expected=offset+len(items)
            if more is not False or next_cursor is not None:issues.append('missing_terminal_metadata')
        for item in items:
            trip_id=item.get('trip_id')
            if not trip_id:issues.append('missing_trip_identity')
            if trip_id in seen:
                issues.append('duplicate_trip' if seen[trip_id]==item else 'conflicting_trip')
            else:seen[trip_id]=item;rows.append(dict(record=item,source=page['source']))
    if pages[0]['offset']!=0:issues.append('first_page_missing')
    if not latest['terminal']:issues.append('last_page_missing')
    if len(identities)!=1 or any(v is None for identity in identities for v in identity):issues.append('dataset_identity_mismatch_or_missing')
    if len(totals)!=1 or len(rows)!=next(iter(totals),None):issues.append('total_count_mismatch')
    return dict(complete=not issues,issues=sorted(set(issues)),records=rows,pages=[p['source'] for p in pages],query_key=latest['key'],total_count=next(iter(totals)) if len(totals)==1 else None)


def durations(facts):
    if not facts or not facts['complete']:return dict(status='indeterminate',ranked=[],invalid_records=[])
    ranked=[];invalid=[]
    for row in facts['records']:
        t=row['record']
        try:
            a=datetime.fromisoformat(t['departure_at']);b=datetime.fromisoformat(t['arrival_at'])
            if a.tzinfo is None or b.tzinfo is None or b<a:raise ValueError('invalid_datetime')
            seconds=int((b-a).total_seconds())
        except (KeyError,ValueError,TypeError):invalid.append(t.get('trip_id'));continue
        ranked.append(dict(trip_id=t.get('trip_id'),train_no=t.get('trip_short_name'),departure_at=t['departure_at'],arrival_at=t['arrival_at'],duration_seconds=seconds,source=row['source']))
    ranked.sort(key=lambda r:(r['duration_seconds'],str(r['trip_id'])))
    return dict(status='complete' if not invalid else 'valid_records_only',ranked=ranked,invalid_records=invalid)


def summary(facts):
    ranking=durations(facts)
    if not facts:return None
    best=ranking['ranked'][:5]
    return dict(query_key=facts['query_key'],complete=facts['complete'],issues=facts['issues'],total_count=facts['total_count'],pages=facts['pages'],duration_status=ranking['status'],fastest_valid_records=best,invalid_datetime_records=ranking['invalid_records'])
