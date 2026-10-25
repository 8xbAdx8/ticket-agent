# -*- coding: utf-8 -*-
"""全局配置：换模型只需要改这里的三个变量。"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
from target.api_config import bootstrap
bootstrap(BASE_DIR)
PROVIDER = os.getenv("AGENT_PROVIDER", "mock")      # mock | openai | deepseek | bailian
DB_PATH = Path(os.getenv("AGENT_DB_PATH", str(BASE_DIR / "data" / "tickets.db")))
POLICY_PATH = BASE_DIR / "data" / "policies.md"
TRACE_DIR = Path(os.getenv("AGENT_TRACE_DIR", str(BASE_DIR / "traces" / (PROVIDER+"_live") if PROVIDER in ("deepseek","bailian") else BASE_DIR / "traces")))
TRACE_DIR.mkdir(parents=True, exist_ok=True)

# ---- 模型提供者：mock（零依赖离线） 或 openai（OpenAI 兼容端点）----
MODEL_NAME = os.getenv("AGENT_MODEL", "deepseek-flash" if PROVIDER == "deepseek" else "glm-4-flash")
BASE_URL = os.getenv("AGENT_BASE_URL", "https://api.deepseek.com" if PROVIDER == "deepseek" else "https://open.bigmodel.cn/api/paas/v4")
# DeepSeek 只有一个密钥来源；AGENT_API_KEY 继续专用于旧 openai Provider。
API_KEY = os.getenv("DEEPSEEK_API_KEY" if PROVIDER == "deepseek" else "AGENT_API_KEY", "")
if PROVIDER=="deepseek":
    from target.api_config import model_config
    _api=model_config(PROVIDER,active=True)
    MODEL_NAME,BASE_URL=_api["model"],_api["base_url"]
if PROVIDER == "bailian":
    # No implicit region/account entitlement. Only the Bailian variables select its endpoint/model/key.
    MODEL_NAME = os.getenv("DASHSCOPE_MODEL", "qwen3.8-flash")
    BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "")
    API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# V3 增量引擎；legacy 保留 V2 零框架依赖路径。
ENGINE = os.getenv("AGENT_ENGINE", "langchain" if PROVIDER in ("deepseek","bailian") else "legacy")  # legacy | langchain
LC_TOOLSET = os.getenv("AGENT_LC_TOOLSET", "read_only")  # read_only | all

# ---- Agent 主循环参数 ----
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "8"))  # 超过即判定为疑似死循环
if MAX_STEPS < 1:
    raise ValueError("AGENT_MAX_STEPS 必须大于 0")
LOCK_TTL_SECONDS = 15 * 60                          # 锁座有效期

# ---- 模拟票务后端：两种形态开关 ----
# False: 直接调用 mock_core 的纯 Python 函数（默认，零部署）
# True : 通过 HTTP 调用 FastAPI 服务（需先 uvicorn 启动，视频演示更好看）
USE_HTTP_MOCK = os.getenv("AGENT_USE_HTTP", "0") == "1"
MOCK_API_URL = os.getenv("AGENT_MOCK_URL", "http://127.0.0.1:8000")

# ---- RAG ----
# False: 中文字/英文词重叠打分（零依赖，离线可用；不是 BM25）
# True : 本地向量检索（需 pip install sentence-transformers faiss-cpu）
USE_VECTOR_RAG = os.getenv("AGENT_VECTOR_RAG", "0") == "1"
EMBED_MODEL = "BAAI/bge-small-zh"
TOP_K = 3

# ---- 演示用默认用户（红队越权测试会用到另一个用户）----
CURRENT_USER_PHONE = "13800000001"
OTHER_USER_PHONE = "13900000002"

def now():
    """业务时钟：北京时间的无时区 datetime，与 SQLite 既有时间格式兼容。"""
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

def today():
    return now().date()
