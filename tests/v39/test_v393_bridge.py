"""V3.9.3 regression: bridge keeps the effective old-tool permissions intact."""
from dataclasses import replace
from types import SimpleNamespace
from tests.v39.test_service import sim
from target.v39.context import scope
from target.v39.registry import service_scope,definitions,NAMES,dispatch
from target.execution_config import resolve_effective_config,scope as effective_scope
from target.tools import TOOLS,TOOL_NAMES

def prepared(sim,monkeypatch,remove=()):
 from web import v39_bridge as bridge
 s,ctx=sim
 effective=resolve_effective_config(ctx.session_id,'developer_custom')
 effective=replace(effective,tool_whitelist=tuple(n for n in effective.tool_whitelist if n not in remove))
 session=SimpleNamespace(sid=ctx.session_id,execution_mode='developer_custom',full_tools=True,resolve_config=lambda:effective)
 monkeypatch.setattr(bridge,'_service',lambda path:s)
 return bridge.prepare(session)

def test_bridge_preserves_all_authorized_old_and_new_tools(sim,monkeypatch):
 s,ctx,effective=prepared(sim,monkeypatch)
 with scope(ctx),service_scope(s),effective_scope(effective):
  names=[t['function']['name'] for t in definitions(TOOLS)]
  assert set(names)==set(TOOL_NAMES)|set(NAMES)
  assert len(names)==19

def test_bridge_old_policy_query_reaches_original_dispatch(sim,monkeypatch):
 s,ctx,effective=prepared(sim,monkeypatch)
 from target import tools
 calls=[]
 monkeypatch.setattr(tools,'dispatch',lambda n,a:(calls.append((n,a)) or {'hits':[]},True,0))
 with scope(ctx),service_scope(s),effective_scope(effective):
  result,ok,_=dispatch('search_policy',{'query':'行李'})
 assert ok and calls==[('search_policy',{'query':'行李'})]

def test_bridge_does_not_restore_revoked_query_permission(sim,monkeypatch):
 s,ctx,effective=prepared(sim,monkeypatch,remove=('query_tickets',))
 with scope(ctx),service_scope(s),effective_scope(effective):
  names=[t['function']['name'] for t in definitions(TOOLS)]
  assert 'query_tickets' not in names
  assert not set(NAMES[:5])&set(names)
