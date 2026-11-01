"""Session-owned experiment editor. Saving never invokes an Agent/model."""
import json
import streamlit as st
from target.agent import SYSTEM_PROMPT
from target.dev_overrides import Store,defaults,registry,TOOLS,WRITES
from target.execution_config import resolve_effective_config


def historical(session,audit):
    if not session or not audit:return
    directory=session.trace_dir/'config-events'
    files=sorted(directory.glob(str(audit.get('trace_id'))+'*.json')) if directory.is_dir() else []
    if not files:st.caption('该历史运行没有配置快照；不补造Prompt SHA或权限。');return
    with st.expander('当时实际配置（只读）'):
        for p in files:
            st.json(json.loads(p.read_text(encoding='utf-8')))


def editor(session):
    view=st.radio('配置视图',['Developer Experiment · Non-Baseline','正式 Baseline（只读）'],key='dev_profile_view')
    if view=='正式 Baseline（只读）':
        baseline=resolve_effective_config('formal-preview','baseline')
        st.caption('正式Baseline不读取Developer Override；固定Fixture/时钟/政策，仅离线。')
        st.write('Baseline ID：'+baseline.baseline_id)
        st.write('最终Prompt SHA-256：'+baseline.prompt_sha256)
        st.code(baseline.prompt,language=None)
        if st.button('核验正式103用例配置（不重算成绩）',key='dev_check_baseline'):
            from target.profile_evaluation import run_batch
            path=run_batch('baseline')
            st.success('已核验103条原始用例和Baseline身份；未运行B原始断言，不代表103条通过。')
            st.caption(str(path))
        return
    if session is None:
        if st.button('新建配置实验会话',key='dev_create_session'):
            from web.runtime import Conversation
            st.session_state['developer_debug']=Conversation('lab',execution_mode='developer_custom')
            st.rerun()
        st.info('先选择已有会话或新建实验；保存配置不会发送请求。');return
    if session.read_only:
        st.info('历史回放只读，不能恢复旧确认或修改该运行配置。');return
    store=Store();saved=store.load(session.sid,owner=session.sid)
    base=session.baseline_settings()
    settings=saved['settings'] if saved and saved['config_source']=='developer_override' else base
    revision=saved['revision'] if saved else 0
    sid=session.sid
    st.markdown('### 会话配置实验')
    st.caption('Developer Experiment · Non-Baseline · '+sid+'；只影响下一轮，不修改正式103用例配置。')
    with st.expander('Baseline Prompt（只读）'):
        st.code(SYSTEM_PROMPT,language=None)
    providers=list(registry());provider=st.selectbox('实验 Provider',providers,index=providers.index(settings['provider']),key='dev_provider_'+sid)
    options=registry()[provider]
    with st.form('dev_override_form_'+sid):
        suffix=st.text_area('Developer Prompt追加内容',value=settings['system_prompt_suffix'],key='dev_suffix_'+sid,height=140)
        st.caption('追加内容不能授予额外工具、跳过身份/用户确认或覆盖Baseline安全边界。')
        model=st.selectbox('实验 Model',options,index=options.index(settings['model']) if settings['model'] in options else 0,key='dev_model_'+sid)
        temperature=None
        if provider=='mock':st.caption('Temperature：N/A，Mock没有采样温度效果。')
        else:temperature=st.slider('Temperature（保守实验范围0—1）',0.0,1.0,float(0.2 if settings['temperature'] is None else settings['temperature']),step=0.05,key='dev_temperature_'+sid)
        st.markdown('**工具白名单 · 仅能在Baseline范围内收紧**')
        from target.tools import TOOLS as definitions
        whitelist=[]
        for name in TOOLS:
            enabled=st.checkbox(name,value=name in settings['tool_whitelist'],key='dev_tool_'+sid+'_'+name)
            if enabled:whitelist.append(name)
            definition=next(t['function'] for t in definitions if t['function']['name']==name)
            st.caption(('写操作，需要用户确认。' if name in WRITES else '查询。')+'Baseline允许；'+definition['description'])
        st.markdown('**写操作权限 · 不提供自动执行**')
        policy={n:st.selectbox('权限 '+n,['confirm','deny'],index=0 if settings['write_policy'][n]=='confirm' else 1,
                             format_func=lambda v:'需要用户确认' if v=='confirm' else '禁止',key='dev_policy_'+sid+'_'+n) for n in WRITES}
        rag=st.selectbox('政策检索方式',['keyword','hybrid','vector'],index=['keyword','hybrid','vector'].index(settings['rag_mode']),key='dev_rag_'+sid)
        embedding=st.checkbox('允许本会话Embedding联网（发送政策问题时可能产生额外费用）',key='dev_embedding_'+sid+'_'+provider)
        st.caption('保存/预览/切换模型不调用API。费用授权绑定Provider和会话，切换Provider先拒绝发送并要求重新核对。')
        save=st.form_submit_button('保存会话配置')
    if save:
        try:
            record=store.save(sid,dict(system_prompt_suffix=suffix,provider=provider,model=model,temperature=temperature,tool_whitelist=whitelist,
                write_policy=policy,rag_mode=rag,allow_embedding=embedding),owner=sid,expected_revision=revision)
            session.allow_rag_network=embedding
            st.success('已保存 revision '+str(record['revision'])+'；下一轮生效，当前运行不变。')
        except (ValueError,OSError) as e:st.error(str(e))
    def restore():
        try:
            store.save(sid,base,owner=sid,source='baseline',expected_revision=revision)
            session.allow_rag_network=False;session.config_cost_consent=None
            st.session_state['dev_suffix_'+sid]=''
            st.session_state['dev_provider_'+sid]=base['provider'];st.session_state['dev_model_'+sid]=base['model']
            st.session_state['dev_rag_'+sid]='keyword'
            for n in TOOLS:st.session_state['dev_tool_'+sid+'_'+n]=True
            for n in WRITES:st.session_state['dev_policy_'+sid+'_'+n]='confirm'
            for p in registry():st.session_state['dev_embedding_'+sid+'_'+p]=False
            st.session_state['dev_notice_'+sid]='已生成恢复Baseline的新revision，旧revision保留；下一轮生效。'
        except (ValueError,OSError) as e:st.session_state['dev_notice_'+sid]=str(e)
    st.button('恢复Baseline',key='dev_restore_'+sid,on_click=restore)
    if st.session_state.get('dev_notice_'+sid):st.info(st.session_state['dev_notice_'+sid])
    current=session.resolve_config() or resolve_effective_config(sid,'developer_custom',engine=session.engine,provider=session.live_provider if session.live else 'mock',
        model=session.live_model if session.live else None,full_tools=session.full_tools,allow_embedding=session.allow_rag_network)
    st.write('配置来源：'+current.config_source+' · revision '+str(current.override_revision))
    st.write('最终Prompt SHA-256：'+current.prompt_sha256)
    st.caption('最终可用工具：'+', '.join(current.tool_whitelist))
    st.caption('Config SHA-256：'+current.config_hash)
    with st.expander('最终有效Prompt预览（下一轮）'):st.code(current.prompt,language=None)
    st.caption('最近冻结配置：'+str(session.effective_hash or '尚无阶段六冻结配置；已有执行请核对实际运行旁证。'))
    if saved is None:st.caption('未保存Override时沿用已有会话运行路径；它不构成正式Baseline评测。保存后下一轮启用冻结配置。')
    with st.form('dev_custom_eval_'+sid):
        message=st.text_input('自定义评估消息',value='查明天上海到杭州的高铁二等座',key='dev_eval_message_'+sid)
        evaluate=st.form_submit_button('执行自定义离线评估',disabled=current.provider!='mock')
    if evaluate:
        try:
            from target.profile_evaluation import run_batch
            path=run_batch('developer_custom',session_id=sid,messages=[message],engine=session.engine)
            st.success('Developer Experiment · Non-Baseline，已生成独立报告，不计正式成绩。')
            st.caption(str(path))
        except Exception as e:st.error('实验未完成：'+type(e).__name__+'，未自动重试。')
