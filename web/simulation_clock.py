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
    runtime=(config.BASE_DIR/'artifacts/runtime').resolve()
    clock_root=Path(os.getenv('TICKET_SIM_CLOCK_ROOT') or runtime/'v310-simulation-clocks').resolve()
    if clock_root==runtime or not clock_root.is_relative_to(runtime):
        raise ValueError('INVALID_SIMULATION_CLOCK_ROOT')
    root=clock_root/uuid.uuid4().hex
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
        st.caption('当前沿用标准时钟场景，旧订单时间不迁移。')
        if st.button('新会话使用独立会话时钟',key='clock_enable_'+session.sid):
            st.session_state['railway_demo_clock_requested']=True
            st.info('请点击“新会话”；旧场景和订单保留，新场景将使用独立会话时钟。')
        return
