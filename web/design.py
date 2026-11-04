"""V3.3 presentation primitives; no model, business, or evidence writes."""
from pathlib import Path
import html
import streamlit as st

COLORS = {"passed": "var(--ta-success)", "failed": "var(--ta-danger)", "skipped": "var(--ta-muted)",
          "not_applicable": "var(--ta-neutral)", "not_verified": "var(--ta-warning)",
          "indeterminate": "var(--ta-uncertain)", "missing": "var(--ta-muted)"}
LABELS = {"passed": "通过", "failed": "失败", "skipped": "跳过", "not_applicable": "不适用",
          "not_verified": "未验证", "indeterminate": "无法判定", "missing": "缺失"}


def escape(value):
    return html.escape(str(value), quote=True)


def theme(name):
    dark = name == "深色"
    tokens = dict(
        bg="#101d2d", panel="#172b40", raised="#20364d", text="#e6eff8", muted="#a3b6cd",
        border="#304760", accent="#8db7ff", strong="#b8d1ff", soft="#1c3653",
        success="#77d8bf", danger="#ffa7b6", warning="#edc878", uncertain="#cdb5ff", neutral="#b1bdca",
        shadow="0 16px 48px -24px #00000099",
    ) if dark else dict(
        bg="#f3f6fa", panel="#ffffff", raised="#eaf0f7", text="#162e49", muted="#607188",
        border="#d6e0ec", accent="#1555c4", strong="#123f91", soft="#e8f0fd",
        success="#12765f", danger="#b83249", warning="#8c5b0a", uncertain="#7955ae", neutral="#5d6a7a",
        shadow="0 16px 48px -24px #162e4933",
    )
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


EVENT_LABELS = {'user_input':'接收输入','agent_start':'Agent 开始','model_start':'模型请求',
    'model_error':'模型请求失败','run_finished':'本轮执行结束','user_confirmation':'用户确认决定','agent_decision':'规则澄清',
    'model_end':'模型返回','model_tool_proposed':'模型提出工具','tool_proposed':'工具调用请求',
    'parameter_validation':'参数校验','permission_check':'权限检查','tool_start':'开始执行工具',
    'tool_result':'工具返回','rag_result':'检索政策证据','tool_message_created':'生成工具消息',
    'tool_result_in_model_request':'结果进入模型请求','agent_returned':'Agent 返回',
    'agent_error':'执行异常','confirmation_requested':'等待用户确认','confirmation_declined':'用户拒绝',
    'operation_resumed':'恢复模拟操作','followup_start':'准备后续问题',
    'followup_model_request':'模型生成后续问题','followup_success':'追问生成完成',
    'followup_error':'追问生成异常','followup_fallback':'使用规则追问',
    'followup_saved':'保存追问快照','followup_http':'追问请求记录'}


def event_label(event):
    status={'recorded':'已记录','accepted':'已接受','passed':'通过','succeeded':'成功',
            'failed':'失败','blocked':'已拦截','approved':'已确认','declined':'已取消'}.get(event.get('status'),event.get('status','未记录'))
    return EVENT_LABELS.get(event.get('event_type'),event.get('event_type','事件'))+' · '+str(status)


PROCESSING = '<div class="ta-processing" role="status" aria-live="polite"><span></span>正在处理请求…</div>'


def processing_event(event):
    """Show only a phase actually emitted by the executor, never invented reasoning."""
    label=event_label(event)
    if event.get('tool'):label+=' · '+str(event['tool'])
    return '<div class="ta-processing" role="status" aria-live="polite"><span></span>'+escape(label)+'</div>'


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
    if len(rows)>20:
        with st.expander('排序选项'):
            order=st.selectbox('排序字段',['原始顺序']+columns,key='table_sort_'+key)
            descending=st.checkbox('降序',key='table_desc_'+key)
        if order!='原始顺序':
            visible.sort(key=lambda r:(r.get(order) is None,0 if isinstance(r.get(order),(int,float)) else 1,
                r.get(order) if isinstance(r.get(order),(int,float)) else text(r.get(order)).casefold()),reverse=descending)
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
