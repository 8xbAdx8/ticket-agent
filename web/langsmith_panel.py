"""Developer-side LangSmith panel: read receipts, explain status, explicit upload/verify.

The user page only keeps local Trace. This module never uploads automatically:
a POST happens only from the explicit consent button, a GET only from the
explicit re-verify button. Rendering and refresh are read-only.
"""
import json
from pathlib import Path

import streamlit as st

from target.diagnostics import sanitize

LOCAL_STATES = {"not_attempted", "user_disabled", "consent_required", "not_configured", "local_trace_required"}

STATE_STYLE = {
    "not_uploaded": ("尚未上传", "idle", "本地记录已保存，尚未上传。"),
    "uploading": ("上传处理中", "wait", "上传请求已提交，等待远端确认；结果未知前不当作成功。"),
    "accepted_pending": ("已接受待核验", "wait", "服务器已接受请求，但尚未证明记录可以读取；HTTP 202 不是上传成功。"),
    "verified": ("已验证", "ok", "已成功读取远端记录，并与本地核验一致。"),
    "verify_failed": ("核验失败", "bad", "远端读取失败；上传记录未必失败，原始 Run ID 保留。"),
    "upload_failed": ("上传失败", "bad", "上传请求本身失败；不会自动重试。"),
}


def classify(receipt):
    """Map a saved receipt to one of six user-facing states.

    Explicit rules: 202 alone is never success; 404 alone is never upload failure.
    """
    if not receipt:
        return {"key": "not_uploaded", "label": STATE_STYLE["not_uploaded"][0],
                "tone": STATE_STYLE["not_uploaded"][1], "detail": STATE_STYLE["not_uploaded"][2],
                "reason": "没有远端回执"}
    status = str(receipt.get("remote_status") or "")
    post = receipt.get("post_http_status")
    get = receipt.get("get_http_status")
    error = receipt.get("error") or {}
    reason = ""
    if isinstance(error, dict):
        reason = str(error.get("category") or "")
        if error.get("http_status"):
            reason += f"（HTTP {error['http_status']}）" if reason else f"HTTP {error['http_status']}"
    if status == "verified":
        return {"key": "verified", "label": "已验证", "tone": "ok",
                "detail": "远端读取成功，记录与本地一致。", "reason": reason}
    if status == "upload_outcome_unknown" or (post is None and status not in LOCAL_STATES):
        return {"key": "uploading", "label": "上传处理中", "tone": "wait",
                "detail": "请求已提交但未取得明确响应；保留已提交的 Run ID，不重复 POST。", "reason": reason}
    if post in (200, 201, 202):
        if get == 404:
            return {"key": "accepted_pending", "label": "已接受待核验", "tone": "wait",
                    "detail": "服务器已接受（HTTP 202），但读取返回 404；这是暂不可读，不是上传失败。",
                    "reason": reason or "run_not_readable（HTTP 404）"}
        if status == "accepted_unverified" or status == "pending_verification":
            if isinstance(get, int) and get >= 500:
                return {"key": "verify_failed", "label": "核验失败", "tone": "bad",
                        "detail": "服务器接受了上传，但读取遇到服务端错误；Run ID 保留。", "reason": reason}
            return {"key": "accepted_pending", "label": "已接受待核验", "tone": "wait",
                    "detail": f"服务器已接受（HTTP {post}），尚未完成读取核验；HTTP 202 不是上传成功。",
                    "reason": reason}
        if status == "failed" or (isinstance(get, int) and get not in (200, 202, 404, 429)):
            return {"key": "verify_failed", "label": "核验失败", "tone": "bad",
                    "detail": "上传已被接受，但远程读取/比对失败；这不等于上传失败。", "reason": reason}
        return {"key": "accepted_pending", "label": "已接受待核验", "tone": "wait",
                "detail": f"上传已被接受（HTTP {post}），等待读取核验；202 不是上传成功。", "reason": reason}
    if post is not None or status == "failed":
        return {"key": "upload_failed", "label": "上传失败", "tone": "bad",
                "detail": "上传请求返回失败；没有自动重试。", "reason": reason}
    return {"key": "not_uploaded", "label": "尚未上传", "tone": "idle",
            "detail": "本地记录已保存，尚未发起远端上传。" if status != "local_trace_required" else "本地 Trace 尚未保存，不能上传。",
            "reason": reason or status}


def _read_rows(path):
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def receipts_for(session, trace_id=None):
    """Merge saved exports and readbacks, latest receipt per remote run wins.

    A readback is a verification, not a second upload: keep the upload count and
    HTTP total from the earlier export when the readback row does not carry them.
    """
    if session is None:
        return []
    exports = _read_rows(session.trace_dir / "langsmith_exports.jsonl")
    readbacks = _read_rows(session.trace_dir / "langsmith_readbacks.jsonl")
    rows = []
    for row in exports + readbacks:
        if trace_id and row.get("local_trace_id") != trace_id:
            continue
        rows.append(row)
    grouped = {}
    for row in sorted(rows, key=lambda item: str(item.get("timestamp") or "")):
        key = row.get("remote_run_id") or f"{row.get('local_trace_id')}-{row.get('timestamp')}"
        merged = grouped.setdefault(key, {})
        previous_uploads = merged.get("upload_attempts") or 0
        previous_http = merged.get("http_requests") or 0
        merged.update({k: v for k, v in row.items() if v is not None})
        merged["upload_attempts"] = max(previous_uploads, row.get("upload_attempts") or 0)
        merged["http_requests"] = max(previous_http, row.get("http_requests") or 0)
        if merged.get("remote_status") == "verified":
            merged["error"] = None
        if not merged.get("post_http_status") and row.get("post_http_status") is None:
            continue
    return sorted(grouped.values(), key=lambda row: str(row.get("timestamp") or ""), reverse=True)


def _metric(label, value, sub=""):
    return (f'<div class="ta-ls-metric"><span>{label}</span><b>{value}</b>'
            f'{f"<small>{sub}</small>" if sub else ""}</div>')


def _short(value, limit=18):
    text = str(value or "未记录")
    return text if len(text) <= limit else text[:limit] + "…"


def render(session, audit):
    """Full-width developer section; never writes unless a button is pressed."""
    st.divider()
    st.subheader("LangSmith 远端追踪")
    st.caption("这里只管理脱敏导出与远端核验；本地 Trace 始终先在用户端/开发者端保存。"
               "展开或刷新本区域不会上传，也不会调用模型。")
    if session is None or audit is None:
        st.markdown('<div class="ta-ls-card ta-ls-idle"><div class="ta-ls-top"><b>尚未上传</b>'
                    '<span>没有选中的运行</span></div><p>在左侧选择一次运行后，这里显示它的本地 Trace ID 与远端回执。</p></div>',
                    unsafe_allow_html=True)
        return

    trace_id = audit.get("trace_id")
    receipts = receipts_for(session, trace_id)
    latest = receipts[0] if receipts else None
    state = classify(latest)
    run = session.agent.langchain_engine.last_live_run if (session.agent and getattr(session.agent, "langchain_engine", None)) else None
    is_latest_live = bool(run and run.get("trace_id") == trace_id and not getattr(session, "read_only", False))
    remote_id = (latest or {}).get("remote_run_id")
    error = (latest or {}).get("error") or {}

    metrics = st.columns(4, gap="small")
    values = [
        ("本地 Trace ID", _short(trace_id), "run_id"),
        ("远程 Run ID", _short(remote_id), "远端"),
        ("上传次数", str((latest or {}).get("upload_attempts", 0) or 0), "POST"),
        ("HTTP 请求", str((latest or {}).get("http_requests", 0) or 0), "POST+GET"),
    ]
    for column, (label, value, sub) in zip(metrics, values):
        column.markdown(_metric(label, value, sub), unsafe_allow_html=True)

    reason = state["reason"]
    st.markdown(
        f'<div class="ta-ls-card ta-ls-{state["tone"]}">'
        f'<div class="ta-ls-top"><b>{state["label"]}</b>'
        f'<span>{_short(remote_id, 24) if remote_id else "未生成远端 Run ID"}</span></div>'
        f'<p>{state["detail"]}</p>'
        f'{f"<p class=ta-ls-reason>最近失败原因：{reason}</p>" if reason and state["tone"] != "ok" else ""}'
        '</div>', unsafe_allow_html=True)

    if receipts:
        rows = []
        for row in receipts[:5]:
            item_state = classify(row)
            rows.append([_short(row.get("local_trace_id"), 14), _short(row.get("remote_run_id"), 14),
                         str(row.get("timestamp") or "未记录")[:19].replace("T", " "),
                         row.get("upload_attempts") if row.get("upload_attempts") is not None else "未记录",
                         row.get("http_requests") if row.get("http_requests") is not None else "未记录",
                         item_state["label"],
                         str((row.get("error") or {}).get("category") or "—")])
        with st.expander(f"上传与核验记录（{len(receipts)} 条）", expanded=True):
            st.markdown('<div class="ta-ls-table">', unsafe_allow_html=True)
            st.table({"本地 Trace": [r[0] for r in rows], "远程 Run": [r[1] for r in rows],
                      "上传时间": [r[2] for r in rows], "上传次数": [r[3] for r in rows],
                      "HTTP": [r[4] for r in rows], "状态": [r[5] for r in rows], "最近失败": [r[6] for r in rows]})
            st.markdown('</div>', unsafe_allow_html=True)

    if getattr(session, "read_only", False):
        st.caption("历史回放为只读：可查看回执，不能上传或重新核验。新会话执行 Live 后再操作。")
    elif not is_latest_live:
        st.caption("当前选中的是历史运行：只展示回执。上传/核验只绑定本会话最新 Live 运行，避免把旧记录重新发送。")
    else:
        consent_key = "ls_consent_" + str(trace_id)
        if latest and remote_id:
            agree = st.checkbox("允许读取现有远端记录核验（仅 GET，最多 3 次；不重新上传）", key=consent_key + "_read")
            if st.button("重新核验现有远端记录（仅 GET）", disabled=not agree, key="ls_recheck_" + str(trace_id)):
                try:
                    session.recheck_export(consent=True)
                    st.rerun()
                except Exception as exc:
                    st.error("核验未完成，未自动重试：" + str(exc)[:160])
            st.caption("已有远端 Run ID：" + str(remote_id) + "；不会重复 POST。")
        else:
            from target.observability import configuration_status
            state_cfg = configuration_status()
            agree = st.checkbox("我已检查脱敏内容，允许将以上运行发送至 LangSmith", key=consent_key + "_post")
            enabled = bool(state_cfg.get("enabled") and state_cfg.get("key_configured"))
            if not enabled:
                st.caption("LangSmith 未启用或未配置：请到集成中心检查；本区域不会自动上传。")
            if st.button("上传本轮并核验远端", disabled=not agree or not enabled, key="ls_export_" + str(trace_id)):
                try:
                    session.export_last(consent=True)
                    st.rerun()
                except Exception as exc:
                    st.error("上传未完成，未自动重试：" + str(exc)[:160])
            st.caption("最多 1 次 POST + 3 次 GET；202 只表示已接受，核验通过后才显示已验证。")

    with st.expander("查看高级技术详情", expanded=False):
        st.caption("HTTP 202 表示服务器已接受，不等于上传成功；HTTP 404 表示暂不可读，不等于上传失败。")
        if not latest:
            st.caption("没有远端回执。")
        else:
            st.json(sanitize(latest), expanded=False)
            attempts = latest.get("attempts") or latest.get("http_attempts") or []
            if attempts:
                st.markdown("**HTTP 请求与响应**")
                for attempt in attempts:
                    if not isinstance(attempt, dict):
                        continue
                    st.caption(f"{attempt.get('method', '?')} {attempt.get('url', attempt.get('path', ''))} · "
                               f"HTTP {attempt.get('http_status', '未记录')} · "
                               f"request_id / attempt_id {attempt.get('request_id') or attempt.get('attempt_id') or '未记录'} · "
                               f"耗时 {attempt.get('duration_ms', attempt.get('latency_ms', '未记录'))} ms")
                    st.json(sanitize(attempt), expanded=False)
            request_id = latest.get("request_id") or next(
                (attempt.get("request_id") or attempt.get("attempt_id")
                 for attempt in attempts if isinstance(attempt, dict)), "未记录")
            st.caption("Request ID / attempt_id：" + str(request_id))
            st.caption("Payload SHA256：" + str(latest.get("payload_sha256") or "未记录"))
            st.caption("Workspace Hash：" + str(latest.get("workspace_sha256") or "未记录"))
            if error:
                st.json(sanitize(error), expanded=False)
