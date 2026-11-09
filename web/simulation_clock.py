"""Trusted clock binding and explicit controls; no model can advance time."""
from datetime import datetime
from pathlib import Path
import os,uuid
import config
from target.v39.simulation_clock import SimulationClock,dataset_anchor


def binding(session):
    ref=getattr(session,'railway_state_reference',None)
    if ref:
        clock=SimulationClock(ref['clock_path'],session.sid,ref['clock_id']) if ref.get('clock_path') else None
        return Path(ref['path']),clock
    mode=os.getenv('RAILWAY_SIM_CLOCK_MODE','demo')
    if mode not in ('real','demo'):raise ValueError('INVALID_SIMULATION_CLOCK_MODE')
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx(suppress_warning=True) is not None:
        import streamlit as st
        if st.session_state.get('railway_demo_clock_requested'):mode='demo'
    if mode!='demo':return None,None
    from target.v39.static import RailwayStatic,VERSION
    root=config.BASE_DIR/'artifacts/runtime/v310-simulation-clocks'/uuid.uuid4().hex
    database=root/'simulation.sqlite';clock_path=root/'clock.sqlite'
    # Keep the existing explicit-path contract for a NEW isolated test/custom
    # database. Never attach virtual time to an existing business database or
    # to the launcher's shared legacy daily database.
    explicit=os.getenv('RAILWAY_SIM_DB_PATH','').strip()
    if explicit:
        candidate=Path(explicit).resolve();sidecar=candidate.with_name(candidate.stem+'-clock.sqlite')
        from target.v39.store import ROOT,safe_path
        if candidate.is_relative_to(ROOT/'data/v39'):raise ValueError('PRODUCT_DATABASE_CLOCK_BLOCKED')
        if not candidate.exists() and not sidecar.exists() and not candidate.is_relative_to(ROOT/'artifacts/runtime/v392-launcher'):
            database=safe_path(candidate);clock_path=sidecar
    clock=SimulationClock.create(clock_path,session.sid,dataset_anchor(RailwayStatic()),VERSION)
    ref=dict(path=str(database),scenario_id='railway-demo',clock_path=str(clock.path),clock_id=clock.clock_id)
    session.railway_state_reference=ref
    return Path(ref['path']),clock


def controls(session,service):
    import streamlit as st
    if not getattr(service.clock,'simulation',False):
        st.caption('当前为原真实时钟场景，旧订单时间不迁移。')
        if st.button('新会话使用独立模拟时钟',key='clock_enable_'+session.sid):
            st.session_state['railway_demo_clock_requested']=True
            st.info('请点击“新会话”；旧场景和订单保留，新场景将使用独立模拟时钟。')
        return
    snap=service.clock.snapshot()
    with st.expander('模拟时间控制（暂停中）',expanded=False):
        st.write('当前模拟时间：'+snap['now'])
        st.caption('暂停时提案和锁座不会因现实等待而过期。推进时间会触发原有超时、发车和P01规则；不能倒拨。跨日期后须重新生成确认卡。新会话创建新的独立场景，不重置旧订单。Trace、API统计和进程租约仍用真实时间。')
        from web.interaction import busy
        amount=st.selectbox('推进模拟时间',[60,600,900,3600,86400],format_func=lambda n:{60:'1分钟',600:'10分钟',900:'15分钟',3600:'1小时',86400:'1天'}[n],key='clock_step_'+session.sid)
        if st.button('推进模拟时间',key='clock_advance_'+session.sid,disabled=session.read_only or busy(session)):
            from web.runtime import CALL_LOCK
            try:
                with CALL_LOCK:
                    service.clock.advance(amount,revision=snap['revision'])
                    from target.v39.context import scope
                    from target.execution_config import scope as effective_scope
                    with effective_scope(session._v39_effective),scope(session._v39_context):service.expire(session._v39_context)
                st.rerun()
            except ValueError as exc:st.error('模拟时间未完成处理：'+str(exc)+'；请刷新核对，未自动重试。')
