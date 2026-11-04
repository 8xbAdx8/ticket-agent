from types import SimpleNamespace
import pytest
from langchain_core.messages import AIMessage,HumanMessage
from langchain.agents.middleware.types import ModelResponse
from target.langchain_agent import ContractMiddleware,TurnContext
from target.trace import Trace
from target.deepseek_runtime import DeepSeekError


class Request:
    def __init__(self,context):
        self.runtime=SimpleNamespace(context=context)
        self.messages=[HumanMessage('预算离线验证')];self.system_message=None
    def override(self,**kw):
        new=Request(self.runtime.context)
        for k,v in kw.items():setattr(new,k,v)
        return new


def context():
    c=TurnContext(Trace('budget-test'),'测试',6)
    c.deepseek_settings=SimpleNamespace(turn_token_budget=512,max_output_tokens=32)
    c.fault_run=SimpleNamespace(model_requests=[])
    return c


def test_usage_counts_once_per_request_budget_not_reset_or_inherited():
    c=context();requests=[]
    def handler(r):
        requests.append(r)
        return ModelResponse(result=[AIMessage('完成',usage_metadata=dict(input_tokens=200,output_tokens=10,total_tokens=210))])
    middleware=ContractMiddleware()
    for _ in range(3):middleware.wrap_model_call(Request(c),handler)
    assert c.trace.tokens==dict(prompt=600,completion=30) and len(requests)==3
    with pytest.raises(DeepSeekError,match='observed_token_budget_exhausted'):
        middleware.wrap_model_call(Request(c),handler)
    assert c.trace.tokens==dict(prompt=600,completion=30) and len(requests)==3
    fresh=context();middleware.wrap_model_call(Request(fresh),handler)
    assert fresh.trace.tokens==dict(prompt=200,completion=10)
