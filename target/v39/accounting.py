"""Successful local ledger entries only. Amounts are integer fen."""
from target.v39.store import integer

def balances(rows):
    paid=refunded=0
    for row in rows:
        value=integer(row['amount_fen'],'amount_fen',1)
        if row['direction'] not in ('DEBIT','CREDIT'):raise ValueError('INVALID_MONEY_DIRECTION')
        if row['status']!='SUCCEEDED':continue
        if row['direction']=='DEBIT':paid+=value
        else:refunded+=value
    if refunded>paid:raise ValueError('MONEY_CONSERVATION_FAILURE')
    return dict(paid_total_fen=paid,refunded_total_fen=refunded,net_paid_fen=paid-refunded)
