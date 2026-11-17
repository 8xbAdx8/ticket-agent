"""Read-only CREATE receipt invariants. No transactions or state changes."""
def creation_proof(order,proposal):
    h=order.get('hold') or {};items=order.get('items',[]);segments=order.get('inventory',[])
    if order['proposal_id']!=proposal['proposal_id'] or order.get('idempotency_key')!=proposal['proposal_id']:return False
    if not h or any(h.get(k)!=order.get(k) for k in ('order_id','hold_id','quote_id','session_id','owner_phone','scenario_id','trip_id','service_date','seat_class')):return False
    if len(items)<order['passenger_count'] or sum(i['item_status']=='ACTIVE' for i in items)!=order['active_item_count']:return False
    if order['order_status']=='PENDING_PAYMENT':
        expected=set(range(order['origin_position'],order['destination_position']))
        if h['status']!='ACTIVE' or h['remaining_quantity']!=order['active_item_count']:return False
        if {s['segment_index'] for s in segments}!=expected or len(segments)!=len(expected):return False
        if any(s['hold_segment_quantity']!=h['remaining_quantity'] or s['held']<h['remaining_quantity'] for s in segments):return False
    return True
