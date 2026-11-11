"""Focus only committed owned proposal cards, without confirming anything."""
import json,re
import streamlit as st
import streamlit.components.v1 as components


def pending(session):
    rail=(getattr(session,'business_view',None) or {}).get('railway') or {}
    return rail.get('pending_proposals',[])


def prepare(session):
    rows=pending(session)
    if not rows:return
    latest=rows[-1]['proposal_id']
    key='railway_proposal_seen_'+session.sid
    if st.session_state.get(key)!=latest:
        st.session_state[key]=latest
        st.session_state['user_info_open']=True
        st.session_state['railway_proposal_focus_'+session.sid]=latest


def mount(session,proposal_id):
    if not re.fullmatch(r'P[a-f0-9]{32}',proposal_id):return
    config=json.dumps(dict(sid=session.sid,pid=proposal_id))
    components.html("""<script>(function(){const c=CONFIG,d=window.parent.document,k='ta-proposal-focus:'+c.sid;
function focus(){const e=d.querySelector('.st-key-railway_proposal_'+c.pid);if(!e)return false;
if(window.parent.sessionStorage.getItem(k)===c.pid)return true;
let p=e.parentElement;while(p){const s=window.parent.getComputedStyle(p);if(/auto|scroll/.test(s.overflowY)&&p.scrollHeight>p.clientHeight){const r=e.getBoundingClientRect(),b=p.getBoundingClientRect();p.scrollTop+=r.top-b.top-12;break;}p=p.parentElement;}
if(!p)e.scrollIntoView({block:'nearest',behavior:'auto'});
window.parent.sessionStorage.setItem(k,c.pid);return true;}
let n=0;const t=setInterval(()=>{if(focus()||++n>30)clearInterval(t)},100);})();</script>""".replace('CONFIG',config),height=0)


def summary(session,snapshot,proposal):
    """Only quote/order snapshots and previously returned static records."""
    quote=next((q for q in snapshot.get('quotes',[]) if q['quote_id']==proposal.get('quote_id')),None)
    if quote is None:return None
    name=quote['trip_id']
    for row in getattr(session,'railway_queries',[]):
        if row.get('tool')!='railway_query_trips' or not row.get('ok'):continue
        result=row.get('result')
        records=result.get('data',[]) if isinstance(result,dict) else []
        if not isinstance(records,list):continue
        for train in records:
            if isinstance(train,dict) and train.get('trip_id')==quote['trip_id']:
                name=train.get('trip_short_name') or train.get('train_no') or name
    return dict(train=name,trip_id=quote['trip_id'],date=quote['service_date'],origin=quote['origin_stop_id'],destination=quote['destination_stop_id'],seat=quote['seat_class'],passengers=quote['passenger_count'],total_fen=quote['total_fen'])
