"""Atomic local simulation transitions. No network, legacy tables or model calls."""
from datetime import datetime,timedelta
import json,uuid
from target.v39.pricing import price
from target.v39.store import integer
from target.v39.item_prices import validate,selected,freeze

KEY=('scenario_id','dataset_version','trip_id','service_date','seat_class','segment_index')


class Lifecycle:
    def _lease(self,c):
        row=c.execute('SELECT * FROM v39_worker_lease WHERE slot=1').fetchone()
        if not row or row['worker_id']!=self.worker or row['boot_epoch']!=self.epoch or row['status']!='ACTIVE':
            raise ValueError('CONFIRMATION_LEASE_LOST')
        # BEGIN IMMEDIATE fences renewal and takeover. An expired owner may renew
        # only while its exact epoch still owns the singleton row.
        c.execute('UPDATE v39_worker_lease SET lease_until=? WHERE slot=1',((self.infrastructure_now()+timedelta(seconds=60)).isoformat(),))

    def close(self):
        if self.epoch:self.store.release_worker(self.worker,self.epoch)
        self._secrets.clear();self.epoch=None

    def _expire(self,c,scenario):
        rows=c.execute("SELECT * FROM v39_orders WHERE scenario_id=? AND order_status='PENDING_PAYMENT' AND expires_at<=?",(scenario,self.stamp())).fetchall()
        for row in rows:
            self._release_pending(c,dict(row),'EXPIRED')
            self._event(c,row['order_id'],'EXPIRE','PENDING_PAYMENT','EXPIRED')
        return len(rows)

    def expire(self,ctx):
        ctx.require()
        with self.store.transaction() as c:return self._expire(c,ctx.scenario_id)

    def _active_items(self,c,o):
        return [dict(r) for r in c.execute("SELECT * FROM v39_order_items WHERE order_id=? AND item_status='ACTIVE' ORDER BY passenger_index",(o['order_id'],))]

    def _departure(self,o):
        return self.static.interval(o['trip_id'],o['service_date'],o['origin_stop_id'],o['destination_stop_id'])['origin']['departure_at']

    def _refund_preview(self,c,o,payload):
        items=self._active_items(c,o)
        scope=payload.get('scope','FULL')
        ids=payload.get('item_ids')
        if scope=='FULL':
            if ids is not None:raise ValueError('FULL_REFUND_MUST_NOT_SELECT_ITEMS')
        elif scope=='ITEMS':
            if not isinstance(ids,list) or not ids or len(set(ids))!=len(ids):raise ValueError('REFUND_EXCEEDS_ALLOWED')
            chosen=set(ids)
            items=[i for i in items if i['item_id'] in chosen]
            if len(items)!=len(ids):raise ValueError('REFUND_ALREADY_DONE_OR_FORBIDDEN')
        else:raise ValueError('INVALID_REFUND_SCOPE')
        if not items:raise ValueError('REFUND_ALREADY_DONE')
        validate(c,items)
        fees=self.policy.refund([i['fare_fen'] for i in items],self._departure(o),self.stamp(),changed=o['change_count']>0,already_refunded=o['refunded_item_count']>0)
        return items,fees

    def _change_preview(self,c,ctx,o,payload):
        self.policy.change(o['change_count'],already_refunded=o['refunded_item_count']>0)
        if datetime.fromisoformat(self._departure(o))<=self.now():raise ValueError('CHANGE_AFTER_DEPARTURE')
        q=self._quote(c,ctx,payload['target_quote_id'])
        if q['dataset_version']!=o['dataset_version']:raise ValueError('INVENTORY_IDENTITY_MISMATCH')
        for name in ('trip_id','service_date','origin_stop_id','destination_stop_id','seat_class'):
            if payload.get('target_'+name)!=q[name]:raise ValueError('TARGET_QUOTE_MISMATCH')
        if datetime.fromisoformat(self._departure(q))<=self.now():raise ValueError('CHANGE_AFTER_DEPARTURE')
        if q['passenger_count']!=o['active_item_count']:raise ValueError('PASSENGER_MISMATCH')
        # Per-passenger deltas must all have the same direction, otherwise one
        # net transaction could conceal money moving both ways.
        items=self._active_items(c,o);fares=price(q,q['segment_count'],len(items))['items']
        deltas=[f['fare_fen']-i['fare_fen'] for i,f in zip(items,fares)]
        if any(d<0 for d in deltas) and any(d>0 for d in deltas):raise ValueError('PRICE_ALLOCATION_DIRECTION_AMBIGUOUS')
        return q,items,fares,deltas

    def _preview(self,c,ctx,action,o,payload):
        if o['order_status']=='PENDING_PAYMENT':
            if action=='PAY':
                integer(payload['expected_total_fen'],'expected_total_fen',1)
                if payload['expected_total_fen']!=o['total_fen']:raise ValueError('AMOUNT_MISMATCH')
                return o['total_fen']
            if action=='CANCEL':return 0
            raise ValueError('INVALID_STATE')
        if o['order_status'] not in ('PAID','CHANGED') or not o['active_item_count']:raise ValueError('INVALID_STATE')
        if action in ('REFUND','CANCEL'):
            items,fees=self._refund_preview(c,o,payload)
            payload['_refund_preview']=dict(items=selected(items,fees),amount_fen=sum(f['amount_fen'] for f in fees),fee_fen=sum(f['fee_fen'] for f in fees),net_fen=sum(f['net_fen'] for f in fees),policy_version=self.policy.version)
            payload['_refund_quote']=o['quote_id'];payload['_refund_hold']=o['hold_id']
            return sum(f['net_fen'] for f in fees)
        if action=='CHANGE':
            q,items,fares,deltas=self._change_preview(c,ctx,o,payload)
            payload['_display_preview']=dict(old_face_fen=o['total_fen'],new_face_fen=q['total_fen'],difference_fen=sum(deltas),passengers=len(items),policy_version=self.policy.version)
            return sum(deltas)
        raise ValueError('INVALID_STATE')

    def _fault(self,c,ctx,name):
        config=json.loads(c.execute('SELECT config_json FROM v39_scenarios WHERE scenario_id=?',(ctx.scenario_id,)).fetchone()[0])
        remaining=integer(config.get(name,0),name)
        if not remaining:return False
        config[name]=remaining-1
        c.execute('UPDATE v39_scenarios SET config_json=? WHERE scenario_id=?',(json.dumps(config),ctx.scenario_id))
        return True

    def _reconcile(self,c,oid):
        # Only successful ledger entries affect balances; failed attempts survive
        # for audit, never as credits/debits or fees.
        from target.v39.accounting import balances
        ledger=balances(c.execute('SELECT direction,amount_fen,status FROM v39_transactions WHERE order_id=?',(oid,)))
        debit,credit=ledger['paid_total_fen'],ledger['refunded_total_fen']
        fee=c.execute("SELECT COALESCE(SUM(fee_fen),0) FROM v39_refund_requests WHERE order_id=? AND status='SUCCEEDED'",(oid,)).fetchone()[0]
        face,count=c.execute("SELECT COALESCE(SUM(fare_fen),0),COUNT(*) FROM v39_order_items WHERE order_id=? AND item_status='ACTIVE'",(oid,)).fetchone()
        if debit-credit!=face+fee:raise ValueError('MONEY_CONSERVATION_FAILURE')
        c.execute('UPDATE v39_orders SET paid_total_fen=?,refunded_total_fen=?,fee_total_fen=?,net_paid_fen=?,total_fen=?,active_item_count=?,refunded_item_count=initial_passenger_count-?,updated_at=?,version=version+1 WHERE order_id=?',(debit,credit,fee,debit-credit,face,count,count,self.stamp(),oid))

    def _refund(self,c,ctx,p,o,payload):
        frozen=payload['_refund_preview'];wanted=frozen['items']
        items=[dict(c.execute('SELECT * FROM v39_order_items WHERE item_id=? AND order_id=?',(v['item_id'],o['order_id'])).fetchone()) for v in wanted]
        validate(c,items)
        conflict=any(i['item_status']!='ACTIVE' for i in items)
        if any(i['price_quote_id']!=v['price_quote_id'] for i,v in zip(items,wanted)):raise ValueError('PROPOSAL_PRICE_STALE')
        if not conflict:
            fees=self.policy.refund([i['fare_fen'] for i in items],self._departure(o),self.stamp(),changed=o['change_count']>0,already_refunded=o['refunded_item_count']>0)
            if selected(items,fees)!=wanted:raise ValueError('PROPOSAL_PRICE_STALE')
        else:fees=[{k:v[k] for k in ('amount_fen','fee_fen','net_fen')} for v in wanted]
        rid='RF'+uuid.uuid4().hex
        gross=sum(f['amount_fen'] for f in fees);fee=sum(f['fee_fen'] for f in fees);net=gross-fee
        self._insert(c,'v39_refund_requests',dict(refund_id=rid,order_id=o['order_id'],scope=payload.get('scope','FULL'),requested_fen=gross,refundable_fen=gross,fee_fen=fee,net_fen=net,status='PENDING',prior_order_status=o['order_status'],prior_total_fen=o['total_fen'],reason=payload.get('reason',''),idempotency_key=p['proposal_id'],created_at=self.stamp()))
        for item,values in zip(items,fees):
            self._insert(c,'v39_refund_items',dict(refund_id=rid,order_id=o['order_id'],order_item_id=item['item_id'],price_quote_id=item['price_quote_id'],status='REQUESTED',**values))
        failed=conflict or self._fault(c,ctx,'refund_failures_remaining')
        error='REFUND_ALREADY_DONE' if conflict else 'SIMULATED_REFUND_FAILURE'
        self._money(c,o['order_id'],'REFUND',net,[(i['item_id'],f['net_fen']) for i,f in zip(items,fees)],refund_id=rid,failed=failed,key=p['proposal_id'])
        c.execute('UPDATE v39_refund_items SET status=? WHERE refund_id=?',('FAILED' if failed else 'SUCCEEDED',rid))
        c.execute('UPDATE v39_refund_requests SET status=?,finished_at=?,failure_code=? WHERE refund_id=?',('FAILED' if failed else 'SUCCEEDED',self.stamp(),error if failed else None,rid))
        if failed:
            c.execute("UPDATE v39_orders SET refund_status='FAILED',version=version+1,updated_at=? WHERE order_id=?",(self.stamp(),o['order_id']))
            self._event(c,o['order_id'],'REFUND_FAILED',o['order_status'],o['order_status'],dict(refund_id=rid))
            return dict(status='REFUND_FAILED',error=error,order_id=o['order_id'],refund_id=rid,simulation=True)
        for i in items:c.execute("UPDATE v39_order_items SET item_status='REFUNDED' WHERE item_id=?",(i['item_id'],))
        h=dict(c.execute('SELECT * FROM v39_holds WHERE hold_id=?',(o['hold_id'],)).fetchone());qty=len(items)
        for s in self._segments(c,h['hold_id']):
            self._delta(c,h,s,0,-qty,'REFUND',refund_id=rid)
            c.execute('UPDATE v39_hold_segments SET quantity=quantity-? WHERE hold_id=? AND segment_index=?',(qty,h['hold_id'],s['segment_index']))
        remaining=h['remaining_quantity']-qty
        c.execute('UPDATE v39_holds SET quantity=?,remaining_quantity=?,status=? WHERE hold_id=?',(remaining,remaining,'CONSUMED' if remaining else 'REFUNDED',h['hold_id']))
        state=o['order_status'] if remaining else 'CANCELLED'
        c.execute("UPDATE v39_orders SET order_status=?,refund_status='SUCCEEDED',policy_profile=? WHERE order_id=?",(state,self.policy.profile,o['order_id']))
        self._reconcile(c,o['order_id'])
        self._event(c,o['order_id'],'REFUND',o['order_status'],state,dict(refund_id=rid,gross_fen=gross,fee_fen=fee,net_fen=net,policy_version=self.policy.version))
        return dict(status=state,order_id=o['order_id'],refund_id=rid,refund_fen=net,fee_fen=fee,remaining_passengers=remaining,simulation=True)

    def _change(self,c,ctx,p,o,payload):
        q,items,fares,deltas=self._change_preview(c,ctx,o,payload)
        data=self._materialize(c,ctx,q);qty=len(items);cid='CH'+uuid.uuid4().hex
        difference=sum(deltas);old=self._segments(c,o['hold_id']);oldmap={tuple(s[k] for k in KEY):s for s in old}
        target={tuple([ctx.scenario_id,q['dataset_version'],q['trip_id'],q['service_date'],q['seat_class'],i]):dict(zip(KEY,[ctx.scenario_id,q['dataset_version'],q['trip_id'],q['service_date'],q['seat_class'],i])) for i in data['segments']}
        retained=target.keys()&oldmap.keys();new=target.keys()-oldmap.keys();released=oldmap.keys()-target.keys()
        change=dict(change_id=cid,order_id=o['order_id'],old_hold_id=o['hold_id'],new_hold_id=None,old_quote_id=o['quote_id'],target_quote_id=q['quote_id'],difference_fen=difference,status='PENDING',prior_order_status=o['order_status'],prior_total_fen=o['total_fen'],idempotency_key=p['proposal_id'],created_at=self.stamp())
        change.update({'target_'+k:q[k] for k in ('trip_id','service_date','origin_stop_id','destination_stop_id','origin_position','destination_position','seat_class')})
        self._insert(c,'v39_change_requests',change)
        unavailable=any(c.execute('SELECT capacity-held-sold FROM v39_inventory_segments WHERE '+ ' AND '.join(k+'=?' for k in KEY),key).fetchone()[0]<qty for key in new)
        fail=self._fault(c,ctx,'change_money_failures_remaining') if difference else False
        if unavailable or fail:
            if fail:
                self._money(c,o['order_id'],'CHANGE_SUPPLEMENT' if difference>0 else 'CHANGE_REFUND',abs(difference),[(i['item_id'],abs(d)) for i,d in zip(items,deltas)],change_id=cid,failed=True,key=p['proposal_id'])
            reason='INVENTORY_INSUFFICIENT' if unavailable else 'SIMULATED_CHANGE_MONEY_FAILURE'
            c.execute("UPDATE v39_change_requests SET status='FAILED',finished_at=?,failure_code=? WHERE change_id=?",(self.stamp(),reason,cid))
            c.execute("UPDATE v39_orders SET change_status='FAILED',version=version+1,updated_at=? WHERE order_id=?",(self.stamp(),o['order_id']))
            self._event(c,o['order_id'],'CHANGE_FAILED',o['order_status'],o['order_status'],dict(change_id=cid,error=reason))
            return dict(status='CHANGE_FAILED',error=reason,order_id=o['order_id'],change_id=cid,simulation=True)
        hid='H'+uuid.uuid4().hex
        h=dict(hold_id=hid,quote_id=q['quote_id'],order_id=o['order_id'],change_id=cid,session_id=ctx.session_id,owner_phone=ctx.owner_phone,scenario_id=ctx.scenario_id,trip_id=q['trip_id'],service_date=q['service_date'],seat_class=q['seat_class'],quantity=qty,initial_quantity=qty,remaining_quantity=qty,status='ACTIVE',expires_at=(self.now()+timedelta(seconds=900)).isoformat(),created_at=self.stamp())
        self._insert(c,'v39_holds',h)
        c.execute('UPDATE v39_change_requests SET new_hold_id=? WHERE change_id=?',(hid,cid))
        for role,keys,mapping in [('RETAINED',retained,target),('NEW',new,target),('RELEASED',released,oldmap)]:
            for key in sorted(keys):
                s={k:mapping[key][k] for k in KEY}
                sources=dict(source_hold_id=o['hold_id'],source_order_id=o['order_id']) if role=='RETAINED' else {}
                self._insert(c,'v39_change_segments',dict(change_id=cid,role=role,quantity=qty,**s,**sources))
                if role!='RELEASED':self._insert(c,'v39_hold_segments',dict(hold_id=hid,inventory_role=role,quantity=qty,**s,**sources))
                if role=='NEW':self._delta(c,h,s,qty,0,'CHANGE_HOLD')
        if difference:self._money(c,o['order_id'],'CHANGE_SUPPLEMENT' if difference>0 else 'CHANGE_REFUND',abs(difference),[(i['item_id'],abs(d)) for i,d in zip(items,deltas)],change_id=cid,key=p['proposal_id'])
        for key in sorted(new):self._delta(c,h,target[key],-qty,qty,'CHANGE_SOLD')
        oldhold=dict(c.execute('SELECT * FROM v39_holds WHERE hold_id=?',(o['hold_id'],)).fetchone())
        for key in sorted(released):self._delta(c,oldhold,oldmap[key],0,-qty,'CHANGE_RELEASE')
        c.execute("UPDATE v39_holds SET status='CHANGED',quantity=0,remaining_quantity=0 WHERE hold_id=?",(o['hold_id'],))
        c.execute('UPDATE v39_hold_segments SET quantity=0 WHERE hold_id=?',(o['hold_id'],))
        c.execute("UPDATE v39_holds SET status='CONSUMED' WHERE hold_id=?",(hid,))
        for item,fare in zip(items,fares):
            freeze(self,c,item['item_id'],q['quote_id'],items.index(item),fare)
            c.execute('UPDATE v39_order_items SET seat_class=?,base_fen=?,seat_fen=?,fixed_fee_share_fen=?,fare_fen=?,price_quote_id=? WHERE item_id=?',(q['seat_class'],fare['base_fen'],fare['seat_fen'],fare['fixed_fee_share_fen'],fare['fare_fen'],q['quote_id'],item['item_id']))
        fields=('quote_id','trip_id','service_date','origin_stop_id','destination_stop_id','origin_sequence','destination_sequence','origin_position','destination_position','seat_class')
        c.execute('UPDATE v39_orders SET '+','.join(k+'=?' for k in fields)+",hold_id=?,order_status='CHANGED',change_status='SUCCEEDED',change_count=change_count+1,policy_profile=? WHERE order_id=?",(*[q[k] for k in fields],hid,self.policy.profile,o['order_id']))
        c.execute("UPDATE v39_quotes SET status='CONSUMED' WHERE quote_id=?",(q['quote_id'],))
        c.execute("UPDATE v39_change_requests SET status='CONFIRMED',finished_at=? WHERE change_id=?",(self.stamp(),cid))
        version=c.execute('SELECT MAX(snapshot_version)+1 FROM v39_order_snapshots WHERE order_id=?',(o['order_id'],)).fetchone()[0]
        self._insert(c,'v39_order_snapshots',dict(order_id=o['order_id'],snapshot_version=version,static_snapshot_json=json.dumps(data),price_snapshot_json=json.dumps(q),quote_hash=q['quote_hash'],created_at=self.stamp()))
        self._reconcile(c,o['order_id'])
        self._event(c,o['order_id'],'CHANGE',o['order_status'],'CHANGED',dict(change_id=cid,difference_fen=difference,policy_version=self.policy.version))
        return dict(status='CHANGED',order_id=o['order_id'],change_id=cid,difference_fen=difference,simulation=True)
