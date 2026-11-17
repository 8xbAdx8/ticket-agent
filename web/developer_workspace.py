# -*- coding: utf-8 -*-
"""开发者工作空间 · 纯原理介绍页。

不连接会话、不读取运行记录、不展示 Agent 运行结果；
运行证据与质量结论统一由测试控制台呈现。
"""
from __future__ import annotations

from web.design import header


def developer_page(sessions):
    """sessions 仅为冻结的 ``web/app.py`` 调用签名保留。"""
    del sessions
    header('Agent 开发者端 · 我们如何设计这个 Agent',
           '按 7 个模块介绍开发原理：思考分析、提示词、工具配置、知识库、'
           '记忆多轮、工作流与边界。提示词与代码均直接取自当前源码。',
           '设计原理 / 源码')
    from web.developer_principles import render
    render()
