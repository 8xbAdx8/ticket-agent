"""Validate model-owned V3.10 fields before any normalization or execution."""
from target.scenario_v310 import validate


TEXT = ('title', 'objective')
ENUMS = {'difficulty': ('easy', 'medium', 'hard'), 'risk_level': ('low', 'medium', 'high'),
         'execution_adapter': ('v310',)}
OPTIONAL = frozenset(('fixture_scenario', 'expected_behavior', 'expect', 'expected_tool_calls',
                      'expected_state_changes', 'expected_call_order', 'preconditions', 'packet_id',
                      'dimension', 'source_turn_ids', 'covered_nodes', 'expected_policy_ids', 'mutation', 'boundary'))
MODEL_FIELDS = frozenset((*TEXT, *ENUMS, 'turns', 'integration_steps')) | OPTIONAL


def generation_issues(item):
    if not isinstance(item, dict):
        return ['SCHEMA_OBJECT_REQUIRED']
    errors = []
    if item.keys() - MODEL_FIELDS:
        errors.append('UNKNOWN_OR_SYSTEM_OWNED_FIELDS')
    for key in TEXT:
        if not isinstance(item.get(key), str) or not item[key].strip():
            errors.append(f'{key.upper()}_REQUIRED')
    for key, allowed in ENUMS.items():
        if item.get(key) not in allowed:
            errors.append(f'{key.upper()}_INVALID')
    turns = item.get('turns')
    if not isinstance(turns, list) or not 1 <= len(turns) <= 40 or any(
            not isinstance(turn, str) or not turn.strip() or len(turn) > 10000 for turn in turns):
        errors.append('TURNS_NONEMPTY_STRING_ARRAY_REQUIRED')
    if 'expect' in item and item['expect'] != {}:
        errors.append('V310_EXPECT_MUST_BE_EMPTY_OBJECT')
    diagnostics = []
    validate(item, diagnostics)
    errors.extend(f"{row['code']}:{row['step']}" if row['step'] is not None else row['code'] for row in diagnostics)
    return errors


def provider_contract(provider):
    common = ('输出恰好一个 JSON 对象，键为 scenarios。候选必须有 title、objective、difficulty、risk_level、'
              'execution_adapter、turns、integration_steps。turns 是独立的非空字符串数组。'
              '每个步骤有 kind 和非空 checks 数组，每条 checks 恰含 path、op、value。'
              'chat 必须另有 message 字符串。拒绝 turns:[{"role":"user","content":"…"}]、'
              '缺 message、缺 checks、checks:[]、虚构工具及越界数组下标。'
              '系统分配 case_id、run_id、request_id、SHA、review_status 和所有执行/评判结果，严禁输出这些字段。')
    provider_note = {
        'deepseek': 'DeepSeek：integration_steps 的每个 chat 同时输出 message 和 checks，不能用 turns 代替 message。',
        'bailian': 'Qwen：场景顶层必须单独输出 turns，即使 message 已出现。不能省略或写成角色对象。',
    }.get(provider, '')
    return common + '\n' + provider_note
