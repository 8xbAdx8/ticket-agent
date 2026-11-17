"""Focus only committed owned proposal cards, without confirming anything."""
import json,re
import streamlit as st
import streamlit.components.v1 as components


def pending(session):
    rail=(getattr(session,'business_view',None) or {}).get('railway') or {}
    return rail.get('pending_proposals',[])


def prepare(session):
    sid=session.sid
    order_id=st.session_state.pop('railway_created_order_'+sid,None)
    rail=(getattr(session,'business_view',None) or {}).get('railway') or {}
    order_ids={order['order_id'] for order in rail.get('orders',[])}
    if st.session_state.get('railway_order_focus_'+sid) not in order_ids:
        st.session_state.pop('railway_order_focus_'+sid,None)
    saved_order=getattr(session,'selected_order_id',None)
    if saved_order in order_ids and 'railway_order_choice_'+sid not in st.session_state:
        st.session_state['railway_order_choice_'+sid]=saved_order
        st.session_state['railway_order_widget_'+sid]=saved_order
    new_order=order_id in order_ids
    if new_order:
        session.selected_order_id=order_id
        session.save_replay()
        st.session_state['railway_order_choice_'+sid]=order_id
        st.session_state['railway_order_widget_'+sid]=order_id
        st.session_state['railway_order_focus_'+sid]=order_id
        st.session_state['user_info_open']=True
    rows=pending(session)
    if not rows:
        st.session_state.pop('railway_proposal_seen_'+sid,None)
        st.session_state.pop('railway_proposal_focus_'+sid,None)
        return
    latest=rows[-1]['proposal_id']
    key='railway_proposal_seen_'+session.sid
    if st.session_state.get(key)!=latest:
        if not new_order:
            st.session_state.pop('railway_order_focus_'+sid,None)
        st.session_state[key]=latest
        st.session_state['user_info_open']=True
        st.session_state['railway_proposal_focus_'+session.sid]=latest


def mount(session,proposal_id):
    if not re.fullmatch(r'P[a-f0-9]{32}',proposal_id):return
    _mount(session,'proposal',proposal_id,'railway_proposal_'+proposal_id)


def mount_order(session,order_id):
    if re.fullmatch(r'V39-[a-f0-9]{32}',order_id):
        _mount(session,'order',order_id,'railway_my_orders')


def _mount(session, kind, identity, target):
    config=json.dumps(dict(sid=session.sid,id=identity,target=target,kind=kind))
    components.html("""<script>(function(){const c=CONFIG,d=window.parent.document,k='ta-'+c.kind+'-focus:'+c.sid;
function focus(){const e=d.querySelector('.st-key-user_right_content .st-key-'+c.target);if(!e||!e.getClientRects().length)return false;
if(window.parent.sessionStorage.getItem(k)===c.id)return true;
let p=e.parentElement;while(p){const s=window.parent.getComputedStyle(p);if(/auto|scroll/.test(s.overflowY)&&p.scrollHeight>p.clientHeight){const r=e.getBoundingClientRect(),b=p.getBoundingClientRect();p.scrollTop+=r.top-b.top-12;break;}p=p.parentElement;}
if(!p)e.scrollIntoView({block:'nearest',behavior:'auto'});
window.parent.sessionStorage.setItem(k,c.id);return true;}
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
