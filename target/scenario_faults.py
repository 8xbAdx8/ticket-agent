"""Trusted reversible test hooks, never exposed as model tools or candidate args."""
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import uuid
from target.scenario_live_agent import save

KINDS=('model_timeout','model_malformed','tool_timeout','tool_error','database_failure',
       'partial_business_failure','duplicate_request','mid_disconnect','user_decline')


@contextmanager
def inject(run,kind):
    if kind not in KINDS:raise ValueError('UNKNOWN_V311_FAULT')
    events=[]
    def seen(stage):events.append(dict(stage=stage,kind=kind))
    with ExitStack() as stack:
        if kind in ('model_timeout','model_malformed'):
            def model(*args,**kwargs):
                seen('model_boundary')
                if kind=='model_timeout':raise TimeoutError('V311_MODEL_TIMEOUT')
                raise ValueError('V311_MALFORMED_MODEL_RESPONSE')
            if not run.session.agent or not run.session.agent.langchain_engine:
                raise ValueError('INITIALIZED_AGENT_REQUIRED_FOR_MODEL_FAULT')
            stack.enter_context(patch.object(type(run.session.agent.langchain_engine.model),'_generate',model))
        elif kind in ('tool_timeout','tool_error'):
            def inventory(*args,**kwargs):
                seen('inventory_tool')
                if kind=='tool_timeout':raise TimeoutError('V311_TOOL_TIMEOUT')
                return dict(error='V311_INJECTED_TOOL_ERROR')
            stack.enter_context(patch.object(run.service,'inventory',inventory))
        elif kind=='database_failure':
            original=run.service._create
            def create(*args,**kwargs):
                value=original(*args,**kwargs);seen('before_transaction_commit')
                raise ValueError('V311_INJECTED_DATABASE_FAILURE')
            stack.enter_context(patch.object(run.service,'_create',create))
        elif kind=='partial_business_failure':
            original=run.service._fault
            def fault(connection,ctx,name):
                if name in ('refund_failures_remaining','change_money_failures_remaining'):
                    seen(name);return True
                return original(connection,ctx,name)
            stack.enter_context(patch.object(run.service,'_fault',fault))
        else:
            # These faults are user/driver actions, not hidden backend changes.
            seen('explicit_driver_action_required')
        try:yield events
        finally:
            save(run.root/('fault-'+kind+'-'+uuid.uuid4().hex+'.json'),dict(kind=kind,observed=events,scope='trusted_test_hook',restored_on_exit=True,claims_live_model_participation=False,model_fault_scope='SDK model method exception; not an HTTP parser/transport test'))
