"""Trusted execution context. Never derived from model tool arguments."""
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass,field,asdict
import hashlib,json,os

CURRENT=ContextVar('ticket_v39_context',default=None)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class Context:
    session_id:str
    owner_phone:str
    scenario_id:str
    enabled:bool=False
    execution_mode:str='developer_custom'
    config_hash:str=''
    config_revision:int=0
    provider:str='mock'
    baseline_id:str='ticket-agent-v37-baseline-1'
    write_policy:tuple=field(default_factory=lambda:tuple((n,'confirm') for n in ('CREATE_ORDER','PAY','CANCEL','REFUND','CHANGE')))
    tool_whitelist:tuple=()

    def require(self,action=None):
        if self.execution_mode=='baseline' or not self.enabled or os.getenv('RAILWAY_SIMULATION_ENABLED','0')!='1' or not all((self.session_id,self.owner_phone,self.scenario_id)):
            raise ValueError('V39_CONTEXT_REQUIRED')
        from target.execution_config import CURRENT as EFFECTIVE
        effective=EFFECTIVE.get()
        if effective and (effective.execution_mode=='baseline' or effective.config_hash!=self.config_hash or effective.override_revision!=self.config_revision):
            raise ValueError('V39_CONFIG_MISMATCH')
        if effective and action:
            required={'CREATE_ORDER':('lock_seat','create_order'),'PAY':('pay_order',),'CANCEL':('cancel_order',),'REFUND':('cancel_order',),'CHANGE':('lock_seat','create_order','cancel_order')}[action]
            if any(n not in effective.tool_whitelist or dict(effective.write_policy).get(n)!='confirm' for n in required):
                raise ValueError('WRITE_POLICY_DENIED')
        if action and dict(self.write_policy).get(action)!='confirm':raise ValueError('WRITE_POLICY_DENIED')

    def snapshot(self):
        return dict(execution_mode=self.execution_mode,config_hash=self.config_hash,config_revision=self.config_revision,
                    write_policy_hash=digest(self.write_policy),feature_flag=str(int(self.enabled)),baseline_id=self.baseline_id,
                    provider=self.provider,tool_whitelist_hash=digest(self.tool_whitelist))

@contextmanager
def scope(context):
    token=CURRENT.set(context)
    try:yield
    finally:CURRENT.reset(token)
