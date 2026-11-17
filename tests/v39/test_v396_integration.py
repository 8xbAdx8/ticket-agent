import pytest
from tests.v39.test_v394_defaults import session


class PagingModel:
    name='scripted_mock'
    last_usage={'prompt':200,'completion':10}
    def __init__(self):self.calls=0
    def chat(self,messages,tools):
        import uuid
        self.calls+=1
        if self.calls>3:raise AssertionError('complete facts must finish locally, no fourth model request')
        args=dict(service_date='2026-11-05',origin_stop_id='AOH',destination_stop_id='HGH',limit=50)
        if self.calls>1:args['cursor']=str((self.calls-1)*50)
        return dict(role='assistant',content='',tool_calls=[dict(id=uuid.uuid4().hex,name='railway_query_trips',arguments=args)])


@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_real_gtfs_three_pages_finish_without_fourth_model_request(session,engine):
    from web.railway_defaults import prepare
    from target.v39.context import scope
    from target.v39.registry import service_scope
    from target.execution_config import scope as effective_scope
    from target.agent import Agent
    from target.langchain_model import LangChainMockModel
    service,ctx,effective=prepare(session);model=PagingModel()
    with scope(ctx),service_scope(service),effective_scope(effective):
        agent=Agent(provider=model,engine=engine,effective_config=effective,model=LangChainMockModel(decision_provider=model) if engine=='langchain' else None)
        result=agent.chat(session.sid,'查询2026-11-05上海虹桥到杭州东的车次，哪趟运行时间最短？',save_trace=False)
    assert model.calls==3
    assert result['tool_sequence']==['railway_query_trips']*3
    assert all(c['ok'] for s in result['steps'] for c in s['calls'])
    assert '109班' in result['reply'] and '45分钟' in result['reply'] and len(result)==10
