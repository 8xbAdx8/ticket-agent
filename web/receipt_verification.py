"""Classify native receipts using the existing owned committed read model."""
import copy

REJECTIONS={'CONFIRMATION_SECRET_LOST','PROPOSAL_EXPIRED','CONFIRMATION_USED','CONFIRMATION_INVALID'}

def assess(proposal,snapshot,native,*,exception=False,before=None):
    result=copy.deepcopy(native)
    operation=next((o for o in snapshot['operations'] if o['proposal_id']==proposal['proposal_id']),None)
    order=next((o for o in snapshot['orders'] if o['proposal_id']==proposal['proposal_id']),None) if proposal['action']=='CREATE_ORDER' else next((o for o in snapshot['orders'] if o['order_id']==proposal['order_id']),None)
    if operation and operation['database_verified']:
        # Native persisted receipt wins over an auxiliary/transport exception.
        result=copy.deepcopy(operation['actual_result'])
        return result,'SUCCEEDED',True
    if proposal['action']=='CREATE_ORDER' and order:
        from target.v39.receipt_proof import creation_proof
        if not creation_proof(order,proposal):
            return dict(result,order_id=order['order_id'],error='BUSINESS_INCONSISTENT',verification_status='PARTIAL'),'PARTIAL',False
        return dict(result,order_id=order['order_id'],error='DATABASE_RECEIPT_NOT_VERIFIED',verification_status='UNKNOWN'),'UNKNOWN',False
    if result.get('status')=='PROPOSAL_EXPIRED':
        return dict(result,error='DATABASE_RECEIPT_NOT_VERIFIED',failure_reason='PROPOSAL_EXPIRED',verification_status='FAILED'),'FAILED',False
    if result.get('status') in REJECTIONS:
        return dict(result,error=result['status'],verification_status='FAILED'),'FAILED',False
    if operation and operation['status']=='FAILED':
        return result,'FAILED',False
    # A completed read after a thrown transaction, with no order or receipt,
    # proves CREATE rolled back. A returned success without proof remains unknown.
    if exception and proposal['action']=='CREATE_ORDER' and order is None and not (operation or {}).get('actual_result'):
        return result,'FAILED',False
    if exception and before and snapshot['state_sha256']==before['state_sha256']:
        return result,'FAILED',False
    if result.get('error') and result.get('error')!='DATABASE_RECEIPT_NOT_VERIFIED' and not exception:
        return result,'FAILED',False
    return dict(result,error='DATABASE_RECEIPT_NOT_VERIFIED',verification_status='UNKNOWN'),'UNKNOWN',False
