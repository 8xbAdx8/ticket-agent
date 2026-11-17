"""评委交付包：裁剪无用辅助文件 + 生成可发送的 zip。

设计前提（重要）：
- artifacts/runtime/.../static.sqlite 是证据库。target/v39/static.py 在 RailwayStatic
  初始化时对整个文件做 SHA256 校验，不匹配会抛 STATIC_DATA_IDENTITY_MISMATCH。
  因此本脚本绝不改动、不重建、不裁剪该数据库，只依赖 zip deflate 压缩它。
- .venv-v35 中的第三方包一律不删目录：pyarrow 是 streamlit 硬依赖，kubernetes /
  onnxruntime / chromadb_rust_bindings 是 chromadb 依赖链，删了会让 RAG 页炸掉。
  只删运行时绝不读取的辅助文件（source map / 类型存根 / 包内文档 / 自带测试）。

用法：
  python scripts/build_send_zip.py --filter-zip   # 推荐：打包时过滤（不改源目录）
  python scripts/build_send_zip.py --slim         # 原地裁剪 + 重建交付清单
  python scripts/build_send_zip.py --zip          # 直接打包 staging 全量

推荐用 --filter-zip：它在写 zip 时按 _droppable() 过滤辅助文件与超长
第三方模板，不删除 staging 的任何文件（规避批量删除拦截），并使用短根目录
TicketAgent/ + 最长路径 ≤150 硬校验，避免评委解压报 0x80010135。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

DELIVERY = Path(r"E:\3AIproject\TicketAgent_评委交付")
ZIP_PATH = DELIVERY.parent / "TicketAgent_评委交付.zip"
AGENT = DELIVERY / "ticket-agent"
VENV = AGENT / ".venv-v35"

# Windows Explorer still enforces MAX_PATH (260) when extracting / copying a
# zip.  Keep the archive's own root short so a judge can unpack it into a
# normal Downloads/Desktop path without error 0x80010135 「路径太长」.
ZIP_ROOT = "TicketAgent"
MAX_REL_PATH = 150

# venv-only trees that are never imported at runtime AND contain the longest
# paths in the archive (Streamlit's bundled AI skill example templates and
# onnxruntime's flatbuffers code generator).  Removing them drops the longest
# entry from 181 to well under 150 characters.
DROP_VENV_CHAINS = (
    (".agents", "skills"),
    ("onnxruntime", "tools", "ort_format_model"),
)

# venv 内可删：运行时完全不读取
DROP_SUFFIXES = (".js.map", ".pyi", ".md", ".rst")
DROP_NAMES = {
    "license", "license.txt", "license.md", "license.rst", "copying", "copying.txt",
    "notice", "notice.txt", "authors", "authors.txt", "authors.rst",
    "changelog", "changelog.md", "changelog.rst", "changes", "changes.rst",
    "history", "history.rst", "contributors", "contributors.rst",
    "readme", "readme.txt", "readme.md", "readme.rst",
}
DROP_DIR_NAMES = {"tests", "test", "__pycache__", ".pytest_cache", ".mypy_cache"}
DROP_FILE_NAMES = {
    "thumbs.db", ".ds_store", "*.bak", "*.tmp", "*.pyc", "*.pyo",
}
# 运行产生的临时日志（不是证据）
DROP_RELATIVE = {
    Path("ticket-agent/artifacts/runtime/evaluator-launch.log"),
}

KEY_FILES = [
    "一键启动.cmd",
    "评审预览.html",
    "README.md",
    "ticket-agent/web/datasets/b_v32_20261020/case_catalog.json",
]


def _in_venv(rel: Path) -> bool:
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == "ticket-agent" and parts[1] == ".venv-v35"


def _has_chain(parts, chain):
    """Whether a path contains this exact consecutive directory chain."""
    width = len(chain)
    return any(tuple(parts[i:i + width]) == chain for i in range(len(parts) - width + 1))


def _droppable(rel: Path, is_dir: bool) -> bool:
    if rel in DROP_RELATIVE:
        return True
    name = rel.name.lower()
    # 任何层级的 Python 缓存都是运行垃圾，不限于 venv
    if is_dir and name in {"__pycache__", ".pytest_cache", ".mypy_cache"}:
        return True
    if not _in_venv(rel):
        return False
    # Applies to files as well as directories, so a zip-time include filter
    # (which never walks directories) drops exactly the same entries as slim().
    if any(_has_chain(rel.parts, chain) for chain in DROP_VENV_CHAINS):
        return True
    if is_dir:
        return name in DROP_DIR_NAMES or name == "licenses"
    if name.endswith(DROP_SUFFIXES) or name in DROP_NAMES:
        return True
    if name in DROP_FILE_NAMES or name.endswith((".bak", ".tmp", ".pyc", ".pyo")):
        return True
    # dist-info 里的非运行必需记录
    if ".dist-info" in rel.parts and name in {
        "direct_url.json", "record.jws", "record.p7s", "requested", "installer",
    }:
        return True
    return False


def _walk_droppable():
    """返回 (待删目录, 待删文件)，目录已按深度倒序，且不含被父目录包含的项。"""
    dirs, files = [], []
    for root, dirnames, filenames in os.walk(DELIVERY):
        rootp = Path(root)
        for d in dirnames:
            p = rootp / d
            if _droppable(p.relative_to(DELIVERY), True):
                dirs.append(p)
        for f in filenames:
            p = rootp / f
            if _droppable(p.relative_to(DELIVERY), False):
                files.append(p)
    # 目录去重：只保留最外层；被父目录覆盖的文件交给删除阶段的 exists 判断
    outer = []
    for d in sorted(dirs, key=lambda p: len(p.parts)):
        if not any(_is_under(d.relative_to(DELIVERY), x.relative_to(DELIVERY)) for x in outer):
            outer.append(d)
    return outer, files


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _totals():
    files = [p for p in DELIVERY.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def slim():
    dirs, files = _walk_droppable()
    before_n, before_b = _totals()
    freed = 0
    removed = 0
    for d in dirs:
        freed += _size(d)
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    for f in files:
        # 父目录可能刚被删掉
        if not f.exists():
            continue
        freed += _size(f)
        try:
            f.unlink()
        except OSError:
            continue
        removed += 1
    # 清理空目录
    for d in sorted((p for p in DELIVERY.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    after_n, after_b = _totals()
    print(f"[slim] 删除 {removed} 项（目录 {len(dirs)} / 文件 {len(files)}），释放 {freed/1048576:.1f} MB")
    print(f"[slim] 文件数 {before_n} -> {after_n}；体积 {before_b/1073741824:.2f} GB -> {after_b/1073741824:.2f} GB")
    write_manifest(after_n, after_b, slim_note=f"已裁剪 {removed} 项运行时不读取的辅助文件（{freed/1048576:.1f} MB）")


def write_manifest(n: int, total: int, slim_note: str = "", zip_size: int | None = None):
    lines = [
        "Ticket Agent · 评委交付包清单",
        "=" * 46,
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"输出目录：{DELIVERY}",
        f"文件数：{n:,}    解压后总大小：{total/1073741824:.2f} GB",
    ]
    if zip_size is not None:
        lines.append(f"发送用压缩包：{ZIP_PATH.name}（{zip_size/1048576:.0f} MB）")
    lines += [
        "",
        "评委只需两步：",
        f"  1) 完整解压/拷贝整个「{ZIP_ROOT}」文件夹（勿在压缩包内运行）",
        "  2) 双击根目录「一键启动.cmd」，浏览器自动打开；或双击「评审预览.html」零依赖查看",
        "",
        "解压位置建议：",
        "  · 请解压到盘符根目录或浅层目录，例如 D:\\TicketAgent 或 D:\\Downloads\\；",
        "    不要放进多层嵌套的中文长路径，Windows 资源管理器会报 0x80010135「路径太长」。",
        "  · 包内已使用短根目录并剔除第三方包里超长的示例模板，最长相对路径 ≤ 150 字符。",
        "",
        "安全与边界：",
        "  · 本包不含任何 API Key；.env 为空模板，一键启动为离线 Mock，不联网、不产生费用",
        "  · 已排除开发期历史运行数据、临时测试库、Trace、源码 __pycache__ 与包内旧启动脚本",
    ]
    if slim_note:
        lines.append(f"  · {slim_note}")
    lines += [
        "  · 裁剪范围仅限第三方包的 *.js.map / *.pyi / 自带文档与自带测试、以及运行产生的日志；未删除任何依赖包",
        "  · 保留 852 MB 静态 GTFS 库（真实车站/车次查询必需）。该库由代码强校验 SHA256，"
        "任何裁剪都会触发 STATIC_DATA_IDENTITY_MISMATCH，因此原样保留，仅靠 zip 压缩减小传输体积",
        "  · 保留内置 Python 环境（streamlit / pandas / altair / pyarrow 等运行必需依赖）",
        "  · 页面成绩为 B 独立 Mock 测试快照，不是当前版本重跑成绩；详见 README 与现阶段总结",
        "",
        "关键文件 SHA256：",
    ]
    for rel in KEY_FILES:
        p = DELIVERY / rel
        lines.append(f"  {rel}  {_sha(p) if p.is_file() else '缺失'}")
    (DELIVERY / "交付清单.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[manifest] 已重建 交付清单.txt")


def _filter_droppable(rel: Path) -> bool:
    """Zip-time include filter: an entry is skipped if it or any ancestor
    directory would have been deleted by slim().  No filesystem mutation."""
    parts = rel.parts
    return (any(_droppable(Path(*parts[:i]), True) for i in range(1, len(parts)))
            or _droppable(rel, False))


def make_zip(include_filter: bool = False):
    """Build the archive.  --filter-zip applies slim()'s rules while writing
    instead of deleting staging files (sandbox-safe, and keeps the source
    delivery folder intact for a later rebuild)."""
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    manifest_name = "交付清单.txt"
    # 清单需要先知道压缩包大小，因此最后单独追加，保证 zip 内外两份清单内容一致
    files = sorted(p for p in DELIVERY.rglob("*")
                   if p.is_file() and p.name != manifest_name)
    removed = 0
    if include_filter:
        kept = [p for p in files if not _filter_droppable(p.relative_to(DELIVERY))]
        removed = len(files) - len(kept)
        files = kept
    total = sum(p.stat().st_size for p in files)
    print(f"[zip] 待压缩 {len(files):,} 个文件 / {total/1073741824:.2f} GB")
    opts = dict(compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True)
    with zipfile.ZipFile(ZIP_PATH, "w", **opts) as zf:
        for i, p in enumerate(files, 1):
            arc = Path(ZIP_ROOT) / p.relative_to(DELIVERY)
            zf.write(p, arc.as_posix())
            if i % 3000 == 0:
                print(f"[zip] {i}/{len(files)}", flush=True)
    size = ZIP_PATH.stat().st_size
    # 清单数字必须对应真正进入压缩包的文件，不能写源目录的总量
    if include_filter:
        n, b = len(files), total
        note = (f"打包时按同一套规则过滤 {removed} 项运行时不读取的辅助文件、"
                f"缓存与超长第三方模板；源目录未改动")
    else:
        n, b = _totals()
        note = ""
    write_manifest(n, b, zip_size=size, slim_note=note)
    with zipfile.ZipFile(ZIP_PATH, "a", **opts) as zf:
        zf.write(DELIVERY / manifest_name,
                 (Path(ZIP_ROOT) / manifest_name).as_posix())
    size = ZIP_PATH.stat().st_size
    print(f"[zip] 完成：{ZIP_PATH}  {size/1048576:.0f} MB  "
          f"(压缩率 {size/total:.1%})")
    # 全量 CRC 校验 + 关键成员检查 + Windows MAX_PATH 防护
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
        assert len(names) == len(files) + 1, f"条目数不一致：{len(names)}"
        key = (Path(ZIP_ROOT) / "一键启动.cmd").as_posix()
        assert key in names and zf.read(key), "一键启动.cmd 缺失"
        assert (Path(ZIP_ROOT) / manifest_name).as_posix() in names
        longest = max((len(n.replace("/", "\\")) for n in names), default=0)
        assert longest <= MAX_REL_PATH, (
            f"包内最长路径 {longest} 字符超过 {MAX_REL_PATH}；"
            "解压到普通目录会触发 Windows 错误 0x80010135「路径太长」")
        bad = zf.testzip()
        assert bad is None, f"CRC 校验失败：{bad}"
        print(f"[zip] 包内最长相对路径 {longest} 字符（上限 {MAX_REL_PATH}）")
    print("[zip] CRC 全量校验通过；清单已同步进压缩包")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slim", action="store_true", help="原地裁剪 staging 目录")
    ap.add_argument("--zip", action="store_true", help="直接打包 staging 全量")
    ap.add_argument("--filter-zip", action="store_true",
                    help="打包时按 slim 规则做 include filter（推荐：不改源、规避批量删除与路径过长）")
    args = ap.parse_args()
    if not DELIVERY.is_dir():
        print(f"交付目录不存在：{DELIVERY}", file=sys.stderr)
        return 1
    if args.filter_zip:
        make_zip(include_filter=True)
        return 0
    if args.slim or (not args.slim and not args.zip):
        slim()
    if args.zip:
        make_zip()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
