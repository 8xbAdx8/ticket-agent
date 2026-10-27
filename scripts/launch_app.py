"""双击启动器的公共实现：不调用模型，不重置数据，不改正式预算。"""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import closing

ROOT=Path(__file__).resolve().parent.parent
# Executing scripts/launch_app.py directly puts scripts/, not the project root,
# on sys.path. The double-click launcher uses this direct entry point.
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def build_environment(mode, runtime_root, inherited=None):
    env=dict(os.environ if inherited is None else inherited)
    if 'TICKET_LANGSMITH_EXPORT_ENABLED' not in env and any(env.get(k,'').lower()=='true' for k in ('LANGCHAIN_TRACING_V2','LANGSMITH_TRACING')):
        env['TICKET_LANGSMITH_EXPORT_ENABLED']='true'
    for name in list(env):
        if name.startswith("DEEPSEEK_") and name!="DEEPSEEK_API_KEY":env.pop(name)
    env.pop("AGENT_API_KEY",None)
    today=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    workspace=Path(runtime_root)/mode/today
    env.update(PYTHONIOENCODING="utf-8",PYTHONUTF8="1",AGENT_USE_HTTP="0",AGENT_VECTOR_RAG="0",
        AGENT_MUTATIONS="{}",AGENT_MAX_STEPS="8",LANGSMITH_TRACING="false",LANGCHAIN_TRACING_V2="false",
        AGENT_DB_PATH=str(workspace/"tickets.db"),AGENT_TRACE_DIR=str(workspace/"traces"),
        STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
    if mode=="offline":
        env.pop("DEEPSEEK_API_KEY",None)
        env.pop('DASHSCOPE_API_KEY',None)
        env.update(TICKET_WEB_OFFLINE_ONLY='1',TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_LANGSMITH_EXPORT_ENABLED='false')
        env.update(AGENT_RAG_MODE="",RAG_ALLOW_NETWORK="0")
        env.update(AGENT_PROVIDER="mock",AGENT_ENGINE="legacy",AGENT_LC_TOOLSET="all",AGENT_MODEL="mock-offline",
                   AGENT_BASE_URL="https://api.deepseek.com")
    elif mode=="live":
        env.update(TICKET_WEB_OFFLINE_ONLY='0',TICKET_DISABLE_LOCAL_SECRETS='0')
        if "DEEPSEEK_API_KEY" in env:env["DEEPSEEK_API_KEY"]=env["DEEPSEEK_API_KEY"].strip()
        env.update(AGENT_PROVIDER="deepseek",AGENT_ENGINE="langchain",AGENT_LC_TOOLSET="read_only",
            AGENT_MODEL="deepseek-flash",AGENT_BASE_URL="https://api.deepseek.com",
            DEEPSEEK_LIVE_TEST_PROFILE="read_only",DEEPSEEK_THINKING="disabled",
            DEEPSEEK_MAX_REQUESTS='0',BAILIAN_MAX_REQUESTS='0',TICKET_INITIAL_LIVE_BUDGET='',TICKET_TOTAL_REQUEST_LIMIT='',
            DEEPSEEK_BUDGET_PATH=str(Path(runtime_root)/"live"/"requests.db"))
    else:raise ValueError("unknown launch mode")
    return env


def missing_dependencies(mode):
    names=["streamlit","pandas"]
    if mode=="live":names += ["langchain","langchain_deepseek","httpx"]
    return [name for name in names if importlib.util.find_spec(name) is None]


def available_port(first, *, exact=False):
    if not 1024<=first<=65535:raise ValueError("端口必须在 1024—65535 范围内。")
    for port in range(first,min(65536,first+(1 if exact else 30))):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
            try:server.bind(("127.0.0.1",port))
            except OSError:continue
            return port
    raise ValueError("本地端口已被占用；请关闭自己启动的旧窗口，或用 --port 指定其他端口。")


def budget_count(path):
    path=Path(path)
    if not path.exists():return 0
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)) as conn:
        return conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]


def prepare_database(env):
    """只初始化新库；已有库即使过期/损坏也不自动重置。"""
    if Path(env["AGENT_DB_PATH"]).exists():return
    result=subprocess.run([sys.executable,str(ROOT/"data/seed.py")],cwd=ROOT,env=env,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8")
    if result.returncode:
        raise ValueError("模拟数据库初始化失败；请检查目录权限。启动器不会覆盖已有库。")


def wait_for_health(process,url,timeout=40):
    deadline=time.monotonic()+timeout
    # 本机健康检查不走系统 HTTP 代理。
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic()<deadline:
        if process.poll() is not None:return False
        try:
            with opener.open(url+"/_stcore/health",timeout=1) as response:
                if response.status==200:return True
        except (OSError,urllib.error.URLError):pass
        time.sleep(.2)
    return False


def serve(env,port,*,open_browser=True):
    url=f"http://127.0.0.1:{port}"
    command=[sys.executable,"-m","streamlit","run",str(ROOT/"web/app.py"),
        "--server.address=127.0.0.1",f"--server.port={port}","--server.headless=true","--browser.gatherUsageStats=false"]
    process=subprocess.Popen(command,cwd=ROOT,env=env)
    try:
        if not wait_for_health(process,url):
            print("网页启动失败或等待超时，请查看上方输出；没有自动重试。",flush=True)
            return 1
        print(f"\n启动成功：{url}\n保留这个窗口；按 Ctrl+C 停止。",flush=True)
        if open_browser:
            try:
                if not webbrowser.open(url):print("浏览器未自动打开，请复制上方网址。",flush=True)
            except OSError:print("浏览器未自动打开，请复制上方网址。",flush=True)
        return process.wait()
    except KeyboardInterrupt:
        print("\n正在停止本次启动的服务...",flush=True)
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("offline","live"),required=True)
    parser.add_argument("--check-only",action="store_true",help="只做本地预检，不初始化数据库、不启动服务、不请求模型")
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--port",type=int)
    parser.add_argument("--runtime-root",type=Path,default=ROOT/"artifacts/runtime/launcher")
    args=parser.parse_args(argv)
    try:
        runtime=args.runtime_root.resolve()
        base=(ROOT/"artifacts/runtime").resolve()
        if not runtime.is_relative_to(base) or runtime==base:
            raise ValueError("启动数据目录必须是项目 artifacts/runtime 下的独立子目录。")
        # Support the documented local .env without importing it in offline mode.
        # Windows user variables are also refreshed by the PowerShell wrapper.
        if args.mode=='live' and Path(os.getenv('TICKET_ENV_FILE',str(ROOT/'.env'))).is_file():
            from target.api_config import bootstrap
            bootstrap(ROOT)
        env=build_environment(args.mode,runtime)
        if args.mode=='live':
            # This launcher opens the daily Web UI, independently of older CLI limits.
            env.update(DEEPSEEK_MAX_REQUESTS='0',DEEPSEEK_BUDGET_PATH=str(ROOT/'artifacts/runtime/manual-live/deepseek/requests.db'))
        missing=missing_dependencies(args.mode)
        if missing:
            print("缺少运行依赖："+", ".join(missing))
            print('请在项目目录运行：.\\.venv-deepseek\\Scripts\\python.exe -m pip install -r requirements-deepseek-lock.txt')
            return 1
        key_present=bool(env.get("DEEPSEEK_API_KEY","").strip())
        if args.mode=='live' and not key_present and env.get('DASHSCOPE_API_KEY','').strip():
            # A Qwen-only setup can open the same online UI without a fake DeepSeek key.
            env.update(AGENT_PROVIDER='bailian',AGENT_MODEL=env.get('DASHSCOPE_MODEL','qwen3.8-flash'),
                       AGENT_BASE_URL=env.get('DASHSCOPE_BASE_URL',''))
            key_present=True
        missing_endpoint=args.mode=='live' and env['AGENT_PROVIDER']=='bailian' and not env.get('DASHSCOPE_BASE_URL','').strip()
        if args.mode=="live" and not key_present and not args.check_only and sys.stdin.isatty():
            key=getpass.getpass("请输入 DeepSeek API Key（隐藏输入，仅本次启动使用，不保存）：").strip()
            if key:env["DEEPSEEK_API_KEY"]=key
            key_present=bool(key)
        state={"mode":args.mode,"provider":env["AGENT_PROVIDER"],"engine":env["AGENT_ENGINE"],
               "toolset":env["AGENT_LC_TOOLSET"],"api_key_configured":key_present,
               "database":str(Path(env["AGENT_DB_PATH"]).relative_to(ROOT)),
               "trace_dir":str(Path(env["AGENT_TRACE_DIR"]).relative_to(ROOT)),"model_requests_sent":0}
        if args.mode=="live":
            from target.api_usage import provider_usage
            state.update(request_limit=None,usage_policy='unlimited_usage_only',
                         usage=provider_usage(env['AGENT_PROVIDER']),historical_budgets_used_for_admission=False)
        if args.check_only:
            state["status"]="missing_key" if args.mode=="live" and not key_present else "missing_bailian_base_url" if missing_endpoint else "passed"
            print(json.dumps(state,ensure_ascii=False))
            return 0 if state["status"]=="passed" else 2
        if missing_endpoint:
            print("DASHSCOPE_BASE_URL 未配置；请设置与百炼账号地域及套餐匹配的兼容地址。没有发送模型请求。")
            return 2
        if args.mode=="live" and not key_present:
            print("DEEPSEEK_API_KEY 未配置；请重新双击在线入口并在窗口隐藏输入 Key。没有发送模型请求。")
            return 2
        port=available_port(args.port if args.port is not None else (8501 if args.mode=="offline" else 8502),exact=args.port is not None)
        print("\n离线模式：Mock，支持全部八个模拟工具，不调用模型 API。" if args.mode=="offline" else
              "\n在线模式："+('Qwen3.8-Flash Live' if env['AGENT_PROVIDER']=='bailian' else 'DeepSeek Live')+
              "，支持八个模拟票务工具。点击网页发送才调用真实模型并产生费用。",flush=True)
        if args.mode=="live":
            print("所有Live入口：DeepSeek/千问/Embedding不设本地累计请求次数上限；每次显式发送才可能产生费用。"
                  "单轮防循环与零自动重试仍生效，旧验收账本保留。",flush=True)
        print("数据库："+state["database"]+"\nTrace："+state["trace_dir"],flush=True)
        prepare_database(env)
        return serve(env,port,open_browser=not args.no_browser)
    except (ValueError,OSError,sqlite3.Error) as exc:
        # 异常对象可能含本地路径/环境细节，不打印原始内容或 SDK 响应。
        print(str(exc) if type(exc) is ValueError else f"启动未完成（{type(exc).__name__}）；检查目录权限与端口。")
        return 1


if __name__=="__main__":raise SystemExit(main())
