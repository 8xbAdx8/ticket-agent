"""用户端的展示用语；只转换显示，不修改事件、参数或执行判断。"""
from web.presentation import escape, TOOL_LABELS


def workspace_label(value):
    """保留导航内部值，避免文案变化重置会话或路由。"""
    return {"出行助手": "用户工作空间", "开发者工作台": "开发者工作空间",
            "测试工作台": "测试控制台"}[value]


def operation_details(args):
    """确认前展示原始参数的中文名称，未知字段也保留供用户核对。"""
    labels = {"train_no": "车次", "date": "日期", "seat_type": "席别",
              "passengers": "乘客", "passenger_ids": "乘客标识", "contact": "联系人",
              "order_id": "订单号", "lock_id": "预留编号", "pay_type": "支付方式",
              "reason": "原因", "phone": "联系号码", "duration_minutes": "监控时长（分钟）",
              "from_city": "出发地", "to_city": "目的地", "kind": "交通方式",
              "question": "问题", "old_train": "原车次", "old_date": "原日期",
              "old_seat": "原席别", "new_train": "目标车次", "new_date": "目标日期",
              "new_seat": "目标席别", "original_amount": "原金额", "new_amount": "新金额",
              "difference": "差额（仅作演示记录）", "policy": "示例政策编号", "note": "说明"}
    # st.write(list)会显示JSON；确认卡把乘客等列表转成可读文字，原始参数不变。
    return [(labels.get(key, "其他信息（" + key + "）"),
             '、'.join(str(item) for item in value) if isinstance(value, (list, tuple)) else value)
            for key, value in args.items()]


def phase_markup(states):
    """复用已判定的阶段状态，只去掉耗时、结束码等诊断字段。"""
    names = {"query": "查询车票", "policy": "查阅政策", "confirm": "确认操作",
             "execute": "处理演示订单", "done": "本轮处理"}
    status = {"done": "处理结束", "failed": "未成功", "blocked": "已阻止",
              "active": "处理中", "waiting": "请确认", "declined": "已取消",
              "pending": "尚未进行", "unknown": "暂无记录"}
    parts = []
    for n, item in enumerate(states, 1):
        parts.append('<div class="ta-phase is-' + escape(item['status']) + '">'
                     '<span class="ta-phase-dot"></span><span class="ta-phase-body"><b>'
                     + str(n).zfill(2) + ' ' + names[item['key']] + '</b><small>'
                     + status.get(item['status'], '状态未知') + '</small></span></div>')
    return '<div class="ta-phases" role="list">' + ''.join(parts) + '</div>'


def processing_markup(event):
    """仅描述实际收到的事件，不把模型提议说成已经执行成功。"""
    kind = event.get('event_type', '')
    if event.get('status') in ('failed', 'blocked'):
        text = '本次处理遇到问题，正在整理结果…'
    elif kind == 'confirmation_requested':
        text = '请确认后再继续操作…'
    elif kind.startswith('followup_'):
        text = '正在整理后续问题…'
    elif kind.startswith('rag_'):
        text = '正在查阅示例政策…'
    elif kind in ('tool_start', 'tool_result'):
        text = '正在处理：' + TOOL_LABELS.get(event.get('tool'), '本次请求') + '…'
    else:
        text = '正在处理请求…'
    return '<div class="ta-processing" role="status" aria-live="polite"><span></span>' + escape(text) + '</div>'


def error_message(category):
    """原始错误仍留在审计中；用户端给出可执行的下一步。"""
    if category in ('timeout', 'request_timeout'):
        return '本次请求超时，结果可能尚未确认。请先核对订单状态，再决定是否重试。'
    if category in ('rate_limited', 'server_error', 'service_unavailable'):
        return '在线服务暂时不可用，本次没有自动重试。请稍后再试。'
    if category in ('permission_denied', 'authentication_failed', 'missing_DEEPSEEK_API_KEY',
                    'missing_DASHSCOPE_API_KEY', 'qwencloud_key_requires_qwencloud_endpoint',
                    'invalid_api_address'):
        return '在线服务配置或访问权限有问题，请联系管理员在开发者工作空间检查。'
    if category == 'insufficient_balance':
        return '在线服务的可用余额或额度不足，请联系管理员核对。'
    if category == 'network_connection':
        return '无法连接在线服务，本次没有自动重试。请检查网络后再试。'
    if category in ('rag_answer_inconsistent', 'query_result_train_authority', 'reply_data_inconsistent',
                    'reply_data_indeterminate', 'reply_tool_mismatch'):
        return '回答与本次查询记录未能核对一致，请先核实车次、政策或订单信息。'
    return '本次请求未完成，请核对输入和订单状态。详细原因可在开发者工作空间查看。'
