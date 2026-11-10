"""Natural-language test runner over the ORIGINAL Conversation/Agent, not DSL replay."""
from contextlib import contextmanager, ExitStack, closing
from pathlib import Path
from unittest.mock import patch
import copy
import json
import os
import uuid
from urllib.parse import urlsplit

from target.scenario_business_oracle import snapshot, invariants, receipt_proof, decline_proof, digest, reply_claims
from target.scenario_live_budget import LiveBatch, ROOT


def save(path, value):
    from target.diagnostics import sanitize
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:
        json.dump(sanitize(value),stream,ensure_ascii=False,indent=2)


def deny_network(*args,**kwargs):
    raise RuntimeError('V311_OFFLINE_TOOL_NETWORK_BLOCKED')


class AgentRun:
    """Retained in the owner process across turns and trusted UI decisions."""
    def __init__(self,batch_root,provider,*,transport=None,scenario='default',batch=None):
        if provider not in ('deepseek','bailian') or scenario not in ('default','sold_out','payment_fail'):
            raise ValueError('INVALID_TEST_CONFIGURATION')
        self.batch=batch if batch is not None else LiveBatch(batch_root)
        # No automatic authorization or recreation of a lost budget.
        with closing(self.batch.connect()) as connection:
            if not connection.execute('SELECT * FROM v311_limits WHERE id=1').fetchone():
                raise ValueError('V311_AUTHORIZED_BUDGET_REQUIRED')
        self.id=uuid.uuid4().hex;self.provider=provider;self.transport=transport
        self.mode='sdk_stub_agent' if transport is not None else 'live_agent'
        self.root=self.batch.root/'cases'/self.id;self.root.mkdir(parents=True,exist_ok=False)
        self.rows=[];self.halted=False
        from web.runtime import Conversation
        self.session=Conversation('user',engine='langchain',live=True,live_provider=provider,full_tools=True,root=self.root/'conversation')
        self.session._unified_interaction=True
        self.session.config_cost_consent=(self.session.sid,provider,0)
        self.allowed_actions={'CREATE_ORDER','PAY','REFUND','CHANGE','CANCEL'}
        self.allowed_people={'合成甲','合成乙','合成丙'}
        with self.environment():
            from target.v39.service import Service
            from web.v39_bridge import prepare
            original=Service.scenario
            def setup(instance,identity,dataset,**kwargs):
                return original(instance,identity,dataset,name=scenario)
            with patch.object(Service,'scenario',setup):
                self.service,self.context,self.effective=prepare(self.session)
        self.initial=self.read()
        save(self.root/'initial.json',self.initial)
        self.persist()

    @contextmanager
    def environment(self):
        from web.runtime import CALL_LOCK
        env=dict(RAILWAY_SIMULATION_ENABLED='1',RAILWAY_SIM_CLOCK_MODE='demo',
                 RAILWAY_SIM_DB_PATH=str(self.root/'simulation.sqlite'),
                 TICKET_TEST_MODE='1',TICKET_DATA_MODE='fixture',TICKET_RAILWAY_QUERY_ENABLED='0',
                 TICKET_ACCEPTANCE_BATCH=str(self.batch.path),TICKET_API_USAGE_DIR=str(self.batch.root/'api-usage'),
                 TICKET_DISABLE_LOCAL_SECRETS='1',TICKET_WEB_OFFLINE_ONLY='0',
                 LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',RAG_ALLOW_NETWORK='0',
                 DEEPSEEK_MAX_OUTPUT_TOKENS='2048',DASHSCOPE_MAX_OUTPUT_TOKENS='2048')
        from target.api_config import model_config
        cfg=model_config(self.provider);host=urlsplit(cfg['base_url']).hostname
        if not host:raise ValueError('PROVIDER_NOT_CONFIGURED')
        with CALL_LOCK,patch.dict(os.environ,env),ExitStack() as stack:
            # Use the guarded subclass for the original accounting hook too.
            from target import acceptance_budget
            def active_batch():
                if Path(os.environ['TICKET_ACCEPTANCE_BATCH']).resolve()!=self.batch.path:
                    raise ValueError('V311_BATCH_PATH_CHANGED')
                return self.batch
            stack.enter_context(patch.object(acceptance_budget,'active',active_batch))
            import httpx
            original_send=httpx.Client.send
            def guarded(client,request,*args,**kwargs):
                if request.url.scheme!='https' or request.url.host!=host:
                    raise ValueError('V311_ONLY_MODEL_ENDPOINT_ALLOWED')
                return original_send(client,request,*args,**kwargs)
            stack.enter_context(patch.object(httpx.Client,'send',guarded))
            # A model request can reach only the configured guarded Provider.
            # Tools, including RAG/legacy fallbacks, must stay offline.
            from target.v39 import registry
            original_dispatch=registry.dispatch
            def tool_dispatch(*args,**kwargs):
                with patch('socket.socket.connect',deny_network),patch('socket.socket.connect_ex',deny_network),patch('socket.create_connection',deny_network),patch('socket.getaddrinfo',deny_network):
                    return original_dispatch(*args,**kwargs)
            stack.enter_context(patch.object(registry,'dispatch',tool_dispatch))
            if self.transport is not None:
                stack.enter_context(patch('socket.socket.connect',deny_network))
                stack.enter_context(patch('socket.create_connection',deny_network))
                from target import deepseek_runtime,bailian_runtime
                runtime=bailian_runtime if self.provider=='bailian' else deepseek_runtime
                original_factory=runtime.make_model
                stack.enter_context(patch.object(runtime,'make_model',lambda settings,**kwargs:original_factory(settings,transport=self.transport,**kwargs)))
            yield

    def read(self):
        return snapshot(self.service.store.path)

    def persist(self):
        # Append immutable revision files. History never overwritten.
        save(self.root/f'run-{len(self.rows):03d}.json',dict(schema='ticket-v311-agent-run/1',execution_id=self.id,
             mode=self.mode,provider=self.provider,session_id=self.session.sid,
             database=str(self.service.store.path),rows=self.rows,halted=self.halted))

    def pending(self):
        return [p for p in self.read()['tables']['proposals'] if p['state']=='PENDING' and p['expires_at']>self.service.stamp()]

    def _record(self,kind,before,output,error=None,*,extra_checks=(),task_checks=None,**fields):
        after=self.read();checks=invariants(after)+list(extra_checks)
        row=dict(index=len(self.rows),kind=kind,before=before,after=after,result=copy.deepcopy(output),error=error,checks=checks,**fields)
        task_checks=list(task_checks) if task_checks is not None else None
        row['task_checks']=task_checks
        row['invariant_status']='PASS' if all(c['passed'] for c in checks) else 'FAIL'
        row['task_status']='NOT_SCORED' if not task_checks else 'PASS' if all(c['passed'] for c in task_checks) else 'FAIL'
        row['passed']=not error and row['invariant_status']=='PASS' and row['task_status']=='PASS'
        if not all(c['passed'] for c in checks):self.halted=True
        self.rows.append(row);self.persist()
        return row

    def turn(self,message,*,request_id=None,expectations=None):
        if self.halted:raise ValueError('V311_RUN_HALTED')
        if not isinstance(message,str) or not message.strip():raise ValueError('USER_MESSAGE_REQUIRED')
        expectations=self.validate_expectations(expectations)
        before=self.read();output={};error=None
        request_id=request_id or uuid.uuid4().hex
        replay=request_id in self.session.receipts
        prior_requests={r['request_id'] for r in self.batch.snapshot()['requests']}
        audit_count=len(self.session.audits)
        with self.environment():
            try:output=self.session.send(message,request_id,defer_followups=True)
            except Exception as exc:error=getattr(exc,'category',type(exc).__name__)
        audit=self.session.audits[-1] if len(self.session.audits)>audit_count and not replay else {}
        events=copy.deepcopy(audit.get('framework_events',[]))
        raw=next((e.get('text') for e in reversed(events) if e.get('event')=='model_final'),None)
        executed=[] if replay else [e for e in events if e.get('event')=='tool_end' and e.get('executed') is True]
        requests=[r for r in self.batch.snapshot()['requests'] if r['request_id'] not in prior_requests]
        claims=reply_claims(raw,self.read())
        tasks=self.task_checks(expectations,executed,raw,before,self.read(),replay)
        return self._record('agent_turn',before,output,error,input=message,request_id=request_id,
                extra_checks=claims['checks'],task_checks=tasks,expectations=expectations,reply_assessment=claims,
                trace_id=audit.get('trace_id'),prompt_sha256=getattr(self.session,'_v39_effective',self.effective).prompt_sha256,
                model=self.session.live_model or (output or {}).get('model'),original_model_reply=raw,
                events=[] if replay else events,executed_tools=executed,model_called=bool(requests),
                http_requests=requests,request_replayed=replay)

    @staticmethod
    def validate_expectations(spec):
        if spec is None:return None
        from target.v39.registry import NAMES
        allowed={'required_tools','forbidden_tools','args','reply_contains','unchanged','replay'}
        from target.scenario_business_oracle import TABLES
        if not isinstance(spec,dict) or not spec or set(spec)-allowed:raise ValueError('INVALID_TASK_EXPECTATIONS')
        for field,values in (('required_tools',NAMES),('forbidden_tools',NAMES),('unchanged',TABLES)):
            if field in spec and (not isinstance(spec[field],list) or any(v not in values for v in spec[field])):raise ValueError('INVALID_TASK_EXPECTATIONS')
        if 'args' in spec and (not isinstance(spec['args'],dict) or any(k not in NAMES or not isinstance(v,dict) for k,v in spec['args'].items())):raise ValueError('INVALID_TASK_EXPECTATIONS')
        if 'reply_contains' in spec and (not isinstance(spec['reply_contains'],list) or any(not isinstance(v,str) or not v for v in spec['reply_contains'])):raise ValueError('INVALID_TASK_EXPECTATIONS')
        if 'replay' in spec and type(spec['replay']) is not bool:raise ValueError('INVALID_TASK_EXPECTATIONS')
        if not any(spec.values()):raise ValueError('INVALID_TASK_EXPECTATIONS')
        return copy.deepcopy(spec)

    @staticmethod
    def task_checks(spec,executed,reply,before,after,replay):
        """Caller freezes objective expectations BEFORE sending; never infer goals
        from the actual model response. Small declarative grammar, no eval/SQL."""
        if not spec:return None
        spec=AgentRun.validate_expectations(spec)
        checks=[]
        names=[e['tool'] for e in executed]
        for tool in spec.get('required_tools',[]):
            wanted=spec.get('args',{}).get(tool,{})
            checks.append(dict(rule='required_tool',tool=tool,passed=any(e['tool']==tool and e.get('ok') is True and all(e.get('args',{}).get(k)==v for k,v in wanted.items()) for e in executed)))
        for tool in spec.get('forbidden_tools',[]):
            checks.append(dict(rule='forbidden_tool',tool=tool,passed=tool not in names))
        for tool,wanted in spec.get('args',{}).items():
            checks.append(dict(rule='tool_args',tool=tool,passed=any(e['tool']==tool and e.get('ok') is True and all(e.get('args',{}).get(k)==v for k,v in wanted.items()) for e in executed)))
        for value in spec.get('reply_contains',[]):
            checks.append(dict(rule='reply_contains',value=value,passed=value in (reply or '')))
        for table in spec.get('unchanged',[]):
            if table not in before['tables']:raise ValueError('INVALID_TASK_TABLE')
            checks.append(dict(rule='unchanged',table=table,passed=before['tables'][table]==after['tables'][table]))
        if 'replay' in spec:checks.append(dict(rule='request_replay',passed=replay==spec['replay'] and (not replay or before['tables']==after['tables'])))
        return checks or None

    def decision_preview(self,proposal_id):
        proposal=next((p for p in self.read()['tables']['proposals'] if p['proposal_id']==proposal_id and (p['state']=='CONFIRMED' or p['state']=='PENDING' and p['expires_at']>self.service.stamp())),None)
        if not proposal:raise ValueError('CURRENT_OWNED_PROPOSAL_REQUIRED')
        payload=json.loads(proposal['payload_json'])
        return dict(proposal_id=proposal_id,action=proposal['action'],payload=payload,payload_sha256=digest(payload))

    def confirm(self,preview,approved,*,actor,expected_outcome=None):
        if self.halted:raise ValueError('V311_RUN_HALTED')
        if actor!='test_user' or type(approved) is not bool:raise ValueError('TRUSTED_TEST_USER_REQUIRED')
        current=self.decision_preview(preview['proposal_id'])
        if current!=preview:raise ValueError('STALE_CONFIRMATION_PREVIEW')
        if current['action'] not in self.allowed_actions:raise ValueError('ACTION_OUTSIDE_AUTHORIZATION')
        payload=current['payload']
        if current['action']=='CREATE_ORDER' and (not set(payload['passengers'])<=self.allowed_people or payload['contact']!=self.context.owner_phone):
            raise ValueError('SYNTHETIC_PERSON_REQUIRED')
        before=self.read();result={};error=None
        with self.environment():
            try:result=self.session.confirm_railway_proposal(current['proposal_id'],approved)
            except Exception as exc:error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        after=self.read()
        proof=receipt_proof(after,current['proposal_id'],result,before=before) if approved else decline_proof(before,after,current['proposal_id'])
        outcome='FAILED' if error or result.get('error') else 'SUCCEEDED' if approved else 'DECLINED'
        expected_outcome=expected_outcome or ('SUCCEEDED' if approved else 'DECLINED')
        row=self._record('trusted_user_decision',before,result,error,actor=actor,approved=approved,
                         extra_checks=[dict(rule='matching_committed_receipt',passed=proof),dict(rule='expected_business_outcome',passed=outcome==expected_outcome)],
                         task_checks=[dict(rule='committed_expected_operation',passed=proof and outcome==expected_outcome)],
                         business_outcome=outcome,expected_business_outcome=expected_outcome,
                         proposal=current,model_called=False,database_receipt_verified=proof)
        # Persist additional assertion as a separate immutable evidence item.
        save(self.root/f'decision-{row["index"]:03d}.json',row)
        return row

    def advance(self,seconds):
        if type(seconds) is not int or not 1<=seconds<=2592000:raise ValueError('INVALID_CLOCK_ADVANCE')
        before=self.read()
        from target.execution_config import scope as effective_scope
        from target.v39.context import scope
        with self.environment(),effective_scope(self.effective),scope(self.context):
            current=self.service.clock.snapshot()
            self.service.clock.advance(seconds,revision=current['revision'])
            self.service.expire(self.context)
        return self._record('trusted_clock_advance',before,dict(seconds=seconds),task_checks=[dict(rule='clock_advanced',passed=self.service.clock.snapshot()['revision']>current['revision'])],model_called=False)

    def reconcile(self,expected_state_sha256,*,actor):
        """Explicit readback before a new user decision; never retries a transaction."""
        view=self.read()
        if actor!='test_user' or view['state_sha256']!=expected_state_sha256:
            raise ValueError('CURRENT_STATE_REVIEW_REQUIRED')
        checks=invariants(view)
        if not all(c['passed'] for c in checks):raise ValueError('V311_INVARIANTS_STILL_FAILED')
        self.halted=False
        return self._record('trusted_reconciliation',view,dict(status='READBACK_ONLY'),task_checks=[dict(rule='reviewed_state_matches',passed=True)],actor=actor,model_called=False)
