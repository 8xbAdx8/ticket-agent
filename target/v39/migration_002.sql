-- V3.9.1 additive migration; immutable version 001 remains separately hashed.
ALTER TABLE v39_order_items ADD COLUMN price_quote_id TEXT REFERENCES v39_quotes(quote_id);
ALTER TABLE v39_refund_items ADD COLUMN price_quote_id TEXT REFERENCES v39_quotes(quote_id);
ALTER TABLE v39_inventory_events ADD COLUMN refund_id TEXT REFERENCES v39_refund_requests(refund_id);
CREATE TABLE v39_item_price_snapshots (
 item_id TEXT NOT NULL REFERENCES v39_order_items(item_id),
 quote_id TEXT NOT NULL REFERENCES v39_quotes(quote_id),
 quote_passenger_index INTEGER NOT NULL CHECK(quote_passenger_index>=0 AND quote_passenger_index<6),
 base_fen INTEGER NOT NULL CHECK(base_fen>=0),
 seat_fen INTEGER NOT NULL CHECK(seat_fen>=0),
 fixed_fee_share_fen INTEGER NOT NULL CHECK(fixed_fee_share_fen>=0),
 fare_fen INTEGER NOT NULL CHECK(fare_fen=seat_fen+fixed_fee_share_fen AND fare_fen>0),
 created_at TEXT NOT NULL,
 PRIMARY KEY(item_id,quote_id)
) STRICT;
CREATE TRIGGER v391_price_snapshot_scope BEFORE INSERT ON v39_item_price_snapshots BEGIN
 SELECT RAISE(ABORT,'ITEM_PRICE_SCOPE') WHERE NOT EXISTS (
  SELECT 1 FROM v39_order_items i JOIN v39_orders o ON o.order_id=i.order_id
  JOIN v39_quotes q ON q.quote_id=NEW.quote_id WHERE i.item_id=NEW.item_id
   AND q.session_id=o.session_id AND q.owner_phone=o.owner_phone AND q.scenario_id=o.scenario_id
   AND q.dataset_version=o.dataset_version AND NEW.quote_passenger_index<q.passenger_count
   AND NEW.base_fen=q.single_base_fen AND NEW.seat_fen=q.single_seat_fen
   AND NEW.fixed_fee_share_fen=(q.fixed_fee_fen/q.passenger_count)+(NEW.quote_passenger_index<q.fixed_fee_fen%q.passenger_count));
END;
CREATE TRIGGER v391_price_snapshot_update BEFORE UPDATE ON v39_item_price_snapshots BEGIN SELECT RAISE(ABORT,'ITEM_PRICE_IMMUTABLE'); END;
CREATE TRIGGER v391_price_snapshot_delete BEFORE DELETE ON v39_item_price_snapshots BEGIN SELECT RAISE(ABORT,'ITEM_PRICE_IMMUTABLE'); END;
CREATE TRIGGER v391_item_insert BEFORE INSERT ON v39_order_items BEGIN
 SELECT RAISE(ABORT,'ITEM_QUOTE_REQUIRED') WHERE NOT EXISTS (
  SELECT 1 FROM v39_orders o JOIN v39_quotes q ON q.quote_id=NEW.price_quote_id
  WHERE o.order_id=NEW.order_id AND q.session_id=o.session_id AND q.owner_phone=o.owner_phone
   AND q.scenario_id=o.scenario_id AND q.dataset_version=o.dataset_version);
END;
CREATE TRIGGER v391_item_update BEFORE UPDATE ON v39_order_items BEGIN
 SELECT RAISE(ABORT,'INACTIVE_ITEM_IMMUTABLE') WHERE OLD.item_status<>'ACTIVE';
 SELECT RAISE(ABORT,'ITEM_IDENTITY_IMMUTABLE') WHERE NEW.item_id<>OLD.item_id OR NEW.order_id<>OLD.order_id
  OR NEW.passenger_index<>OLD.passenger_index OR NEW.passenger_name<>OLD.passenger_name;
 SELECT RAISE(ABORT,'ITEM_PRICE_MISMATCH') WHERE NOT EXISTS (
  SELECT 1 FROM v39_item_price_snapshots s WHERE s.item_id=NEW.item_id AND s.quote_id=NEW.price_quote_id
   AND s.base_fen=NEW.base_fen AND s.seat_fen=NEW.seat_fen AND s.fixed_fee_share_fen=NEW.fixed_fee_share_fen AND s.fare_fen=NEW.fare_fen);
 SELECT RAISE(ABORT,'REFUND_SUCCESS_REQUIRED') WHERE NEW.item_status='REFUNDED' AND NOT EXISTS (
  SELECT 1 FROM v39_refund_items r JOIN v39_refund_requests q USING(refund_id)
   WHERE r.order_item_id=NEW.item_id AND r.status='SUCCEEDED' AND q.status='SUCCEEDED');
END;
DROP INDEX ux_proposal_pending;
CREATE UNIQUE INDEX ux_proposal_pending ON v39_proposals(session_id,action,aggregate_id)
 WHERE state='PENDING' AND action<>'REFUND';
DROP TRIGGER trg_refund_items_scope;
CREATE TRIGGER trg_refund_items_scope BEFORE INSERT ON v39_refund_items BEGIN
 SELECT RAISE(ABORT,'REFUND_ITEM_SCOPE') WHERE NOT EXISTS (
  SELECT 1 FROM v39_refund_requests r JOIN v39_order_items i ON i.item_id=NEW.order_item_id
  JOIN v39_item_price_snapshots s ON s.item_id=i.item_id AND s.quote_id=NEW.price_quote_id
  WHERE r.refund_id=NEW.refund_id AND r.order_id=NEW.order_id AND i.order_id=NEW.order_id
   AND i.item_status IN ('ACTIVE','REFUNDED') AND NEW.amount_fen=s.fare_fen);
END;
CREATE TRIGGER v391_refund_price_update BEFORE UPDATE ON v39_refund_items BEGIN
 SELECT RAISE(ABORT,'REFUND_PRICE_IMMUTABLE') WHERE NEW.price_quote_id IS NOT OLD.price_quote_id;
 SELECT RAISE(ABORT,'REFUND_PRICE_MISMATCH') WHERE NEW.status='SUCCEEDED' AND NOT EXISTS (
  SELECT 1 FROM v39_order_items i JOIN v39_item_price_snapshots s ON s.item_id=i.item_id AND s.quote_id=NEW.price_quote_id
  WHERE i.item_id=NEW.order_item_id AND i.item_status='ACTIVE' AND i.price_quote_id=NEW.price_quote_id
   AND i.fare_fen=s.fare_fen AND NEW.amount_fen=s.fare_fen);
END;
CREATE TRIGGER v391_refund_final_guard BEFORE UPDATE OF status ON v39_refund_requests
 WHEN NEW.status IN ('SUCCEEDED','FAILED') BEGIN
 SELECT RAISE(ABORT,'REFUND_FINAL_INCOMPLETE') WHERE
  NOT EXISTS (SELECT 1 FROM v39_transactions t WHERE t.refund_id=NEW.refund_id AND t.order_id=NEW.order_id
   AND t.transaction_type='REFUND' AND t.amount_fen=NEW.net_fen
   AND t.status=NEW.status AND t.allocated_fen=t.amount_fen
   AND (SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=t.transaction_id)=t.amount_fen)
  OR NOT EXISTS (SELECT 1 FROM v39_refund_items WHERE refund_id=NEW.refund_id)
  OR EXISTS (SELECT 1 FROM v39_refund_items WHERE refund_id=NEW.refund_id AND status<>NEW.status)
  OR (SELECT COALESCE(SUM(amount_fen),0) FROM v39_refund_items WHERE refund_id=NEW.refund_id)<>NEW.requested_fen
  OR (SELECT COALESCE(SUM(fee_fen),0) FROM v39_refund_items WHERE refund_id=NEW.refund_id)<>NEW.fee_fen
  OR (SELECT COALESCE(SUM(net_fen),0) FROM v39_refund_items WHERE refund_id=NEW.refund_id)<>NEW.net_fen;
END;
