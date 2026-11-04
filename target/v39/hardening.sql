-- Role-aware identity checks: NEW/RETAINED target the new quote;
-- RELEASED targets the old quote. Historical RELEASED rows cannot target the new train.
CREATE TRIGGER v39_hold_identity_insert BEFORE INSERT ON v39_hold_segments BEGIN
 SELECT RAISE(ABORT,'HOLD_IDENTITY_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_holds h JOIN v39_quotes q ON q.quote_id=h.quote_id
  WHERE h.hold_id=NEW.hold_id AND h.session_id=q.session_id AND h.owner_phone=q.owner_phone
   AND h.scenario_id=NEW.scenario_id AND q.dataset_version=NEW.dataset_version
   AND h.trip_id=NEW.trip_id AND h.service_date=NEW.service_date AND h.seat_class=NEW.seat_class
   AND NEW.segment_index>=q.origin_position AND NEW.segment_index<q.destination_position
   AND NEW.quantity=h.remaining_quantity
 );
 SELECT RAISE(ABORT,'RETAINED_SOURCE_SCOPE') WHERE NEW.inventory_role='RETAINED' AND NOT EXISTS (
  SELECT 1 FROM v39_holds dst JOIN v39_holds src ON src.hold_id=NEW.source_hold_id
  JOIN v39_orders o ON o.order_id=NEW.source_order_id
  JOIN v39_hold_segments s ON s.hold_id=src.hold_id
  WHERE dst.hold_id=NEW.hold_id AND dst.order_id=o.order_id AND src.order_id=o.order_id
   AND dst.owner_phone=o.owner_phone AND src.owner_phone=o.owner_phone
   AND o.hold_id=src.hold_id AND src.status='CONSUMED'
   AND s.scenario_id=NEW.scenario_id AND s.dataset_version=NEW.dataset_version
   AND s.trip_id=NEW.trip_id AND s.service_date=NEW.service_date AND s.seat_class=NEW.seat_class
   AND s.segment_index=NEW.segment_index AND s.quantity=NEW.quantity
   AND src.remaining_quantity=NEW.quantity
 );
END;

CREATE TRIGGER v39_hold_identity_update BEFORE UPDATE ON v39_hold_segments BEGIN
 SELECT RAISE(ABORT,'HOLD_SEGMENT_IDENTITY_IMMUTABLE') WHERE
  NEW.hold_id<>OLD.hold_id OR NEW.scenario_id<>OLD.scenario_id OR NEW.dataset_version<>OLD.dataset_version
  OR NEW.trip_id<>OLD.trip_id OR NEW.service_date<>OLD.service_date OR NEW.seat_class<>OLD.seat_class
  OR NEW.segment_index<>OLD.segment_index OR NEW.inventory_role<>OLD.inventory_role
  OR NEW.source_hold_id IS NOT OLD.source_hold_id OR NEW.source_order_id IS NOT OLD.source_order_id
  OR NEW.quantity>OLD.quantity;
END;
CREATE TRIGGER v39_hold_parent_update BEFORE UPDATE ON v39_holds BEGIN
 SELECT RAISE(ABORT,'HOLD_IDENTITY_IMMUTABLE') WHERE NEW.hold_id<>OLD.hold_id OR NEW.quote_id<>OLD.quote_id
  OR NEW.order_id IS NOT OLD.order_id OR NEW.change_id IS NOT OLD.change_id OR NEW.session_id<>OLD.session_id
  OR NEW.owner_phone<>OLD.owner_phone OR NEW.scenario_id<>OLD.scenario_id OR NEW.trip_id<>OLD.trip_id
  OR NEW.service_date<>OLD.service_date OR NEW.seat_class<>OLD.seat_class OR NEW.initial_quantity<>OLD.initial_quantity;
END;
CREATE TRIGGER v39_hold_delete BEFORE DELETE ON v39_holds BEGIN
 SELECT RAISE(ABORT,'HOLD_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER v39_rule_dataset_insert BEFORE INSERT ON v39_price_rules BEGIN
 SELECT RAISE(ABORT,'INVENTORY_IDENTITY_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_scenarios WHERE scenario_id=NEW.scenario_id AND dataset_version=NEW.dataset_version);
END;
CREATE TRIGGER v39_rule_dataset_update BEFORE UPDATE ON v39_price_rules BEGIN
 SELECT RAISE(ABORT,'INVENTORY_IDENTITY_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_scenarios WHERE scenario_id=NEW.scenario_id AND dataset_version=NEW.dataset_version);
END;
CREATE TRIGGER v39_inventory_dataset_insert BEFORE INSERT ON v39_inventory_segments BEGIN
 SELECT RAISE(ABORT,'INVENTORY_IDENTITY_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_scenarios WHERE scenario_id=NEW.scenario_id AND dataset_version=NEW.dataset_version);
END;
CREATE TRIGGER v39_order_identity_insert BEFORE INSERT ON v39_orders BEGIN
 SELECT RAISE(ABORT,'ORDER_IDENTITY_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_quotes q JOIN v39_holds h ON h.hold_id=NEW.hold_id AND h.quote_id=q.quote_id
  WHERE q.quote_id=NEW.quote_id AND q.scenario_id=NEW.scenario_id AND q.dataset_version=NEW.dataset_version
   AND q.owner_phone=NEW.owner_phone AND q.session_id=NEW.session_id AND h.order_id=NEW.order_id
   AND h.owner_phone=NEW.owner_phone AND h.session_id=NEW.session_id AND h.scenario_id=NEW.scenario_id
   AND q.trip_id=NEW.trip_id AND q.service_date=NEW.service_date AND q.seat_class=NEW.seat_class
   AND q.origin_stop_id=NEW.origin_stop_id AND q.destination_stop_id=NEW.destination_stop_id
   AND q.origin_position=NEW.origin_position AND q.destination_position=NEW.destination_position
 );
END;

CREATE TRIGGER v39_change_identity_insert BEFORE INSERT ON v39_change_segments BEGIN
 SELECT RAISE(ABORT,'CHANGE_IDENTITY_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_change_requests ch
  JOIN v39_quotes q ON q.quote_id=CASE WHEN NEW.role='RELEASED' THEN ch.old_quote_id ELSE ch.target_quote_id END
  JOIN v39_orders o ON o.order_id=ch.order_id
  WHERE ch.change_id=NEW.change_id AND q.scenario_id=NEW.scenario_id AND q.dataset_version=NEW.dataset_version
   AND q.trip_id=NEW.trip_id AND q.service_date=NEW.service_date AND q.seat_class=NEW.seat_class
   AND NEW.segment_index>=q.origin_position AND NEW.segment_index<q.destination_position
   AND o.active_item_count=NEW.quantity
 );
 SELECT RAISE(ABORT,'CHANGE_RETAINED_SCOPE') WHERE NEW.role='RETAINED' AND NOT EXISTS (
  SELECT 1 FROM v39_change_requests ch JOIN v39_holds src ON src.hold_id=ch.old_hold_id
  JOIN v39_orders o ON o.order_id=ch.order_id JOIN v39_hold_segments s ON s.hold_id=src.hold_id
  WHERE ch.change_id=NEW.change_id AND src.order_id=o.order_id AND o.hold_id=src.hold_id
   AND NEW.source_hold_id=src.hold_id AND NEW.source_order_id=o.order_id
   AND src.owner_phone=o.owner_phone AND src.status='CONSUMED'
   AND s.scenario_id=NEW.scenario_id AND s.dataset_version=NEW.dataset_version
   AND s.trip_id=NEW.trip_id AND s.service_date=NEW.service_date AND s.seat_class=NEW.seat_class
   AND s.segment_index=NEW.segment_index AND s.quantity=NEW.quantity AND src.remaining_quantity=NEW.quantity
 );
END;
CREATE TRIGGER v39_change_segments_immutable BEFORE UPDATE ON v39_change_segments BEGIN
 SELECT RAISE(ABORT,'CHANGE_SEGMENT_IMMUTABLE');
END;

CREATE TRIGGER v39_rule_overlap_insert BEFORE INSERT ON v39_price_rules WHEN NEW.status='ACTIVE' BEGIN
 SELECT RAISE(ABORT,'PRICE_RULE_TIME_INVALID') WHERE julianday(NEW.valid_from) IS NULL
  OR (NEW.valid_until IS NOT NULL AND (julianday(NEW.valid_until) IS NULL OR julianday(NEW.valid_until)<=julianday(NEW.valid_from)));
 SELECT RAISE(ABORT,'PRICE_RULE_OVERLAP_REJECTED') WHERE EXISTS (
  SELECT 1 FROM v39_price_rules r WHERE r.status='ACTIVE' AND r.rule_id=NEW.rule_id
   AND r.scenario_id=NEW.scenario_id AND r.dataset_version=NEW.dataset_version AND r.trip_id IS NEW.trip_id AND r.seat_class=NEW.seat_class
   AND julianday(r.valid_from)<COALESCE(julianday(NEW.valid_until),1e10)
   AND julianday(NEW.valid_from)<COALESCE(julianday(r.valid_until),1e10)
 );
END;
CREATE TRIGGER v39_rule_overlap_update BEFORE UPDATE ON v39_price_rules WHEN NEW.status='ACTIVE' BEGIN
 SELECT RAISE(ABORT,'PRICE_RULE_TIME_INVALID') WHERE julianday(NEW.valid_from) IS NULL
  OR (NEW.valid_until IS NOT NULL AND (julianday(NEW.valid_until) IS NULL OR julianday(NEW.valid_until)<=julianday(NEW.valid_from)));
 SELECT RAISE(ABORT,'PRICE_RULE_OVERLAP_REJECTED') WHERE EXISTS (
  SELECT 1 FROM v39_price_rules r WHERE r.status='ACTIVE' AND r.rule_id=NEW.rule_id
   AND NOT (r.rule_id=OLD.rule_id AND r.version=OLD.version)
   AND r.scenario_id=NEW.scenario_id AND r.dataset_version=NEW.dataset_version AND r.trip_id IS NEW.trip_id AND r.seat_class=NEW.seat_class
   AND julianday(r.valid_from)<COALESCE(julianday(NEW.valid_until),1e10)
   AND julianday(NEW.valid_from)<COALESCE(julianday(r.valid_until),1e10)
 );
END;
CREATE TRIGGER v39_refund_delete BEFORE DELETE ON v39_refund_requests BEGIN
 SELECT RAISE(ABORT,'REFUND_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER v39_refund_item_delete BEFORE DELETE ON v39_refund_items BEGIN
 SELECT RAISE(ABORT,'REFUND_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER v39_audit_update BEFORE UPDATE ON v39_audit_events BEGIN
 SELECT RAISE(ABORT,'AUDIT_IMMUTABLE');
END;
CREATE TRIGGER v39_audit_delete BEFORE DELETE ON v39_audit_events BEGIN
 SELECT RAISE(ABORT,'AUDIT_IMMUTABLE');
END;
CREATE TRIGGER v39_inventory_events_update BEFORE UPDATE ON v39_inventory_events BEGIN
 SELECT RAISE(ABORT,'AUDIT_IMMUTABLE');
END;
CREATE TRIGGER v39_inventory_events_delete BEFORE DELETE ON v39_inventory_events BEGIN
 SELECT RAISE(ABORT,'AUDIT_IMMUTABLE');
END;

CREATE TRIGGER v39_transaction_transition BEFORE UPDATE ON v39_transactions BEGIN
 SELECT RAISE(ABORT,'TRANSACTION_IMMUTABLE') WHERE OLD.status<>'PENDING';
 SELECT RAISE(ABORT,'TRANSACTION_IDENTITY_IMMUTABLE') WHERE NEW.transaction_id<>OLD.transaction_id
  OR NEW.order_id<>OLD.order_id OR NEW.transaction_type<>OLD.transaction_type
  OR NEW.refund_id IS NOT OLD.refund_id OR NEW.change_id IS NOT OLD.change_id
  OR NEW.direction<>OLD.direction OR NEW.amount_fen<>OLD.amount_fen OR NEW.idempotency_key<>OLD.idempotency_key
  OR NEW.request_hash<>OLD.request_hash OR NEW.provider<>OLD.provider;
 SELECT RAISE(ABORT,'REFUND_REQUEST_NOT_PENDING') WHERE NEW.status='SUCCEEDED' AND NEW.transaction_type='REFUND'
  AND NOT EXISTS (SELECT 1 FROM v39_refund_requests r WHERE r.refund_id=NEW.refund_id AND r.order_id=NEW.order_id
   AND r.status='PENDING' AND r.net_fen=NEW.amount_fen);
END;
CREATE TRIGGER v39_transaction_delete BEFORE DELETE ON v39_transactions WHEN OLD.status<>'PENDING' BEGIN
 SELECT RAISE(ABORT,'TRANSACTION_IMMUTABLE');
END;

CREATE TRIGGER v39_allocation_insert BEFORE INSERT ON v39_transaction_allocations BEGIN
 SELECT RAISE(ABORT,'ALLOCATION_TRANSACTION_SCOPE') WHERE NOT EXISTS (
  SELECT 1 FROM v39_transactions t WHERE t.transaction_id=NEW.transaction_id AND t.order_id=NEW.order_id
   AND t.change_id IS NEW.change_id AND t.status='PENDING'
 );
END;
CREATE TRIGGER v39_allocation_update BEFORE UPDATE ON v39_transaction_allocations BEGIN
 SELECT RAISE(ABORT,'ALLOCATION_IMMUTABLE') WHERE
  (SELECT status FROM v39_transactions WHERE transaction_id=OLD.transaction_id)<>'PENDING';
 SELECT RAISE(ABORT,'ALLOCATION_TRANSACTION_SCOPE') WHERE NOT EXISTS (
  SELECT 1 FROM v39_transactions t JOIN v39_order_items i ON i.item_id=NEW.order_item_id
  WHERE t.transaction_id=NEW.transaction_id AND t.order_id=NEW.order_id AND i.order_id=NEW.order_id
   AND t.change_id IS NEW.change_id AND t.status='PENDING'
   AND NEW.amount_fen+COALESCE((SELECT SUM(amount_fen) FROM v39_transaction_allocations
    WHERE transaction_id=NEW.transaction_id AND allocation_id<>OLD.allocation_id),0)<=t.amount_fen
 );
END;
CREATE TRIGGER v39_allocation_delete BEFORE DELETE ON v39_transaction_allocations BEGIN
 SELECT RAISE(ABORT,'ALLOCATION_IMMUTABLE') WHERE
  (SELECT status FROM v39_transactions WHERE transaction_id=OLD.transaction_id)<>'PENDING';
END;
CREATE TRIGGER v39_allocation_sum_insert AFTER INSERT ON v39_transaction_allocations BEGIN
 UPDATE v39_transactions SET allocated_fen=(SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=NEW.transaction_id) WHERE transaction_id=NEW.transaction_id;
END;
CREATE TRIGGER v39_allocation_sum_delete AFTER DELETE ON v39_transaction_allocations BEGIN
 UPDATE v39_transactions SET allocated_fen=(SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=OLD.transaction_id) WHERE transaction_id=OLD.transaction_id;
END;
CREATE TRIGGER v39_allocation_sum_update AFTER UPDATE ON v39_transaction_allocations BEGIN
 UPDATE v39_transactions SET allocated_fen=(SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=OLD.transaction_id) WHERE transaction_id=OLD.transaction_id;
 UPDATE v39_transactions SET allocated_fen=(SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=NEW.transaction_id) WHERE transaction_id=NEW.transaction_id AND NEW.transaction_id<>OLD.transaction_id;
END;

CREATE TRIGGER v39_refund_initial BEFORE INSERT ON v39_refund_requests WHEN NEW.status<>'PENDING' BEGIN
 SELECT RAISE(ABORT,'REFUND_MUST_START_PENDING');
END;
CREATE TRIGGER v39_refund_item_initial BEFORE INSERT ON v39_refund_items WHEN NEW.status<>'REQUESTED' BEGIN
 SELECT RAISE(ABORT,'REFUND_ITEM_MUST_START_REQUESTED');
END;
CREATE TRIGGER v39_refund_item_transition BEFORE UPDATE ON v39_refund_items BEGIN
 SELECT RAISE(ABORT,'REFUND_ITEM_IMMUTABLE') WHERE OLD.status<>'REQUESTED'
  OR NEW.refund_id<>OLD.refund_id OR NEW.order_id<>OLD.order_id OR NEW.order_item_id<>OLD.order_item_id
  OR NEW.amount_fen<>OLD.amount_fen OR NEW.fee_fen<>OLD.fee_fen OR NEW.net_fen<>OLD.net_fen;
 SELECT RAISE(ABORT,'REFUND_ITEM_SUCCESS_SCOPE') WHERE NEW.status='SUCCEEDED' AND NOT EXISTS (
  SELECT 1 FROM v39_refund_requests r JOIN v39_transactions t ON t.refund_id=r.refund_id AND t.order_id=r.order_id
  JOIN v39_order_items i ON i.item_id=NEW.order_item_id AND i.order_id=r.order_id
  WHERE r.refund_id=NEW.refund_id AND r.status='PENDING' AND t.status='SUCCEEDED'
   AND i.item_status='ACTIVE' AND i.fare_fen=NEW.amount_fen
   AND (SELECT COALESCE(SUM(a.amount_fen),0) FROM v39_transaction_allocations a
    WHERE a.transaction_id=t.transaction_id AND a.order_item_id=i.item_id)=NEW.net_fen
 );
END;
CREATE TRIGGER v39_refund_transition BEFORE UPDATE ON v39_refund_requests BEGIN
 SELECT RAISE(ABORT,'REFUND_IMMUTABLE') WHERE OLD.status<>'PENDING'
  OR NEW.refund_id<>OLD.refund_id OR NEW.order_id<>OLD.order_id OR NEW.requested_fen<>OLD.requested_fen
  OR NEW.refundable_fen<>OLD.refundable_fen OR NEW.fee_fen<>OLD.fee_fen OR NEW.net_fen<>OLD.net_fen;
 SELECT RAISE(ABORT,'REFUND_AGGREGATE_MISMATCH') WHERE NEW.status='SUCCEEDED' AND (
  NOT EXISTS (SELECT 1 FROM v39_transactions t WHERE t.refund_id=NEW.refund_id AND t.order_id=NEW.order_id AND t.status='SUCCEEDED' AND t.amount_fen=NEW.net_fen)
  OR EXISTS (SELECT 1 FROM v39_refund_items i WHERE i.refund_id=NEW.refund_id AND i.status<>'SUCCEEDED')
  OR COALESCE((SELECT SUM(amount_fen) FROM v39_refund_items WHERE refund_id=NEW.refund_id),0)<>NEW.requested_fen
  OR COALESCE((SELECT SUM(fee_fen) FROM v39_refund_items WHERE refund_id=NEW.refund_id),0)<>NEW.fee_fen
 );
 SELECT RAISE(ABORT,'REFUND_FAILURE_STATE_MISMATCH') WHERE NEW.status='FAILED' AND (
  EXISTS (SELECT 1 FROM v39_refund_items WHERE refund_id=NEW.refund_id AND status<>'FAILED')
  OR EXISTS (SELECT 1 FROM v39_transactions WHERE refund_id=NEW.refund_id AND status NOT IN ('FAILED','TIMEOUT'))
 );
END;
