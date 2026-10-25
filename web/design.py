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


def csv_cell(value):
    """Prevent spreadsheet formula execution in downloadable evidence text."""
    value=str(value)
    return "'"+value if value.lstrip().startswith(("=","+","-","@","\t","\r")) else value


def table(rows,key,search=True):
    """Theme-consistent evidence table. Filter and CSV share the same rows."""
    import csv
    import io
    import json
    from target.diagnostics import sanitize
    rows=sanitize(list(rows))
    if not rows:
        st.caption("暂无该类记录。")
        return
    columns=list(dict.fromkeys(k for r in rows for k in r))
    text=lambda value:"未知" if value is None else "是" if value is True else "否" if value is False else json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
    needle=st.text_input("筛选表格内容",key="table_search_"+key) if search and len(rows)>10 else ""
    visible=[r for r in rows if not needle or needle.lower() in (json.dumps(r,ensure_ascii=False)+" "+" ".join(text(v) for v in r.values())).lower()]
    labels={"id":"检查编号","name":"检查项目","expect":"期望","actual":"实际","passed":"是否通过","detail":"说明"}
    headings="".join("<th>"+escape(labels.get(c,c))+"</th>" for c in columns)
    body="".join("<tr>"+"".join("<td>"+escape(text(r.get(c)))+"</td>" for c in columns)+"</tr>" for r in visible)
    st.markdown('<div class="ta-table-wrap"><table aria-label="证据数据表"><thead><tr>'+headings+'</tr></thead><tbody>'+body+'</tbody></table></div>',unsafe_allow_html=True)
    st.caption(f"当前显示 {len(visible)} / {len(rows)} 条；横向空间不足时仅在表格内滚动。")
    output=io.StringIO(newline="")
    writer=csv.DictWriter(output,fieldnames=columns)
    writer.writeheader()
    writer.writerows([{c:csv_cell(text(r.get(c))) for c in columns} for r in visible])
    st.download_button("下载当前表格 CSV",("\ufeff"+output.getvalue()).encode("utf-8"),file_name="evidence-table.csv",mime="text/csv",key="table_export_"+key)
