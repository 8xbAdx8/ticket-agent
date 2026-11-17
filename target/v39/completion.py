"""Internal output completeness and deterministic read-result fallback."""
import re
from target.v39.query_facts import collect,durations


class OutputTruncated(Exception):
    pass


def query_answer(events):
    facts=collect(events);ranking=durations(facts)
    if not facts or not facts['complete'] or not ranking['ranked']:return None
    rows=ranking['ranked'];minimum=rows[0]['duration_seconds']
    fastest=[r for r in rows if r['duration_seconds']==minimum]
    lines=[f"已核对完整分页，共{facts['total_count']}班。按实际到发日期时间计算，最短运行时间为{minimum//60}分钟。"]
    if ranking['invalid_records']:lines.append('部分记录时间无效，以上仅比较时间有效的记录，不代表全量最短。')
    for r in fastest[:5]:lines.append(f"{r['train_no']}：出发 {r['departure_at'][11:16]}，到达 {r['arrival_at'][11:16]}。")
    if len(fastest)>5:lines.append(f'另有{len(fastest)-5}班并列最短，完整原始结果保留在查询记录中。')
    return '\n'.join(lines)+'\n静态时刻不代表实时运行状态，库存与交易为本地模拟。'


def resolve(reply,message,events):
    if not re.search(r'最短|最快|比较.*(?:时长|运行时间)',message):return reply,None
    result=query_answer(events)
    return (result,dict(event='deterministic_duration_answer',original_model_reply=reply,public_reply=result)) if result and result!=reply else (reply,None)


def local_answer(message,events):
    return query_answer(events) if re.search(r'最短|最快|比较.*(?:时长|运行时间)',message) else None


def incomplete_reply(events,category='model_output_truncated'):
    reason='模型输出已截断，未将残缺回答作为完整结果。' if category=='model_output_truncated' else '本轮模型上下文预算不足，已停止继续请求，未自动重试。'
    answer=query_answer(events)
    return reason+('\n以下为本地确定性查询摘要：\n'+answer if answer else '\n请核对已返回的工具结果；没有相应成功凭据的业务操作不能视为完成。')
