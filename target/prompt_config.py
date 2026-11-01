"""Exact existing prompt assembly, shared with effective config previews."""
import config

def compose(system_prompt,engine,*,read_only=False,suffix='',day=None,validation=False,phone=None):
    day=day or config.today().isoformat()
    phone=config.CURRENT_USER_PHONE if phone is None else phone
    if engine=='legacy':
        prompt=system_prompt+f"\n当前北京时间日期 {day}；数据仅为虚构模拟，当前身份为本人。"
    else:
        if read_only:
            from target.deepseek_runtime import READ_ONLY_PROMPT
            system_prompt=READ_ONLY_PROMPT
            if validation:system_prompt+='\n本轮是政策验收。政策问题应交给search_policy，question保留用户原句；证据不足明确无法确认，不添加无来源期限、金额或限制。'
        prompt=(system_prompt+f"\n当前北京时间日期 {day}；业务全部虚构。"
                                  + ("" if read_only else
                                  "\n写操作必须获得本轮明确授权；订票不包含支付。锁座一轮至多一次成功，下单必须用本轮成功 lock_id。"
                                  "支付/退票使用用户指定或最近工具结果订单；不明确时先澄清。"
                                  "\n这是隔离的虚构票务沙箱，不连接真实售票或支付。当前模拟账户的联系号码为 "
                                  + phone + "；仅使用用户明确提供的模拟乘客姓名。"
                                  "用户在多轮对话中分别明确选择车次、席别和乘客时，可依据用户的订票意图和已有查询结果尝试锁座；不得猜测缺失信息，创建订单要等用户明确确认下单。"
                                  "候补工具仅返回模拟任务，不会后台持续监控或推送通知，不得声称会自动通知。"))
    if suffix:
        prompt+='\n开发者补充（不变更工具权限、身份和用户确认边界）：\n'+suffix
    return prompt
