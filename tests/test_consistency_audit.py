from target.consistency_audit import LAYERS, audit_conversation, audit_operation


IDENTITY = dict(session_id='own', operation_id='op', order_id='order', proposal_id='proposal')


def observation(layer, state='PAID', **change):
    return dict(IDENTITY, layer=layer, order_status=state, evidence_ref=f'evidence#{layer}') | change


def test_four_matching_structured_layers_are_required():
    rows = [observation(layer) for layer in LAYERS]
    assert audit_operation(IDENTITY, rows)['status'] == 'passed'
    result = audit_operation(IDENTITY, rows[:-1] + [observation('UI', session_id='foreign')])
    assert result['status'] == 'indeterminate'
    assert result['missing_layers'] == ['UI']


def test_same_operation_different_order_and_proposal_never_join():
    rows = [observation('Business'), observation('UI', 'CANCELLED', order_id='other'),
            observation('Runtime', 'CANCELLED', proposal_id='other')]
    result = audit_operation(IDENTITY, rows)
    assert result['status'] == 'indeterminate'
    assert result['layers']['Business'][0]['status'] == 'PAID'
    assert not result['layers']['UI'] and not result['layers']['Runtime']


def test_conflicting_bound_states_fail_with_missing_other_layers():
    result = audit_operation(IDENTITY, [observation('Business'), observation('UI', 'PENDING_PAYMENT')])
    assert result['status'] == 'failed'
    assert set(result['missing_layers']) == {'Agent', 'Runtime'}


def test_runtime_and_ui_only_accept_their_own_events():
    receipt = dict(IDENTITY, source_run_id='chat', database_verified=True,
                   after=dict(order_id='order', order_status='PAID'),
                   actual_result=dict(order_id='order', status='PAID'))
    runtime = dict(IDENTITY, event_id='e1', event_type='business_operation_completed',
                   run_id='op', business_receipt=receipt)
    snapshot = dict(session_id='own', turns=[dict(run_id='chat', reply='订单 PAID')], receipts=[receipt],
                    operation_events=[runtime, dict(IDENTITY, event_id='e2', event_type='ui_operation_completed',
                                                    run_id='op', order_status='PAID')])
    row = audit_conversation(snapshot)[0]
    assert row['status'] == 'indeterminate'
    assert row['missing_layers'] == ['Agent', 'UI']
    assert row['layers']['Runtime'][0]['ref'].endswith('/actual_result')
    snapshot['operation_events'].append(runtime)
    assert 'Runtime' in audit_conversation(snapshot)[0]['missing_layers']
    snapshot['turns'] = [dict(run_id='another-run')]
    assert audit_conversation(snapshot) == []
