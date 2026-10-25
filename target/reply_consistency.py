"""Conservative checks for explicit train-time claims. Never rewrites model text."""
import re

TIME=r"(\d{1,2}:\d{2})"


def normalized(value):
    h,m=value.split(':');return f'{int(h):02}:{m}'


def check(reply,events):
    trains={t['train_no']:t for e in events if e.get('event')=='tool_end' and e.get('tool')=='query_tickets' and e.get('ok')
            for t in (e.get('result') or {}).get('trains',[]) if isinstance(t,dict) and t.get('train_no')}
    findings=[]; checked=0; header=None
    for line in (reply or '').splitlines():
        if '|' in line:
            cells=[c.strip().strip('*') for c in line.strip().strip('|').split('|')]
            if any('车次' in c for c in cells) and any('出发' in c or '发车' in c for c in cells):header=cells;continue
        ids=[n for n in trains if re.search(r'(?<![A-Za-z0-9])'+re.escape(n)+r'(?!\d)',line)]
        if len(ids)!=1:continue
        train=trains[ids[0]];claims=[]
        if header and '|' in line and len(cells)==len(header):
            for title,value in zip(header,cells):
                field='depart' if '出发' in title or '发车' in title else 'arrive' if '到达' in title or '抵达' in title else None
                match=re.fullmatch(TIME,value)
                if field and match:claims.append((field,match[1]))
        for field,label in (('depart',r'出发|发车|开车'),('arrive',r'到达|抵达')):
            for match in re.finditer(TIME+r'\s*(?:'+label+r')',line):claims.append((field,match[1]))
            for match in re.finditer(r'(?:'+label+r')[：:]?\s*'+TIME,line):claims.append((field,match[1]))
        for field,value in claims:
            if train.get(field):
                checked+=1
                if normalized(value)!=normalized(train[field]):
                    findings.append({'train_no':ids[0],'field':field,'claimed':normalized(value),'tool_value':train[field]})
    return {'status':'failed' if findings else 'checked_fields_match' if checked else 'not_verified',
            'checked_fields':checked,'findings':findings,'scope':'Explicit per-train departure/arrival only; not full semantic evaluation'}
