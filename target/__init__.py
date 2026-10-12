# -*- coding: utf-8 -*-
"""被测层包。

成员 A 负责本目录下全部代码：
  mock_core.py  模拟票务后端核心（纯 Python 函数）
  mock_api.py   FastAPI 外壳（可选，视频演示用）
  tools.py      工具 schema 与分发
  rag.py        政策知识库检索
  providers.py  模型提供者（mock / 真实模型）
  agent.py      主循环与对外 chat() 接口
  trace.py      执行记录（接口契约核心）
"""
