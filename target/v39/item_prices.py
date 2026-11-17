"""Per-item immutable price provenance; no old/new quote amount guessing."""

FIELDS=('base_fen','seat_fen','fixed_fee_share_fen','fare_fen')

def freeze(service,c,item_id,quote_id,index,fare):
    service._insert(c,'v39_item_price_snapshots',dict(item_id=item_id,quote_id=quote_id,
        quote_passenger_index=index,created_at=service.stamp(),**{k:fare[k] for k in FIELDS}))

def validate(c,items):
    for item in items:
        row=c.execute('SELECT * FROM v39_item_price_snapshots WHERE item_id=? AND quote_id=?',
                      (item['item_id'],item['price_quote_id'])).fetchone()
        if not row or any(row[k]!=item[k] for k in FIELDS):
            raise ValueError('ITEM_PRICE_SNAPSHOT_MISMATCH')

def selected(items,fees):
    return [dict(item_id=i['item_id'],price_quote_id=i['price_quote_id'],**f) for i,f in zip(items,fees)]
