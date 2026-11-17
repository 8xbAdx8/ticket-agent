"""Local-only railway simulation. Queries and model proposals cannot confirm."""
from datetime import datetime,timedelta,timezone
import hashlib,json,secrets,uuid
from target.v39.context import digest
from target.v39.store import integer
from target.v39.pricing import price,select_rule
from target.v39.policy import Policy
from target.v39.lifecycle import Lifecycle
from target.v39.passengers import has_placeholders,require_names


def insert(c,table,values):
    c.execute('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',tuple(values.values()))


class Service(Lifecycle):
    _insert=staticmethod(insert)
    def __init__(self,store,static,*,clock=None,policy=None,worker='confirmation'):
        self.store=store;self.static=static;self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.policy=policy or Policy();self.worker=worker;self.epoch=None;self._secrets={}

    def now(self):
        value=self.clock()
        if value.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
        return value.astimezone(timezone.utc)

    def stamp(self):return self.now().isoformat()

    def infrastructure_now(self):
        # Paused business time must not freeze or extend a real worker lease.
        return datetime.now(timezone.utc) if getattr(self.clock,'simulation',False) else self.now()

    def start(self):
        self.store.initialize()
        self.epoch=self.store.acquire_worker(self.worker,now=self.infrastructure_now())

    def scenario(self,scenario_id,dataset_version,*,name='default'):
        capacities={'default':(20,8,3),'tight':(3,2,1),'sufficient':(100,50,20),'sold_out':(0,0,0),'payment_fail':(20,8,3)}
        if name not in capacities:raise ValueError('INVALID_SCENARIO')
        with self.store.transaction() as c:
            existing=c.execute('SELECT * FROM v39_scenarios WHERE scenario_id=?',(scenario_id,)).fetchone()
            if existing:
                if existing['dataset_version']!=dataset_version:raise ValueError('DATASET_IDENTITY_MISMATCH')
                return
            insert(c,'v39_scenarios',dict(scenario_id=scenario_id,name=name,seed=20261102,dataset_version=dataset_version,status='ACTIVE',config_json=json.dumps(dict(capacity=dict(zip(('SECOND','FIRST','BUSINESS'),capacities[name])))),created_at=self.stamp()))
            for seat,bp in [('SECOND',10000),('FIRST',15000),('BUSINESS',30000)]:
                insert(c,'v39_price_rules',dict(rule_id=scenario_id+'-'+seat,version=1,scenario_id=scenario_id,dataset_version=dataset_version,trip_id=None,seat_class=seat,base_fen_per_segment=1000,seat_multiplier_bp=bp,fixed_fee_fen=0,priority=0,valid_from=self.stamp(),valid_until=None,status='ACTIVE'))

    def _scope(self,c,ctx):
        ctx.require()
        row=c.execute("SELECT * FROM v39_scenarios WHERE scenario_id=? AND status='ACTIVE'",(ctx.scenario_id,)).fetchone()
        if not row:raise ValueError('SCENARIO_NOT_ACTIVE')
        return row

    def _interval(self,c,ctx,args):
        s=self._scope(c,ctx)
        seat=args['seat_class']
        if seat not in ('SECOND','FIRST','BUSINESS'):raise ValueError('INVALID_SEAT_CLASS')
        data=self.static.interval(args['trip_id'],args['service_date'],args['origin_stop_id'],args['destination_stop_id'])
        if data['dataset_version']!=s['dataset_version']:raise ValueError('DATASET_IDENTITY_MISMATCH')
        return s,data

    def _materialize(self,c,ctx,args):
        scenario,data=self._interval(c,ctx,args)
        cap=json.loads(scenario['config_json']).get('capacity',{}).get(args['seat_class'])
        if cap is None:raise ValueError('INVENTORY_NOT_CONFIGURED')
        integer(cap,'capacity')
        for i in data['segments']:
            a,b=data['stops'][i:i+2]
            c.execute('INSERT OR IGNORE INTO v39_inventory_segments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (ctx.scenario_id,data['dataset_version'],args['trip_id'],args['service_date'],args['seat_class'],i,a['stop_id'],a['sequence_index'],i,b['stop_id'],b['sequence_index'],i+1,cap,0,0,0,self.stamp()))
        return data

    def inventory(self,ctx,**args):
        quantity=integer(args.get('quantity',1),'quantity',1,6)
        with self.store.transaction() as c:
            self._expire(c,ctx.scenario_id)
            try:data=self._materialize(c,ctx,args)
            except ValueError as exc:
                if str(exc)=='INVENTORY_NOT_CONFIGURED':return dict(status=str(exc),available=None,simulation=True)
                raise
            rows=c.execute('SELECT capacity-held-sold FROM v39_inventory_segments WHERE scenario_id=? AND dataset_version=? AND trip_id=? AND service_date=? AND seat_class=? AND segment_index>=? AND segment_index<?',
                (ctx.scenario_id,data['dataset_version'],args['trip_id'],args['service_date'],args['seat_class'],data['origin']['position'],data['destination']['position'])).fetchall()
            available=min(r[0] for r in rows)
            return dict(status='SIMULATED_AVAILABLE' if available>=quantity else 'INVENTORY_SOLD_OUT' if available==0 else 'INVENTORY_INSUFFICIENT',available=available,simulation=True,dataset_version=data['dataset_version'])

    def quote(self,ctx,**args):
        count=integer(args['passenger_count'],'passenger_count',1,6)
        with self.store.transaction() as c:
            _,data=self._interval(c,ctx,args)
            rule=select_rule(c,ctx.scenario_id,data['dataset_version'],args['trip_id'],args['seat_class'],self.stamp())
            fare=price(rule,len(data['segments']),count)
            q=dict(quote_id='Q'+uuid.uuid4().hex,session_id=ctx.session_id,owner_phone=ctx.owner_phone,scenario_id=ctx.scenario_id,dataset_version=data['dataset_version'],trip_id=args['trip_id'],service_date=args['service_date'],origin_stop_id=args['origin_stop_id'],destination_stop_id=args['destination_stop_id'],origin_sequence=data['origin']['sequence_index'],destination_sequence=data['destination']['sequence_index'],origin_position=data['origin']['position'],destination_position=data['destination']['position'],seat_class=args['seat_class'],passenger_count=count,rule_id=rule['rule_id'],rule_version=rule['version'],base_fen_per_segment=rule['base_fen_per_segment'],seat_multiplier_bp=rule['seat_multiplier_bp'],fixed_fee_fen=rule['fixed_fee_fen'],segment_count=len(data['segments']),currency='CNY',status='ACTIVE',expires_at=(self.now()+timedelta(seconds=600)).isoformat(),created_at=self.stamp())
            q.update({k:v for k,v in fare.items() if k!='items'});q['quote_hash']=digest(q)
            insert(c,'v39_quotes',q)
            return dict(status='QUOTED',quote=q,items=fare['items'],simulation=True)

    def _quote(self,c,ctx,qid):
        q=c.execute('SELECT * FROM v39_quotes WHERE quote_id=?',(qid,)).fetchone()
        if not q or q['owner_phone']!=ctx.owner_phone or q['session_id']!=ctx.session_id:raise ValueError('QUOTE_FORBIDDEN')
        if q['scenario_id']!=ctx.scenario_id:raise ValueError('QUOTE_FORBIDDEN')
        if q['status']!='ACTIVE':raise ValueError('QUOTE_CONSUMED')
        if q['expires_at']<=self.stamp():raise ValueError('QUOTE_EXPIRED')
        if digest({k:v for k,v in dict(q).items() if k!='quote_hash'})!=q['quote_hash']:raise ValueError('QUOTE_HASH_MISMATCH')
        return dict(q)

    def order(self,ctx,order_id=None):
        ctx.require()
        with self.store.transaction() as c:
            if order_id:
                self._expire(c,ctx.scenario_id)
                row=c.execute('SELECT * FROM v39_orders WHERE order_id=? AND owner_phone=? AND session_id=? AND scenario_id=?',(order_id,ctx.owner_phone,ctx.session_id,ctx.scenario_id)).fetchone()
                if not row:raise ValueError('ORDER_FORBIDDEN')
                result=dict(row);result['items']=[dict(r) for r in c.execute('SELECT * FROM v39_order_items WHERE order_id=? ORDER BY passenger_index',(order_id,))]
                result['transactions']=[dict(r) for r in c.execute('SELECT * FROM v39_transactions WHERE order_id=? ORDER BY created_at',(order_id,))]
                result['refunds']=[dict(r) for r in c.execute('SELECT * FROM v39_refund_requests WHERE order_id=? ORDER BY created_at',(order_id,))]
                result['changes']=[dict(r) for r in c.execute('SELECT * FROM v39_change_requests WHERE order_id=? ORDER BY created_at',(order_id,))]
                result['refund_items']=[dict(r) for r in c.execute('SELECT * FROM v39_refund_items WHERE order_id=?',(order_id,))]
                result['price_snapshots']=[dict(r) for r in c.execute('SELECT s.* FROM v39_item_price_snapshots s JOIN v39_order_items i ON i.item_id=s.item_id WHERE i.order_id=?',(order_id,))]
                return result
            self._expire(c,ctx.scenario_id)
            return [dict(r) for r in c.execute('SELECT * FROM v39_orders WHERE owner_phone=? AND session_id=? AND scenario_id=? ORDER BY created_at DESC',(ctx.owner_phone,ctx.session_id,ctx.scenario_id))]

    def refund_preview(self,ctx,order_id,item_ids):
        ctx.require('REFUND')
        with self.store.transaction() as c:
            row=c.execute('SELECT * FROM v39_orders WHERE order_id=? AND session_id=? AND owner_phone=? AND scenario_id=?',(order_id,ctx.session_id,ctx.owner_phone,ctx.scenario_id)).fetchone()
            if not row:raise ValueError('ORDER_FORBIDDEN')
            if row['order_status'] not in ('PAID','CHANGED'):raise ValueError('INVALID_STATE')
            items,fees=self._refund_preview(c,dict(row),dict(scope='ITEMS',item_ids=item_ids))
            return dict(amount_fen=sum(f['amount_fen'] for f in fees),fee_fen=sum(f['fee_fen'] for f in fees),net_fen=sum(f['net_fen'] for f in fees),policy_version=self.policy.version)

    def pending(self,ctx):
        ctx.require()
        with self.store.transaction() as c:
            return [dict(r) for r in c.execute("SELECT * FROM v39_proposals WHERE session_id=? AND owner_phone=? AND scenario_id=? AND state='PENDING' ORDER BY created_at DESC",(ctx.session_id,ctx.owner_phone,ctx.scenario_id))]

    def decline(self,ctx,proposal_id):
        ctx.require()
        with self.store.transaction() as c:
            changed=c.execute("UPDATE v39_proposals SET state='CANCELLED' WHERE proposal_id=? AND session_id=? AND owner_phone=? AND scenario_id=? AND state='PENDING'",(proposal_id,ctx.session_id,ctx.owner_phone,ctx.scenario_id)).rowcount
            if changed:
                c.execute("UPDATE v39_confirmation_tokens SET invalidated_at=?,invalid_reason='USER_DECLINED' WHERE proposal_id=? AND used_at IS NULL",(self.stamp(),proposal_id))
                insert(c,'v39_audit_events',dict(event_id=uuid.uuid4().hex,aggregate_type='proposal',aggregate_id=proposal_id,event_type='USER_DECLINED',detail_json='{}',created_at=self.stamp()))
        if changed:self._secrets.pop(proposal_id,None)
        return bool(changed)

    def page_event(self,ctx,name,args,result,ok,elapsed):
        ctx.require()
        with self.store.transaction() as c:
            insert(c,'v39_audit_events',dict(event_id=uuid.uuid4().hex,aggregate_type='page',aggregate_id=ctx.session_id,event_type=name,detail_json=json.dumps(dict(source='page_operation',ok=ok,elapsed_ms=elapsed,args=args,result=result),ensure_ascii=False),created_at=self.stamp()))

    def propose(self,ctx,action,payload):
        ctx.require(action)
        if self.epoch is None:raise ValueError('CONFIRMATION_WORKER_NOT_STARTED')
        if action not in ('CREATE_ORDER','PAY','CANCEL','REFUND','CHANGE'):raise ValueError('INVALID_ACTION')
        retired=[]
        with self.store.transaction() as c:
            self._scope(c,ctx)
            self._lease(c)
            payload=dict(payload)
            amount=None
            if action=='CREATE_ORDER':
                q=self._quote(c,ctx,payload['quote_id'])
                names=payload['passengers']
                require_names(names,q['passenger_count'])
                if payload.get('contact',ctx.owner_phone)!=ctx.owner_phone:raise ValueError('ORDER_FORBIDDEN')
                amount=q['total_fen'];payload['_display_preview']=dict(total_fen=amount,passengers=len(names))
                aggregate=q['quote_id']
            else:
                order=c.execute('SELECT * FROM v39_orders WHERE order_id=? AND owner_phone=? AND session_id=? AND scenario_id=?',(payload['order_id'],ctx.owner_phone,ctx.session_id,ctx.scenario_id)).fetchone()
                if not order:raise ValueError('ORDER_FORBIDDEN')
                aggregate=order['order_id']
                payload['_order_version']=order['version']
                if action in ('REFUND','CHANGE') or action=='CANCEL' and order['order_status'] in ('PAID','CHANGED'):
                    self.policy.require();payload['_policy']=digest(self.policy.__dict__)
                amount=self._preview(c,ctx,action,dict(order),payload)
            now=self.stamp()
            c.execute("UPDATE v39_proposals SET state='EXPIRED' WHERE session_id=? AND state='PENDING' AND expires_at<=?",(ctx.session_id,now))
            if action=='CREATE_ORDER':
                # Only retire an owned, unused legacy placeholder draft for this
                # exact quote. Keep its original payload and history. This and
                # the replacement proposal commit or roll back together.
                drafts=c.execute("SELECT * FROM v39_proposals p WHERE session_id=? AND owner_phone=? AND scenario_id=? AND action='CREATE_ORDER' AND aggregate_id=? AND state='PENDING' AND NOT EXISTS (SELECT 1 FROM v39_orders o WHERE o.proposal_id=p.proposal_id) AND NOT EXISTS (SELECT 1 FROM v39_confirmation_tokens t WHERE t.proposal_id=p.proposal_id AND t.used_at IS NOT NULL)",(ctx.session_id,ctx.owner_phone,ctx.scenario_id,aggregate)).fetchall()
                for draft in drafts:
                    previous=json.loads(draft['payload_json'])
                    if digest(previous)!=draft['request_hash'] or not has_placeholders(previous.get('passengers')):continue
                    c.execute("UPDATE v39_proposals SET state='CANCELLED' WHERE proposal_id=? AND state='PENDING'",(draft['proposal_id'],))
                    c.execute("UPDATE v39_confirmation_tokens SET invalidated_at=?,invalid_reason='PASSENGER_NAME_REQUIRED' WHERE proposal_id=? AND used_at IS NULL",(now,draft['proposal_id']))
                    retired.append(draft['proposal_id'])
            pending=c.execute("SELECT COUNT(*) FROM v39_proposals WHERE session_id=? AND action=? AND aggregate_id=? AND state='PENDING'",(ctx.session_id,action,aggregate)).fetchone()[0]
            if pending>=(2 if action=='REFUND' else 1):raise ValueError('PROPOSAL_ALREADY_PENDING')
            pid='P'+uuid.uuid4().hex;raw=secrets.token_bytes(32);h=hashlib.sha256(raw).hexdigest();expiry=(self.now()+timedelta(seconds=300)).isoformat()
            values=dict(proposal_id=pid,session_id=ctx.session_id,owner_phone=ctx.owner_phone,action=action,aggregate_id=aggregate,quote_id=payload.get('quote_id') or payload.get('target_quote_id'),order_id=payload.get('order_id'),scenario_id=ctx.scenario_id,confirmation_owner_worker=self.worker,confirmation_boot_epoch=self.epoch,idempotency_key=pid,request_hash=digest(payload),payload_json=json.dumps(payload,ensure_ascii=False),state='PENDING',expires_at=expiry,created_at=now)
            values.update(ctx.snapshot());insert(c,'v39_proposals',values)
            insert(c,'v39_confirmation_tokens',dict(token_hash=h,proposal_id=pid,owner_worker_id=self.worker,owner_boot_epoch=self.epoch,session_id=ctx.session_id,owner_phone=ctx.owner_phone,action=action,aggregate_id=aggregate,quote_id=values['quote_id'],amount_fen=amount,args_hash=digest(payload),expires_at=expiry,created_at=now))
            for old in retired:
                insert(c,'v39_audit_events',dict(event_id=uuid.uuid4().hex,aggregate_type='proposal',aggregate_id=old,event_type='INVALID_PASSENGER_PROPOSAL_REPLACED',detail_json=json.dumps(dict(replacement_proposal_id=pid,reason='PASSENGER_NAME_REQUIRED')),created_at=now))
        for old in retired:self._secrets.pop(old,None)
        self._secrets[pid]=raw
        return dict(proposal_id=pid,status='CONFIRMATION_REQUIRED',expires_at=expiry,simulation=True,
                    preview=payload.get('_refund_preview') or payload.get('_display_preview'))

    def _event(self,c,order_id,kind,before,after,detail=None):
        insert(c,'v39_audit_events',dict(event_id=uuid.uuid4().hex,aggregate_type='order',aggregate_id=order_id,event_type=kind,from_state=before,to_state=after,detail_json=json.dumps(detail or {},ensure_ascii=False),created_at=self.stamp()))

    def _delta(self,c,hold,segment,held,sold,reason,*,refund_id=None):
        key=(segment['scenario_id'],segment['dataset_version'],segment['trip_id'],segment['service_date'],segment['seat_class'],segment['segment_index'])
        changed=c.execute('UPDATE v39_inventory_segments SET held=held+?,sold=sold+?,version=version+1,updated_at=? WHERE scenario_id=? AND dataset_version=? AND trip_id=? AND service_date=? AND seat_class=? AND segment_index=? AND held+?>=0 AND sold+?>=0 AND held+sold+?+?<=capacity',(held,sold,self.stamp(),*key,held,sold,held,sold)).rowcount
        if changed!=1:raise ValueError('INVENTORY_INSUFFICIENT')
        insert(c,'v39_inventory_events',dict(event_id=uuid.uuid4().hex,scenario_id=key[0],dataset_version=key[1],trip_id=key[2],service_date=key[3],seat_class=key[4],segment_index=key[5],delta_held=held,delta_sold=sold,hold_id=hold['hold_id'],order_id=hold['order_id'],change_id=hold.get('change_id'),refund_id=refund_id,reason=reason,created_at=self.stamp()))

    def _segments(self,c,hold_id):
        return [dict(r) for r in c.execute('SELECT * FROM v39_hold_segments WHERE hold_id=? ORDER BY segment_index',(hold_id,))]

    def _release_pending(self,c,order,status):
        h=dict(c.execute('SELECT * FROM v39_holds WHERE hold_id=?',(order['hold_id'],)).fetchone())
        if h['status']!='ACTIVE':raise ValueError('INVALID_HOLD_STATE')
        for s in self._segments(c,h['hold_id']):
            self._delta(c,h,s,-s['quantity'],0,status)
            c.execute('UPDATE v39_hold_segments SET quantity=0 WHERE hold_id=? AND segment_index=?',(h['hold_id'],s['segment_index']))
        c.execute('UPDATE v39_holds SET status=?,quantity=0,remaining_quantity=0,released_at=? WHERE hold_id=?',('EXPIRED' if status=='EXPIRED' else 'RELEASED',self.stamp(),h['hold_id']))
        c.execute('UPDATE v39_orders SET order_status=?,updated_at=?,version=version+1 WHERE order_id=?',(status,self.stamp(),order['order_id']))

    def _money(self,c,order_id,kind,amount,allocations,*,refund_id=None,change_id=None,failed=False,key):
        integer(amount,'amount_fen',1)
        if sum(a[1] for a in allocations)!=amount:raise ValueError('ALLOCATION_SUM_MISMATCH')
        tid='TX'+uuid.uuid4().hex
        insert(c,'v39_transactions',dict(transaction_id=tid,order_id=order_id,transaction_type=kind,direction='DEBIT' if kind in ('PAYMENT','CHANGE_SUPPLEMENT') else 'CREDIT',amount_fen=amount,status='PENDING',idempotency_key=key,request_hash=digest([kind,amount,allocations]),refund_id=refund_id,change_id=change_id,created_at=self.stamp()))
        for item,value in allocations:
            insert(c,'v39_transaction_allocations',dict(allocation_id=uuid.uuid4().hex,transaction_id=tid,order_id=order_id,order_item_id=item,change_id=change_id,amount_fen=value))
        c.execute('UPDATE v39_transactions SET status=?,finished_at=? WHERE transaction_id=?',('TIMEOUT' if failed=='TIMEOUT' else 'FAILED' if failed else 'SUCCEEDED',self.stamp(),tid))
        return tid

    def confirm(self,ctx,proposal_id):
        ctx.require()
        with self.store.transaction() as c:
            p=c.execute('SELECT * FROM v39_proposals WHERE proposal_id=? AND session_id=? AND owner_phone=?',(proposal_id,ctx.session_id,ctx.owner_phone)).fetchone()
            if not p:raise ValueError('PROPOSAL_NOT_FOUND')
            key='confirm:'+ctx.session_id+':'+proposal_id+':'+p['action']
            receipt=c.execute("SELECT * FROM v39_idempotency WHERE scope='confirm' AND key=?",(key,)).fetchone()
            payload=json.loads(p['payload_json'])
            if digest(payload)!=p['request_hash']:raise ValueError('IDEMPOTENCY_CONFLICT')
            if receipt:
                if receipt['request_hash']!=p['request_hash']:raise ValueError('IDEMPOTENCY_CONFLICT')
                return json.loads(receipt['response_json'])
            ctx.require(p['action'])
            if any(p[n]!=v for n,v in ctx.snapshot().items()):raise ValueError('PROPOSAL_CONFIG_STALE')
            if p['confirmation_owner_worker']!=self.worker:raise ValueError('CONFIRMATION_WRONG_WORKER')
            self._lease(c)
            if p['confirmation_boot_epoch']!=self.epoch or proposal_id not in self._secrets:
                c.execute("UPDATE v39_proposals SET state='SECRET_LOST' WHERE proposal_id=? AND state='PENDING'",(proposal_id,))
                c.execute("UPDATE v39_confirmation_tokens SET invalidated_at=?,invalid_reason='SECRET_LOST' WHERE proposal_id=? AND used_at IS NULL",(self.stamp(),proposal_id))
                return dict(status='CONFIRMATION_SECRET_LOST',simulation=True)
            if p['expires_at']<=self.stamp():
                c.execute("UPDATE v39_proposals SET state='EXPIRED' WHERE proposal_id=?",(proposal_id,))
                return dict(status='PROPOSAL_EXPIRED',simulation=True)
            if p['state']!='PENDING':raise ValueError('CONFIRMATION_USED')
            token=hashlib.sha256(self._secrets[proposal_id]).hexdigest()
            used=c.execute('UPDATE v39_confirmation_tokens SET used_at=? WHERE token_hash=? AND proposal_id=? AND used_at IS NULL AND invalidated_at IS NULL AND expires_at>? AND args_hash=? AND owner_boot_epoch=?',(self.stamp(),token,proposal_id,self.stamp(),p['request_hash'],self.epoch)).rowcount
            if used!=1:raise ValueError('CONFIRMATION_INVALID')
            if p['action']=='CREATE_ORDER':result=self._create(c,ctx,p,payload)
            else:
                order=c.execute('SELECT * FROM v39_orders WHERE order_id=? AND owner_phone=? AND session_id=? AND scenario_id=?',(payload['order_id'],ctx.owner_phone,ctx.session_id,ctx.scenario_id)).fetchone()
                if not order:raise ValueError('ORDER_FORBIDDEN')
                if '_policy' in payload and payload['_policy']!=digest(self.policy.__dict__):raise ValueError('PROPOSAL_POLICY_STALE')
                refund=p['action']=='REFUND' or p['action']=='CANCEL' and '_refund_preview' in payload
                if order['version']!=payload['_order_version'] and not (order['order_status']=='EXPIRED' and p['action']=='PAY') and not refund:raise ValueError('PROPOSAL_ORDER_STALE')
                if refund and (order['quote_id']!=payload['_refund_quote'] or order['hold_id']!=payload['_refund_hold']):raise ValueError('PROPOSAL_ORDER_STALE')
                result=self._execute(c,ctx,p,dict(order),payload)
            c.execute("UPDATE v39_proposals SET state='CONFIRMED',consumed_at=? WHERE proposal_id=?",(self.stamp(),proposal_id))
            insert(c,'v39_idempotency',dict(scope='confirm',key=key,request_hash=p['request_hash'],response_json=json.dumps(result,ensure_ascii=False),status='FAILED' if result.get('error') else 'SUCCEEDED',created_at=self.stamp(),expires_at=(self.now()+timedelta(days=30)).isoformat()))
            return result

    def _create(self,c,ctx,p,payload):
        q=self._quote(c,ctx,payload['quote_id']);names=payload['passengers']
        require_names(names,q['passenger_count'])
        if datetime.fromisoformat(self._departure(q))<=self.now():raise ValueError('DEPARTURE_ALREADY_PASSED')
        self._expire(c,ctx.scenario_id)
        self._materialize(c,ctx,q)
        if len(names)!=q['passenger_count']:raise ValueError('PASSENGER_MISMATCH')
        oid='V39-'+uuid.uuid4().hex;hid='H'+uuid.uuid4().hex;now=self.stamp()
        h=dict(hold_id=hid,quote_id=q['quote_id'],order_id=oid,session_id=ctx.session_id,owner_phone=ctx.owner_phone,scenario_id=ctx.scenario_id,trip_id=q['trip_id'],service_date=q['service_date'],seat_class=q['seat_class'],quantity=len(names),initial_quantity=len(names),remaining_quantity=len(names),status='ACTIVE',expires_at=(self.now()+timedelta(seconds=900)).isoformat(),created_at=now)
        insert(c,'v39_holds',h)
        for i in range(q['origin_position'],q['destination_position']):
            s=dict(hold_id=hid,scenario_id=ctx.scenario_id,dataset_version=q['dataset_version'],trip_id=q['trip_id'],service_date=q['service_date'],seat_class=q['seat_class'],segment_index=i,quantity=len(names),inventory_role='NEW')
            self._delta(c,h,s,len(names),0,'HOLD');insert(c,'v39_hold_segments',s)
        o={k:q[k] for k in ('dataset_version','trip_id','service_date','origin_stop_id','destination_stop_id','origin_sequence','destination_sequence','origin_position','destination_position','seat_class','total_fen','currency')}
        o.update(order_id=oid,proposal_id=p['proposal_id'],session_id=ctx.session_id,owner_phone=ctx.owner_phone,scenario_id=ctx.scenario_id,quote_id=q['quote_id'],hold_id=hid,passenger_count=len(names),initial_passenger_count=len(names),active_item_count=len(names),refunded_item_count=0,order_status='PENDING_PAYMENT',payment_status='UNPAID',refund_status='NONE',change_status='NONE',policy_profile=self.policy.profile if self.policy.approved else 'D9_PENDING',idempotency_key=p['proposal_id'],created_at=now,updated_at=now,expires_at=h['expires_at'])
        insert(c,'v39_orders',o)
        fares=price(q,q['segment_count'],q['passenger_count'])['items']
        from target.v39.item_prices import freeze
        for i,(name,fare) in enumerate(zip(names,fares)):
            iid='I'+uuid.uuid4().hex
            insert(c,'v39_order_items',dict(item_id=iid,order_id=oid,passenger_index=i,passenger_name=name,seat_class=q['seat_class'],item_status='ACTIVE',price_quote_id=q['quote_id'],created_at=now,**fare))
            freeze(self,c,iid,q['quote_id'],i,fare)
        insert(c,'v39_order_snapshots',dict(order_id=oid,snapshot_version=1,static_snapshot_json=json.dumps({k:q[k] for k in ('dataset_version','trip_id','service_date','origin_stop_id','destination_stop_id')}),price_snapshot_json=json.dumps(q),quote_hash=q['quote_hash'],created_at=now))
        c.execute("UPDATE v39_quotes SET status='CONSUMED' WHERE quote_id=?",(q['quote_id'],))
        self._event(c,oid,'CREATE_ORDER',None,'PENDING_PAYMENT')
        return dict(status='PENDING_PAYMENT',order_id=oid,total_fen=q['total_fen'],simulation=True)

    def _execute(self,c,ctx,p,o,payload):
        action=p['action'];oid=o['order_id']
        if action in ('REFUND','CANCEL') and '_refund_preview' in payload:return self._refund(c,ctx,p,o,payload)
        if o['order_status']=='EXPIRED' and action=='PAY':return dict(status='EXPIRED',error='EXPIRED',order_id=oid,simulation=True)
        if o['order_status']=='PENDING_PAYMENT':
            if o['expires_at']<=self.stamp():
                self._release_pending(c,o,'EXPIRED');self._event(c,oid,'EXPIRE',o['order_status'],'EXPIRED')
                return dict(status='EXPIRED',error='EXPIRED',order_id=oid,simulation=True)
            if action=='CANCEL':
                self._release_pending(c,o,'CANCELLED');self._event(c,oid,'CANCEL',o['order_status'],'CANCELLED')
                return dict(status='CANCELLED',order_id=oid,simulation=True)
            if action!='PAY':raise ValueError('INVALID_STATE')
            if payload['expected_total_fen']!=o['total_fen'] or type(payload['expected_total_fen']) is not int:raise ValueError('AMOUNT_MISMATCH')
            failed=c.execute('SELECT name FROM v39_scenarios WHERE scenario_id=?',(ctx.scenario_id,)).fetchone()[0]=='payment_fail'
            timeout=self._fault(c,ctx,'payment_timeouts_remaining')
            items=c.execute("SELECT item_id,fare_fen FROM v39_order_items WHERE order_id=? AND item_status='ACTIVE' ORDER BY passenger_index",(oid,)).fetchall()
            self._money(c,oid,'PAYMENT',o['total_fen'],[(r[0],r[1]) for r in items],failed='TIMEOUT' if timeout else failed,key=p['proposal_id'])
            if failed or timeout:
                self._release_pending(c,o,'PAYMENT_FAILED')
                c.execute('UPDATE v39_orders SET payment_status=? WHERE order_id=?',('TIMEOUT' if timeout else 'FAILED',oid))
                self._event(c,oid,'PAYMENT_FAILED',o['order_status'],'PAYMENT_FAILED')
                return dict(status='PAYMENT_FAILED',error='PAYMENT_TIMEOUT' if timeout else 'PAYMENT_FAILED',order_id=oid,simulation=True)
            h=dict(c.execute('SELECT * FROM v39_holds WHERE hold_id=?',(o['hold_id'],)).fetchone())
            for s in self._segments(c,h['hold_id']):self._delta(c,h,s,-s['quantity'],s['quantity'],'PAYMENT')
            c.execute("UPDATE v39_holds SET status='CONSUMED' WHERE hold_id=?",(h['hold_id'],))
            c.execute("UPDATE v39_orders SET order_status='PAID',payment_status='SUCCEEDED',paid_total_fen=total_fen,net_paid_fen=total_fen,updated_at=?,version=version+1 WHERE order_id=?",(self.stamp(),oid))
            self._event(c,oid,'PAYMENT',o['order_status'],'PAID')
            return dict(status='PAID',order_id=oid,simulation=True)
        if o['order_status'] in ('PAID','CHANGED'):
            if action in ('REFUND','CANCEL'):return self._refund(c,ctx,p,o,payload)
            if action=='CHANGE':return self._change(c,ctx,p,o,payload)
        raise ValueError('INVALID_STATE')
