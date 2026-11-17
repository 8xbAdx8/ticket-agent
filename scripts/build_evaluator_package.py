"""从当前工作目录生成一个「评委交付包」：干净、无密钥、体积可控。

解决的问题：评委不该拿到 2.2G 的开发现场，也不该看到明文 API Key 与几百个
历史测试临时目录。本脚本只复制运行必需的文件，并生成一个新的交付根目录。

用法： <内置 Python> scripts/build_evaluator_package.py [--out DIR] [--force]
默认输出：部署目录同级的 TicketAgent_评委交付
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent          # ticket-agent
DEPLOY = ROOT.parent                                   # agent_test
DEFAULT_OUT = DEPLOY.parent / "TicketAgent_评委交付"

# artifacts/runtime 里只有这些是运行/演示必需的，其余是开发期历史产物。
KEEP_RUNTIME = {
    "railway-static-phase8-20261102-184912",           # 893MB 静态 GTFS，查票必需
    "v35-rag",                                         # RAG 离线索引
    "v39-architecture-v1.2.2-20261103-121613",         # 回归测试要读的冻结 schema.sql
}
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".git", "traces", "_secrets", "node_modules"}
# 交付包里只保留根目录的一键入口；包内这些旧脚本/旧说明会误导评委。
SKIP_ROOT_FILES = {"启动_在线模式.cmd", "启动_离线模式.cmd", "启动说明.md", "先读我-运行说明.txt"}
ROOT_FILES = ("一键启动.cmd", "README.md", "现阶段总结.md", "评审预览.html")


def ignore_factory():
    def ignore(directory, names):
        current = Path(directory)
        try:
            rel = current.relative_to(ROOT)
        except ValueError:
            return set()
        parts = rel.parts
        in_venv = bool(parts) and parts[0] == ".venv-v35"
        blocked = set()
        for name in names:
            # 便携 Python 环境整体保留：.pyc / __pycache__ 也是运行环境的一部分。
            if in_venv:
                continue
            if name == ".env" or name.endswith(".pyc") or (not parts and name in SKIP_ROOT_FILES):
                blocked.add(name)
            elif name in SKIP_NAMES and not (name == "traces" and len(parts) > 1):
                blocked.add(name)
            elif len(parts) == 2 and parts[0] == "artifacts" and parts[1] == "runtime" and name not in KEEP_RUNTIME:
                blocked.add(name)
        return blocked
    return ignore


def human(size):
    return f"{size / 1024 / 1024:.1f} MB" if size < 1024 ** 3 else f"{size / 1024 ** 3:.2f} GB"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build(out: Path, force=False):
    out = out.resolve()
    if out in (DEPLOY.resolve(), ROOT.resolve()) or any(parent in (DEPLOY.resolve(), ROOT.resolve()) for parent in out.parents):
        raise ValueError("输出目录不能是源目录或其子目录（会递归复制）。")
    if out.exists():
        if not force:
            raise FileExistsError(f"输出目录已存在：{out}；确认后加 --force 重新生成。")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    target = out / "ticket-agent"
    shutil.copytree(ROOT, target, ignore=ignore_factory())
    for name in ROOT_FILES:
        source = DEPLOY / name
        if source.is_file():
            shutil.copy2(source, out / name)
        else:
            print(f"  [提示] 根目录缺少 {name}，交付包中将不包含。")
    # 交付包内不放任何真实密钥：离线模式本来也不读 .env。
    (target / ".env").write_text(
        "# 评委交付包：离线演示不需要任何 API Key，此文件故意为空。\n"
        "# 如需在线模式，请自行填入你自己的 Key 与兼容端点；演示请用根目录「一键启动.cmd」。\n",
        encoding="utf-8")
    # 启动脚本编码自校验：必须是 CRLF + GBK 可读 + 无 BOM。
    cmd = out / "一键启动.cmd"
    if cmd.is_file():
        raw = cmd.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "启动脚本不应带 BOM"
        assert raw.count(b"\r\n") > 0 and b"\n" not in raw.replace(b"\r\n", b""), "启动脚本必须 CRLF"
        raw.decode("gbk")
    files = [p for p in out.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    key_files = [out / "一键启动.cmd", out / "评审预览.html", out / "README.md",
                 target / "web" / "datasets" / "b_v32_20261020" / "case_catalog.json"]
    lines = [
        "Ticket Agent · 评委交付包清单", "=" * 46,
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"输出目录：{out}", f"文件数：{len(files):,}    总大小：{human(total)}",
        "", "评委只需两步：",
        "  1) 完整解压/拷贝整个文件夹（勿在压缩包内运行）",
        "  2) 双击根目录「一键启动.cmd」，浏览器自动打开；或双击「评审预览.html」零依赖查看",
        "", "安全与边界：",
        "  · 本包不含任何 API Key；.env 为空模板，一键启动为离线 Mock，不联网、不产生费用",
        "  · 已排除开发期历史运行数据、临时测试库、Trace、源码 __pycache__ 与包内旧启动脚本",
        "  · 保留 893MB 静态 GTFS 库（真实车站/车次查询必需）与内置 Python 环境",
        "  · 页面成绩为 B 独立 Mock 测试快照，不是当前版本重跑成绩；详见 README 与现阶段总结",
        "", "关键文件 SHA256：",
    ]
    for path in key_files:
        lines.append(f"  {path.relative_to(out).as_posix()}  {digest(path) if path.is_file() else '缺失'}")
    (out / "交付清单.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, len(files), total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        path, count, size = build(args.out, args.force)
        print(f"交付包已生成：{path}\n文件 {count:,} 个 · {human(size)}")
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"生成失败：{exc}")
        raise SystemExit(1)
