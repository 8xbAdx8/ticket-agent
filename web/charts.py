"""Altair charts consume reviewed rows, not demonstration fixtures."""
import altair as alt
import pandas as pd
import streamlit as st
from web.design import COLORS, LABELS
from web.evidence import MUTATIONS, STATUS_LABELS


def finish(chart,height=245):
    dark=st.session_state.get("theme","深色")=="深色"
    text="#a6b1c5" if dark else "#586a81"
    return chart.properties(height=height,background="transparent").configure_view(stroke=None).configure_axis(
        labelColor=text,titleColor=text,gridColor="#2c3547" if dark else "#e4e9f0",domain=False,labelFont="Microsoft YaHei",titleFont="Microsoft YaHei").configure_legend(
        labelColor=text,titleColor=text,labelFont="Microsoft YaHei").configure_title(color=text,font="Microsoft YaHei")


def dimensions(rows):
    frame=pd.DataFrame(rows)
    return finish(alt.Chart(frame).mark_bar(cornerRadiusEnd=4,color="#54bca4",size=19).encode(
        y=alt.Y("dimension:N",sort=None,title=None),x=alt.X("rate:Q",scale=alt.Scale(domain=[0,1]),axis=alt.Axis(format="%"),title="通过 / 已执行"),
        tooltip=["dimension:N","passed:Q","failed:Q","not_applicable:Q","not_verified:Q"]))


def statuses(counts,outcomes=("通过","失败")):
    labels=dict(LABELS,passed=outcomes[0],failed=outcomes[1],not_run="未执行",unknown="未知")
    colors=dict(COLORS,not_run=COLORS["not_verified"],unknown=COLORS["indeterminate"])
    frame=pd.DataFrame([{"status":label,"count":counts.get(key,0),"code":key} for key,label in labels.items()])
    return finish(alt.Chart(frame).mark_bar(cornerRadiusEnd=4,size=20).encode(
        y=alt.Y("status:N",sort=None,title=None),x=alt.X("count:Q",title="用例数"),
        color=alt.Color("code:N",scale=alt.Scale(domain=list(colors),range=list(colors.values())),legend=None),tooltip=["status:N","count:Q"]))


def latency(rows):
    return finish(alt.Chart(pd.DataFrame(rows)).mark_circle(size=45,opacity=.65,color="#849fe3").encode(
        x=alt.X("case:N",sort=None,title="实际用例",axis=alt.Axis(labels=False,ticks=False)),y=alt.Y("latency_ms:Q",title="单轮耗时 (ms)"),
        tooltip=["case:N","turn:Q","latency_ms:Q","dimension:N"]))


def mutation_distribution(rows):
    return finish(alt.Chart(pd.DataFrame(rows)).mark_bar(size=18,cornerRadiusEnd=3,color="#54bca4").encode(
        y=alt.Y("mutation:N",sort=None,title=None,axis=alt.Axis(labelLimit=210)),x=alt.X("detected:Q",title="已检出的选定组合数"),tooltip=["mutation:N","detected:Q","tested:Q"]))


def heatmap(rows):
    palette={"detected":"#438e7d","missed":"#ce6375","not_triggered":"#8878b1","not_applicable":"#67768c",
             "not_run":"#657ca2","skipped":"#596979","not_verified":"#303b50","indeterminate":"#b39353","unknown":"#826983","missing":"#a3663f"}
    frame=pd.DataFrame([{
        "mutation": row["mutation"], "case_id": row["case_id"], "c5": row.get("c5"),
        "kind": f"M{MUTATIONS.index(row['mutation']) + 1}", "result_label": STATUS_LABELS[row["status"]],
    } for row in rows], columns=["mutation","case_id","c5","kind","result_label"])
    point=alt.selection_point(name="cell",fields=["mutation","case_id"],on="click",empty=False)
    chart=alt.Chart(frame).mark_rect(cornerRadius=2,strokeWidth=2,stroke="#161c27").encode(
        x=alt.X("case_id:N",sort=None,title="宿主用例",axis=alt.Axis(labelAngle=-40)),y=alt.Y("kind:N",sort=None,title=None,axis=alt.Axis(labelOverlap=False)),
        color=alt.Color("result_label:N",scale=alt.Scale(domain=[STATUS_LABELS[key] for key in palette],range=list(palette.values())),legend=alt.Legend(title="单元格状态",orient="bottom",columns=3)),
        opacity=alt.condition(point,alt.value(1),alt.value(.8)),tooltip=[
            alt.Tooltip("kind:N",title="变异类型"),alt.Tooltip("case_id:N",title="宿主用例"),
            alt.Tooltip("result_label:N",title="判定"),alt.Tooltip("c5:N",title="C5 命中")]).add_params(point)
    return finish(chart,310)
