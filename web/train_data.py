"""Source display and explicit session selection; never sends network requests."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import streamlit as st
import config
from target.train_source import SourceChoice
from target.train_snapshot import SYNTHETIC,read_snapshot

def selection_mode(session):
    from target.train_source import source_scope,selected
    with source_scope(getattr(session,'train_source_choice',None)):return selected().mode

def source_status(result):
    meta=(result or {}).get('data_source') or {}
    mode=meta.get('mode','fixture')
    if mode=='fixture':
        st.caption('数据来源：固定演示数据（会话日期与演示库存）；不提供真实出票服务。')
    elif mode=='snapshot':
        label='SYNTHETIC_TEST_FIXTURE · 合成测试快照，非真实12306数据' if meta.get('classification')==SYNTHETIC else '用户提供的12306数据快照（原始采集未独立核验）' if meta.get('classification') else '本地快照（不可用）'
        st.caption('数据来源：'+label)
        if meta.get('fetched_at'):
            from datetime import datetime,timezone,timedelta
            fetched=datetime.fromisoformat(meta['fetched_at']).astimezone(timezone(timedelta(hours=8)))
            st.caption('采集时间（北京时间）：'+fetched.strftime('%Y-%m-%d %H:%M:%S'))
        if meta.get('coverage'):st.caption('声明覆盖：'+meta['coverage']['start_date']+' 至 '+meta['coverage']['end_date'])
        if meta.get('observed_dates'):st.caption('实际有记录日期：'+'、'.join(meta['observed_dates']))
        if meta.get('sha256'):st.caption('数据SHA256：'+meta['sha256'])
        st.caption('历史快照，非实时余票保证；查询不会真实锁座、出票或扣款。')
    else:st.caption('实时数据源未授权、未接入；未发出任何实时请求。')
    status=meta.get('status')
    if status:
        text=status+' · '+meta.get('message','')
        if 'error' in (result or {}):st.warning(text)
        else:st.info(text)
    st.caption('订单、支付、退款与改签均为演示操作；不会向12306提交订单、真实锁座或扣款。')

def snapshots():
    root=Path(os.getenv('TICKET_SNAPSHOT_DIR',str(config.BASE_DIR/'data/real')))
    if not root.is_dir() or root.is_symlink():return []
    found=[]
    for path in sorted(root.glob('snapshot-*.json')):
        if path.name.endswith('.receipt.json') or path.is_symlink():continue
        try:
            if path.stat().st_size>8_000_000:continue
            h=hashlib.sha256(path.read_bytes()).hexdigest();data,_=read_snapshot(path,h)
            found.append((path,h,data))
        except (ValueError,OSError):continue
    return found

def settings(session):
    with st.expander('车次数据来源（独立于模型配置）',expanded=True):
        if session is None:st.info('先创建或选择一个会话。');return
        if session.read_only or session.execution_mode=='baseline' or os.getenv('TICKET_TEST_MODE')=='1' or st.session_state.get('dev_profile_view')=='正式 Baseline（只读）':
            st.caption('正式Baseline/Test固定Fixture；历史回放只读，不读取快照或恢复旧授权。');return
        names={'固定演示数据':'fixture','本地快照':'snapshot','实时来源（未授权）':'live'}
        current=getattr(session.train_source_choice,'mode','fixture')
        mode=st.selectbox('车次数据来源',list(names),index=list(names.values()).index(current),key='train_source_mode_'+session.sid)
        choices=snapshots() if names[mode]=='snapshot' else []
        pick=None
        if choices:
            pick=st.selectbox('已导入快照',range(len(choices)),format_func=lambda i:choices[i][2]['snapshot_id']+' · '+choices[i][2]['classification'],key='train_snapshot_'+session.sid)
        elif names[mode]=='snapshot':st.info('没有已验证的导入快照；选择后会明确返回SNAPSHOT_MISSING，不回落演示数据。')
        if names[mode]=='live':st.warning('LIVE_SOURCE_BLOCKED_PENDING_AUTHORIZATION：本阶段没有网络适配器。')
        st.caption('切换不会调用模型或网络。快照模式禁止新候补、锁座、建单和改签；请切回演示数据并重新查询后演示购票。')
        if st.button('保存车次数据来源',key='train_source_save_'+session.sid):
            choice=SourceChoice(names[mode]) if pick is None else SourceChoice('snapshot',str(choices[pick][0].resolve()),choices[pick][1])
            try:
                session.set_train_source(choice)
                st.success('车次数据来源已保存；下一轮生效，未发送请求。')
            except ValueError as e:st.warning(str(e))
        if session.last_train_query:source_status(session.last_train_query)
