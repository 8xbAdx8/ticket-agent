"""V3.3 presentation primitives; no model, business, or evidence writes."""
from pathlib import Path
import html
import streamlit as st

COLORS = {"passed": "#54c5aa", "failed": "#f17b86", "skipped": "#8ba1bb",
          "not_applicable": "#a2a8b5", "not_verified": "#d9b76c", "indeterminate": "#b7a0df", "missing": "#68758b"}
LABELS = {"passed": "通过", "failed": "失败", "skipped": "跳过", "not_applicable": "不适用",
          "not_verified": "未验证", "indeterminate": "无法判定", "missing": "缺失"}


def escape(value):
    return html.escape(str(value), quote=True)


def theme(name):
    dark = name == "深色"
    tokens = dict(bg="#10141d", panel="#181e2a", raised="#202838", text="#e9edf5", muted="#a6b1c5", border="#2c3547", accent="#64d6b6") if dark else dict(
        bg="#f4f6fa", panel="#ffffff", raised="#eef2f7", text="#1b2638", muted="#586a81", border="#dce3ed", accent="#147d68")
    css = ":root{" + ";".join("--ta-"+k+":"+v for k,v in tokens.items()) + ";--primary-color:var(--ta-accent);--background-color:var(--ta-bg);--secondary-background-color:var(--ta-panel);--text-color:var(--ta-text);}" 
    st.markdown("<style>"+css+(Path(__file__).with_name("design.css")).read_text(encoding="utf-8")+"</style>", unsafe_allow_html=True)


def header(title, subtitle, badge="V3.3"):
    st.markdown(f'<div class="ta-heading"><div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div><span class="ta-badge">{escape(badge)}</span></div>', unsafe_allow_html=True)


def kpis(items):
    columns = st.columns(len(items))
    for col, (label, value, note) in zip(columns, items):
        col.markdown(f'<div class="ta-kpi"><span>{escape(label)}</span><strong>{escape("未知" if value is None else value)}</strong><small>{escape(note)}</small></div>', unsafe_allow_html=True)


def tag(text, status="passed"):
    return f'<span class="ta-tag" style="color:{COLORS.get(status, COLORS["missing"])}">{escape(text)}</span>'


def empty(title, detail):
    st.markdown(f'<div class="ta-empty"><b>{escape(title)}</b><p>{escape(detail)}</p></div>', unsafe_allow_html=True)


def panel_title(title, note=None):
    st.markdown(f"### {title}")
    if note:
        st.caption(note)


PROCESSING = '<div class="ta-processing" role="status" aria-live="polite"><span></span>正在处理请求…</div>'
