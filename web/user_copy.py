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


def phase_markup(states, *, animate=False):
    """复用已判定的阶段状态，只去掉耗时、结束码等诊断字段。"""
    names = {"query": "查询车票", "policy": "查阅政策", "confirm": "确认操作",
             "execute": "处理演示订单", "done": "本轮处理"}
    status = {"done": "处理结束", "failed": "未成功", "blocked": "已阻止",
              "active": "处理中", "waiting": "请确认", "declined": "已取消",
              "pending": "尚未进行", "unknown": "暂无记录"}
    parts = []
    icons={'done':'✓','failed':'!','blocked':'⊘','active':'●','waiting':'◉','declined':'–'}
    for n, item in enumerate(states, 1):
        parts.append('<div role="listitem" class="ta-phase is-' + escape(item['status']) + (' ta-motion-active' if animate and item['status']=='active' else '') + '">'
                     '<span class="ta-phase-dot ta-state-icon" aria-hidden="true">'+icons.get(item['status'],'○')+'</span><span class="ta-phase-body"><b>'
                     + str(n).zfill(2) + ' ' + names[item['key']] + '</b><small>'
                     + status.get(item['status'], '状态未知') + '</small></span></div>')
    return '<div class="ta-phases" role="list">' + ''.join(parts) + '</div>'


def processing_markup(event):
    """仅描述实际收到的事件，不把模型提议说成已经执行成功。"""
    from web.request_motion import state,markup
    view=state({'status':'RUNNING'},[event],active=True)
    if event.get('status') in ('failed','blocked'):
        view=dict(state='BLOCKED' if event['status']=='blocked' else 'FAILED',text='本次处理遇到问题，正在整理结果',moving=False)
    return markup(view)


def error_message(category):
    if category=='model_output_truncated':
        return '模型文字达到输出上限，回答未完整返回；已执行查询和已提交的模拟交易仍保留。请查看下方数据库状态，未自动重试。'
    if str(category or '').startswith('acceptance_'):
        return '本次验收批次已被安全预算拦截；本次未继续请求模型。已完成的交易和记录保留，不会自动重试，请核对批次预算。'
    """原始错误仍留在审计中；用户端给出可执行的下一步。"""
    if category=='observed_token_budget_exhausted':
        return '本轮上下文已达到安全预算，已停止继续调用模型；已执行工具结果完整保留。请新建会话或缩小查询范围后重试，不要重复已完成的查询。'
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
