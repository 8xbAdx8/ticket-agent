"""Correct explicit total-count claims only; preserve original text in audit."""
import re

def reconcile(reply,events):
    last=next((e for e in reversed(events) if e.get('event')=='tool_end' and e.get('tool')=='railway_query_trips' and e.get('ok') is True),None)
    data=last.get('result',{}) if last else {}
    total=data.get('total_count')
    if type(total) is not int:return reply,[]
    changes=[]
    pattern=r'((?:一共|总共|共计|总计|合计|查询到|查到|共)\s*[：:]?\s*\*{0,2})(\d+)(\s*\*{0,2}\s*(?:班|趟))'
    def fix(m):
        if int(m[2])==total:return m[0]
        changes.append(dict(claimed=int(m[2]),actual_total=total,call_id=last.get('call_id')))
        return m[1]+str(total)+m[3]
    return re.sub(pattern,fix,reply),changes
