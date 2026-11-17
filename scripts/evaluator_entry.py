"""评委入口：零安装、零配置、零联网的离线启动。

双击根目录「一键启动.cmd」后真正执行的是这里。职责：
1. 中文环境自检（内置 Python / 依赖 / 静态 GTFS 库 / 103 条用例数据）
2. 清除继承的密钥与在线变量，保证演示过程不可能调用模型或产生费用
3. 调用既有 launch_app.py 启动离线 Web UI（端口探测、自动开浏览器、健康检查）
4. 失败时给中文诊断，并指向零依赖的「评审预览.html」

本文件不安装任何东西、不写业务库、不修改证据文件。
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# cmd.exe 默认 GBK；中文提示按控制台编码输出，不依赖 chcp。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="gbk", errors="replace")
    except (AttributeError, ValueError):
        pass
# 继承的 UTF-8 强制开关会让中文在 cmd 窗口变乱码。
os.environ.pop("PYTHONUTF8", None)
os.environ.pop("PYTHONIOENCODING", None)

PREVIEW = ROOT.parent / "评审预览.html"
LOG = ROOT / "artifacts" / "runtime" / "evaluator-launch.log"


def _check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def preflight():
    checks = []
    python = Path(sys.executable)
    checks.append(_check("内置 Python 3.12", python.is_file() and sys.version_info[:2] == (3, 12),
                         str(python)))
    missing = [n for n in ("streamlit", "pandas", "altair") if importlib.util.find_spec(n) is None]
    checks.append(_check("Web 运行依赖", not missing, "缺失：" + ", ".join(missing) if missing else "streamlit / pandas / altair 就绪"))
    checks.append(_check("应用入口", (ROOT / "web" / "app.py").is_file(), "web/app.py"))
    catalog = ROOT / "web" / "datasets" / "b_v32_20261020" / "case_catalog.json"
    checks.append(_check("103 条独立用例数据", catalog.is_file(), "web/datasets/b_v32_20261020/"))
    manifest = ROOT / "web" / "datasets" / "b_v32_20261020" / "manifest.json"
    checks.append(_check("证据 manifest", manifest.is_file(), "manifest.json"))
    static = ROOT / "artifacts" / "runtime" / "railway-static-phase8-20261102-184912" / "static.sqlite"
    checks.append(_check("铁路 GTFS 静态库", static.is_file(),
                         f"{static.name} · {static.stat().st_size / 1024 / 1024:.0f} MB" if static.is_file() else "静态库缺失，查票功能不可用"))
    checks.append(_check("模拟数据库初始化脚本", (ROOT / "data" / "seed.py").is_file(), "data/seed.py"))
    return checks


def _strip_secrets():
    removed = []
    for name in list(os.environ):
        if (name.endswith(("_API_KEY", "_TOKEN"))
                or name.startswith(("DASHSCOPE_", "DEEPSEEK_", "LANGCHAIN_", "LANGSMITH_", "OPENAI_"))):
            os.environ.pop(name, None)
            removed.append(name)
    os.environ["RAILWAY_SIMULATION_ENABLED"] = "1"
    os.environ["TICKET_WEB_OFFLINE_ONLY"] = "1"
    os.environ["TICKET_DISABLE_LOCAL_SECRETS"] = "1"
    return removed


def _log(lines):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as stream:
            stream.write("\n".join([datetime.now().isoformat(timespec="seconds"), *lines, ""]) + "\n")
    except OSError:
        pass


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    print("=" * 62)
    print("  Ticket Agent · 评委演示环境（离线 Mock，不联网、不花钱）")
    print("=" * 62)
    checks = preflight()
    for item in checks:
        print(f"  [{'OK' if item['ok'] else '!!'}] {item['name']}：{item['detail']}")
    failed = [c for c in checks if not c["ok"]]
    _log([f"[{'OK' if c['ok'] else 'FAIL'}] {c['name']} | {c['detail']}" for c in checks])
    if failed:
        print("\n  环境自检未通过，未启动服务：")
        for c in failed:
            print("    - " + c["name"] + "：" + c["detail"])
        print("\n  请确认整个文件夹是完整解压出来的（尤其 .venv-v35 与 artifacts 目录）。")
        if PREVIEW.is_file():
            print(f"  无需安装任何东西，可直接双击打开：{PREVIEW.name} 查看零依赖演示页。")
        return 1
    removed = _strip_secrets()
    print(f"\n  已隔离继承的在线密钥变量 {len(removed)} 个；本窗口不会调用任何模型 API。")
    print("  正在启动本地服务，首次约需 10–30 秒；就绪后会自动打开浏览器。")
    print("  浏览器中请走：先在 Agent 用户端完成一轮对话 → 测试工作台 → AI 场景总测试。")
    print("  保持本窗口开启；按 Ctrl+C 或关闭窗口即停止服务。\n")
    _log([f"secrets_removed={len(removed)}", "launch=offline"])
    try:
        import launch_app
        return launch_app.main(["--mode", "offline"] + argv)
    except Exception as exc:  # 兜底：给评委一句人话，而不是 traceback
        message = f"启动未完成（{type(exc).__name__}）：{exc}"
        print("\n  " + message)
        _log([message])
        if PREVIEW.is_file():
            print(f"  可直接双击 {PREVIEW.name} 查看零依赖演示页，不影响评审。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
