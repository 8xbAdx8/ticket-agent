"""Provider-specific QA-09 pilot using the existing ABC authorization and runner."""
import json

from target.scenario_abc_budget import R2_ROOT
from target.scenario_abc_live import PILOT_ARGS, PilotModel
from target.scenario_generation_contract import provider_contract
from target.v39.registry import TOOLS


def example(provider):
    message = '查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。'
    keys = ('origin_stop_id', 'destination_stop_id') if provider == 'deepseek' else ('destination_stop_id', 'service_date')
    checks = [dict(path='result.queries.0.tool', op='eq', value='railway_query_trips')]
    checks.extend(dict(path='result.queries.0.args.'+key, op='eq', value=PILOT_ARGS[key]) for key in keys)
    checks.append(dict(path='metrics.order_count', op='eq', value=0))
    return dict(title='核对铁路区间的查询参数', objective='验证 Agent 只读查询及传参', difficulty='easy',
                risk_level='low', turns=[message], expected_behavior='answer', execution_adapter='v310',
                fixture_scenario='default', dimension='工具调用', source_turn_ids=['turn-001'],
                covered_nodes=['工具选择', '参数构造'], expected_tool_calls=[], expected_state_changes=[], expect={},
                integration_steps=[dict(kind='chat', message=message, checks=checks)])


class R2Model(PilotModel):
    source = 'r2_live_model'

    def __init__(self, provider, *, batch=None, revision=1):
        super().__init__(provider, batch=batch, evidence_root=R2_ROOT)
        if revision not in (1, 2) or revision == 2 and provider != 'deepseek':
            raise ValueError('R2_INVALID_PILOT_REVISION')
        self.revision = revision

    def pilot_marker(self):
        suffix = '-revision-2' if self.revision == 2 else ''
        return self.evidence_root/f'pilot-{self.provider}{suffix}.json'

    def provider_for(self, stage):
        if stage == 'judge':
            return 'bailian' if self.provider == 'deepseek' else 'deepseek'
        return self.provider

    def prepare_prompt(self, system, user, step):
        if step != 'generate':
            packet = json.loads(user)
            for row in packet['evidence']:
                row.pop('calls', None)
            for event in packet['tool_events']:
                result = event.get('result')
                if isinstance(result, dict) and len(json.dumps(result, ensure_ascii=False).encode('utf8')) > 3000:
                    data = result.get('data')
                    event['result'] = {key: result[key] for key in ('status', 'count', 'found', 'total', 'error', 'quote') if key in result}
                    if isinstance(data, list):
                        event['result'].update(data_count=len(data), first_record=data[0] if data else None)
                    event['result']['raw_detail_in_tool_trace'] = True
            note = ('\n逐项核对本用例 Oracle 和事件，缺证给 indeterminate。对被省略的工具明细不作推断。'
                    '如果订单存在但四层有缺失，整条业务结论为 indeterminate，保留可验证的只读和 SQLite 事实。'
                    '另返回 inconsistent_fields 字符串数组，指出矛盾或缺失字段。')
            return system + note, json.dumps(packet, ensure_ascii=False, separators=(',', ':'))
        contract = next(t['function']['parameters'] for t in TOOLS if t['function']['name'] == 'railway_query_trips')
        source = json.loads(user)['conversation']['turns'][0]
        # This focused acceptance prompt supersedes the general-purpose workbench
        # prompt, which also describes direct tool and confirmation DSL steps.
        attribution = {'dimension': '工具调用', 'source_turn_ids': [source['turn_id']], 'covered_nodes': ['工具选择', '参数构造']}
        system = ('你为 Ticket Agent QA-09 生成一条可执行的只读 V3.10 测试场景。\n'
                  + provider_contract(self.provider) + '\n'
                  '工作台还强制要求这三个候选顶层字段，逐字填写键和值，任何一个缺失都会拒绝：'
                  + json.dumps(attribution, ensure_ascii=False) + '\n'
                  '本轮只使用一个 chat 步骤，让被测 Agent 自主调用 railway_query_trips。'
                  '固定日期、出发站和到达站来自输入目标。保留样例的每一个必填字段和断言类型。'
                  '提交前自查 dimension、source_turn_ids、covered_nodes、turns、chat.message、chat.checks 均已输出。可以修改标题和目标描述。'
                  '不要输出工具调用实测、订单状态或 PASS。严格输出一个 JSON 对象。\n'
                  '完整合法示例：' + json.dumps({'scenarios': [example(self.provider)]}, ensure_ascii=False))
        return system, json.dumps(dict(test_goal=example(self.provider)['turns'][0], required_attribution=attribution,
                                       source_turn={'id': source['turn_id'], 'question': source['user']},
                                       tool_schema=contract), ensure_ascii=False)
