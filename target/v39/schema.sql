-- Ticket Agent V3.9 executable migration 001; derived from immutable V1.2.2.
-- Runtime executes statements individually inside an explicit transaction.
-- Target: independent application-shared V3.9 SQLite, not data/tickets.db.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE v39_schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  checksum TEXT NOT NULL

) STRICT;

CREATE TABLE v39_worker_lease (
  slot INTEGER NOT NULL DEFAULT 1 UNIQUE CHECK(slot=1),
  worker_id TEXT PRIMARY KEY,
  boot_epoch TEXT NOT NULL,
  lease_until TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','RELEASED'))
) STRICT;

CREATE TABLE v39_scenarios (
  scenario_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  seed INTEGER NOT NULL,
  dataset_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','ARCHIVED')),
  config_json TEXT NOT NULL,
  created_at TEXT NOT NULL

) STRICT;

CREATE TABLE v39_price_rules (
  rule_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  trip_id TEXT,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  base_fen_per_segment INTEGER NOT NULL CHECK (base_fen_per_segment > 0),
  seat_multiplier_bp INTEGER NOT NULL CHECK (seat_multiplier_bp > 0),
  fixed_fee_fen INTEGER NOT NULL DEFAULT 0 CHECK (fixed_fee_fen >= 0),
  priority INTEGER NOT NULL DEFAULT 0,
  valid_from TEXT NOT NULL,
  valid_until TEXT,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','INACTIVE')),
  PRIMARY KEY (rule_id, version),
  UNIQUE (scenario_id, dataset_version, rule_id, version),
  FOREIGN KEY (scenario_id) REFERENCES v39_scenarios(scenario_id)

) STRICT;
CREATE UNIQUE INDEX ux_price_rule_scope
  ON v39_price_rules(scenario_id, dataset_version, COALESCE(trip_id,''), seat_class, priority, valid_from) WHERE status='ACTIVE';

CREATE TABLE v39_inventory_segments (
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
  from_stop_id TEXT NOT NULL,
  from_sequence INTEGER NOT NULL CHECK (from_sequence >= 1),
  from_position INTEGER NOT NULL CHECK (from_position >= 0),
  to_stop_id TEXT NOT NULL,
  to_sequence INTEGER NOT NULL CHECK (to_sequence >= 1),
  to_position INTEGER NOT NULL CHECK (to_position >= 0),
  capacity INTEGER NOT NULL CHECK (capacity >= 0),
  held INTEGER NOT NULL DEFAULT 0 CHECK (held >= 0),
  sold INTEGER NOT NULL DEFAULT 0 CHECK (sold >= 0),
  version INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index),
  FOREIGN KEY (scenario_id) REFERENCES v39_scenarios(scenario_id),
  CHECK (from_position < to_position),
  CHECK (from_position + 1 = to_position),
  CHECK (held + sold <= capacity)

) STRICT;
CREATE INDEX ix_inventory_lookup
  ON v39_inventory_segments(scenario_id, trip_id, service_date, seat_class);

CREATE TABLE v39_quotes (
  quote_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  owner_phone TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  origin_stop_id TEXT NOT NULL,
  destination_stop_id TEXT NOT NULL,
  origin_sequence INTEGER NOT NULL CHECK (origin_sequence >= 1),
  destination_sequence INTEGER NOT NULL CHECK (destination_sequence >= 1),
  origin_position INTEGER NOT NULL CHECK (origin_position >= 0),
  destination_position INTEGER NOT NULL CHECK (destination_position >= 0),
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  passenger_count INTEGER NOT NULL CHECK (passenger_count BETWEEN 1 AND 6),
  rule_id TEXT NOT NULL,
  rule_version INTEGER NOT NULL,
  base_fen_per_segment INTEGER NOT NULL CHECK (base_fen_per_segment > 0),
  seat_multiplier_bp INTEGER NOT NULL CHECK (seat_multiplier_bp > 0),
  fixed_fee_fen INTEGER NOT NULL DEFAULT 0 CHECK (fixed_fee_fen >= 0),
  segment_count INTEGER NOT NULL CHECK (segment_count > 0),
  single_base_fen INTEGER NOT NULL CHECK (single_base_fen >= 0),
  single_seat_fen INTEGER NOT NULL CHECK (single_seat_fen >= 0),
  base_total_fen INTEGER NOT NULL CHECK (base_total_fen >= 0),
  seat_total_fen INTEGER NOT NULL CHECK (seat_total_fen >= 0),
  total_fen INTEGER NOT NULL CHECK (total_fen >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  quote_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','EXPIRED','CONSUMED')),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (scenario_id) REFERENCES v39_scenarios(scenario_id),
  FOREIGN KEY (scenario_id, dataset_version, rule_id, rule_version)
    REFERENCES v39_price_rules(scenario_id, dataset_version, rule_id, version),
  CHECK (origin_position < destination_position),
  CHECK (segment_count = destination_position - origin_position)

) STRICT;
CREATE INDEX ix_quotes_owner ON v39_quotes(owner_phone, session_id, status, expires_at);
CREATE INDEX ix_quotes_trip ON v39_quotes(scenario_id, trip_id, service_date);

CREATE TABLE v39_holds (
  hold_id TEXT PRIMARY KEY,
  quote_id TEXT NOT NULL,
  order_id TEXT,
  change_id TEXT,
  session_id TEXT NOT NULL,
  owner_phone TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 6),
  initial_quantity INTEGER NOT NULL CHECK (initial_quantity BETWEEN 1 AND 6),
  remaining_quantity INTEGER NOT NULL CHECK (remaining_quantity BETWEEN 0 AND 6),
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','CONSUMED','RELEASED','EXPIRED','CHANGED','REFUNDED')),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  released_at TEXT,
  version INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (quote_id) REFERENCES v39_quotes(quote_id),
  FOREIGN KEY (scenario_id) REFERENCES v39_scenarios(scenario_id),
  CHECK (remaining_quantity <= initial_quantity),
  CHECK (quantity <= initial_quantity)

) STRICT;
CREATE INDEX ix_holds_expiry ON v39_holds(status, expires_at);
CREATE INDEX ix_holds_owner ON v39_holds(owner_phone, status);

CREATE TABLE v39_hold_segments (
  hold_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 6),
  inventory_role TEXT NOT NULL CHECK (inventory_role IN ('NEW','RETAINED')),
  source_hold_id TEXT,
  source_order_id TEXT,
  PRIMARY KEY (hold_id, scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index),
  FOREIGN KEY (hold_id) REFERENCES v39_holds(hold_id) ON DELETE CASCADE,
  FOREIGN KEY (source_hold_id) REFERENCES v39_holds(hold_id),
  FOREIGN KEY (source_order_id) REFERENCES v39_orders(order_id),
  FOREIGN KEY (scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index)
    REFERENCES v39_inventory_segments(scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index),
  CHECK (inventory_role <> 'RETAINED' OR (source_hold_id IS NOT NULL AND source_order_id IS NOT NULL))

) STRICT;

CREATE TABLE v39_proposals (
  proposal_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  owner_phone TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('CREATE_ORDER','PAY','CANCEL','REFUND','CHANGE')),
  aggregate_id TEXT,
  quote_id TEXT,
  order_id TEXT,
  scenario_id TEXT NOT NULL,
  execution_mode TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  write_policy_hash TEXT NOT NULL,
  feature_flag TEXT NOT NULL,
  baseline_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  tool_whitelist_hash TEXT NOT NULL,
  config_revision INTEGER NOT NULL,
  confirmation_owner_worker TEXT,
  confirmation_boot_epoch TEXT,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING','CONFIRMED','CANCELLED','EXPIRED','SECRET_LOST')),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  consumed_at TEXT,
  FOREIGN KEY (scenario_id) REFERENCES v39_scenarios(scenario_id),
  FOREIGN KEY (quote_id) REFERENCES v39_quotes(quote_id),
  UNIQUE (session_id, action, idempotency_key)

) STRICT;
CREATE UNIQUE INDEX ux_proposal_pending
  ON v39_proposals(session_id, action, COALESCE(aggregate_id,''), state)
  WHERE state='PENDING';
CREATE INDEX ix_proposals_expiry ON v39_proposals(state, expires_at);

CREATE TABLE v39_orders (
  order_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  owner_phone TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  hold_id TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  origin_stop_id TEXT NOT NULL,
  destination_stop_id TEXT NOT NULL,
  origin_sequence INTEGER NOT NULL CHECK (origin_sequence >= 1),
  destination_sequence INTEGER NOT NULL CHECK (destination_sequence >= 1),
  origin_position INTEGER NOT NULL,
  destination_position INTEGER NOT NULL,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  passenger_count INTEGER NOT NULL CHECK (passenger_count BETWEEN 1 AND 6),
  initial_passenger_count INTEGER NOT NULL CHECK (initial_passenger_count BETWEEN 1 AND 6),
  active_item_count INTEGER NOT NULL DEFAULT 0 CHECK (active_item_count >= 0),
  refunded_item_count INTEGER NOT NULL DEFAULT 0 CHECK (refunded_item_count >= 0),
  total_fen INTEGER NOT NULL CHECK (total_fen >= 0),
  paid_total_fen INTEGER NOT NULL DEFAULT 0 CHECK (paid_total_fen >= 0),
  refunded_total_fen INTEGER NOT NULL DEFAULT 0 CHECK (refunded_total_fen >= 0),
  fee_total_fen INTEGER NOT NULL DEFAULT 0 CHECK (fee_total_fen >= 0),
  net_paid_fen INTEGER NOT NULL DEFAULT 0 CHECK (net_paid_fen >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  order_status TEXT NOT NULL CHECK (order_status IN
    ('PENDING_PAYMENT','PAID','CHANGED','CANCELLED','EXPIRED','PAYMENT_FAILED')),
  payment_status TEXT NOT NULL CHECK (payment_status IN
    ('UNPAID','PENDING','SUCCEEDED','FAILED','TIMEOUT')),
  refund_status TEXT NOT NULL CHECK (refund_status IN
    ('NONE','REQUESTED','SUCCEEDED','FAILED')),
  change_status TEXT NOT NULL CHECK (change_status IN
    ('NONE','REQUESTED','SUCCEEDED','FAILED')),
  change_count INTEGER NOT NULL DEFAULT 0 CHECK (change_count BETWEEN 0 AND 1),
  policy_profile TEXT NOT NULL DEFAULT 'D9_PENDING' CHECK (policy_profile IN ('D9_PENDING','P02_STRICT','CHANGED_REFUND_P01')),
  idempotency_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (proposal_id) REFERENCES v39_proposals(proposal_id),
  FOREIGN KEY (scenario_id) REFERENCES v39_scenarios(scenario_id),
  FOREIGN KEY (quote_id) REFERENCES v39_quotes(quote_id),
  FOREIGN KEY (hold_id) REFERENCES v39_holds(hold_id),
  UNIQUE (session_id, idempotency_key),
  UNIQUE (proposal_id),
  UNIQUE (quote_id),
  UNIQUE (hold_id),
  CHECK (origin_position < destination_position),
  CHECK (active_item_count + refunded_item_count <= initial_passenger_count)

) STRICT;
CREATE INDEX ix_orders_owner ON v39_orders(owner_phone, created_at DESC);
CREATE INDEX ix_orders_state ON v39_orders(order_status, expires_at);

CREATE TABLE v39_order_items (
  item_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  passenger_index INTEGER NOT NULL CHECK (passenger_index BETWEEN 0 AND 5),
  passenger_name TEXT NOT NULL,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  base_fen INTEGER NOT NULL CHECK (base_fen >= 0),
  seat_fen INTEGER NOT NULL CHECK (seat_fen >= 0),
  fixed_fee_share_fen INTEGER NOT NULL CHECK (fixed_fee_share_fen >= 0),
  fare_fen INTEGER NOT NULL CHECK (fare_fen >= 0),
  item_status TEXT NOT NULL CHECK (item_status IN ('ACTIVE','REFUNDED','SUPERSEDED')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (order_id) REFERENCES v39_orders(order_id) ON DELETE CASCADE,
  UNIQUE (order_id, passenger_index),
  UNIQUE (order_id, item_id),
  CHECK (fare_fen = seat_fen + fixed_fee_share_fen)

) STRICT;
CREATE INDEX ix_order_items_order ON v39_order_items(order_id);

CREATE TABLE v39_order_snapshots (
  order_id TEXT NOT NULL,
  snapshot_version INTEGER NOT NULL,
  static_snapshot_json TEXT NOT NULL,
  price_snapshot_json TEXT NOT NULL,
  quote_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (order_id, snapshot_version),
  FOREIGN KEY (order_id) REFERENCES v39_orders(order_id) ON DELETE CASCADE

) STRICT;

CREATE TABLE v39_transactions (
  transaction_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  change_id TEXT,
  refund_id TEXT,
  transaction_type TEXT NOT NULL CHECK (transaction_type IN
    ('PAYMENT','CHANGE_SUPPLEMENT','CHANGE_REFUND','REFUND')),
  direction TEXT NOT NULL CHECK (direction IN ('DEBIT','CREDIT')),
  amount_fen INTEGER NOT NULL CHECK (amount_fen > 0),
  allocated_fen INTEGER NOT NULL DEFAULT 0 CHECK (allocated_fen >= 0),
  status TEXT NOT NULL CHECK (status IN ('PENDING','SUCCEEDED','FAILED','TIMEOUT')),
  failure_code TEXT,
  provider TEXT NOT NULL DEFAULT 'SIMULATED' CHECK (provider='SIMULATED'),
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY (order_id) REFERENCES v39_orders(order_id),
  FOREIGN KEY (change_id, order_id) REFERENCES v39_change_requests(change_id, order_id),
  FOREIGN KEY (refund_id, order_id) REFERENCES v39_refund_requests(refund_id, order_id),
  UNIQUE (order_id, transaction_type, idempotency_key),
  UNIQUE (transaction_id, order_id),
  CHECK ((transaction_type IN ('PAYMENT','CHANGE_SUPPLEMENT') AND direction='DEBIT') OR (transaction_type IN ('CHANGE_REFUND','REFUND') AND direction='CREDIT')),
  CHECK ((transaction_type='PAYMENT' AND refund_id IS NULL AND change_id IS NULL AND direction='DEBIT') OR
         (transaction_type='REFUND' AND refund_id IS NOT NULL AND change_id IS NULL AND direction='CREDIT') OR
         (transaction_type='CHANGE_SUPPLEMENT' AND change_id IS NOT NULL AND refund_id IS NULL AND direction='DEBIT') OR
         (transaction_type='CHANGE_REFUND' AND change_id IS NOT NULL AND refund_id IS NULL AND direction='CREDIT'))

) STRICT;
CREATE INDEX ix_transactions_order ON v39_transactions(order_id, created_at);
CREATE INDEX ix_transactions_change ON v39_transactions(change_id, created_at);
CREATE UNIQUE INDEX ux_transactions_refund_success
  ON v39_transactions(refund_id) WHERE refund_id IS NOT NULL AND status='SUCCEEDED';

CREATE TABLE v39_transaction_allocations (
  allocation_id TEXT PRIMARY KEY,
  transaction_id TEXT NOT NULL,
  order_id TEXT NOT NULL,
  order_item_id TEXT,
  change_id TEXT,
  amount_fen INTEGER NOT NULL CHECK (amount_fen >= 0),
  FOREIGN KEY (transaction_id, order_id) REFERENCES v39_transactions(transaction_id, order_id) ON DELETE CASCADE,
  FOREIGN KEY (order_id, order_item_id) REFERENCES v39_order_items(order_id, item_id),
  FOREIGN KEY (change_id) REFERENCES v39_change_requests(change_id)

) STRICT;
CREATE INDEX ix_alloc_transaction ON v39_transaction_allocations(transaction_id);

CREATE TABLE v39_refund_requests (
  refund_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('FULL','ITEMS')),
  requested_fen INTEGER NOT NULL CHECK (requested_fen >= 0),
  refundable_fen INTEGER NOT NULL CHECK (refundable_fen >= 0),
  fee_fen INTEGER NOT NULL DEFAULT 0 CHECK (fee_fen >= 0),
  net_fen INTEGER NOT NULL CHECK (net_fen >= 0),
  status TEXT NOT NULL CHECK (status IN ('PENDING','SUCCEEDED','FAILED')),
  prior_order_status TEXT NOT NULL,
  prior_total_fen INTEGER NOT NULL CHECK (prior_total_fen >= 0),
  reason TEXT,
  failure_code TEXT,
  idempotency_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY (order_id) REFERENCES v39_orders(order_id),
  UNIQUE (order_id, idempotency_key),
  UNIQUE (refund_id, order_id),
  CHECK (requested_fen = fee_fen + net_fen)

) STRICT;
CREATE INDEX ix_refund_requests_order ON v39_refund_requests(order_id, created_at);

CREATE TABLE v39_refund_items (
  refund_id TEXT NOT NULL,
  order_id TEXT NOT NULL,
  order_item_id TEXT NOT NULL,
  amount_fen INTEGER NOT NULL CHECK (amount_fen >= 0),
  fee_fen INTEGER NOT NULL DEFAULT 0 CHECK (fee_fen >= 0),
  net_fen INTEGER NOT NULL CHECK (net_fen >= 0),
  status TEXT NOT NULL CHECK (status IN ('REQUESTED','SUCCEEDED','FAILED')),
  PRIMARY KEY (refund_id, order_item_id),
  FOREIGN KEY (refund_id, order_id) REFERENCES v39_refund_requests(refund_id, order_id),
  FOREIGN KEY (order_id, order_item_id) REFERENCES v39_order_items(order_id, item_id),
  CHECK (amount_fen = fee_fen + net_fen)
) STRICT;
CREATE UNIQUE INDEX ux_refund_item_success
  ON v39_refund_items(order_item_id) WHERE status='SUCCEEDED';
CREATE TABLE v39_change_requests (
  change_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  old_hold_id TEXT NOT NULL,
  new_hold_id TEXT,
  old_quote_id TEXT NOT NULL,
  target_quote_id TEXT NOT NULL,
  target_trip_id TEXT NOT NULL,
  target_service_date TEXT NOT NULL,
  target_origin_stop_id TEXT NOT NULL,
  target_destination_stop_id TEXT NOT NULL,
  target_origin_position INTEGER NOT NULL,
  target_destination_position INTEGER NOT NULL,
  target_seat_class TEXT NOT NULL CHECK (target_seat_class IN ('SECOND','FIRST','BUSINESS')),
  difference_fen INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','CONFIRMED','REJECTED','FAILED')),
  prior_order_status TEXT NOT NULL,
  prior_total_fen INTEGER NOT NULL CHECK (prior_total_fen >= 0),
  failure_code TEXT,
  idempotency_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY (order_id) REFERENCES v39_orders(order_id),
  FOREIGN KEY (old_hold_id) REFERENCES v39_holds(hold_id),
  FOREIGN KEY (new_hold_id) REFERENCES v39_holds(hold_id),
  FOREIGN KEY (old_quote_id) REFERENCES v39_quotes(quote_id),
  FOREIGN KEY (target_quote_id) REFERENCES v39_quotes(quote_id),
  UNIQUE (order_id, idempotency_key),
  UNIQUE (change_id, order_id)
) STRICT;
CREATE INDEX ix_changes_order ON v39_change_requests(order_id, created_at);

CREATE TABLE v39_change_segments (
  change_id TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  seat_class TEXT NOT NULL CHECK (seat_class IN ('SECOND','FIRST','BUSINESS')),
  segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
  role TEXT NOT NULL CHECK (role IN ('RETAINED','NEW','RELEASED')),
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 6),
  source_hold_id TEXT,
  source_order_id TEXT,
  PRIMARY KEY (change_id, scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index),
  FOREIGN KEY (change_id) REFERENCES v39_change_requests(change_id) ON DELETE CASCADE,
  FOREIGN KEY (source_hold_id) REFERENCES v39_holds(hold_id),
  FOREIGN KEY (source_order_id) REFERENCES v39_orders(order_id),
  FOREIGN KEY (scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index)
    REFERENCES v39_inventory_segments(scenario_id, dataset_version, trip_id, service_date, seat_class, segment_index),
  CHECK (role <> 'RETAINED' OR (source_hold_id IS NOT NULL AND source_order_id IS NOT NULL))

) STRICT;

CREATE TABLE v39_confirmation_tokens (
  token_hash TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL,
  owner_worker_id TEXT NOT NULL,
  owner_boot_epoch TEXT NOT NULL,
  secret_version INTEGER NOT NULL DEFAULT 1,
  session_id TEXT NOT NULL,
  owner_phone TEXT NOT NULL,
  action TEXT NOT NULL,
  aggregate_id TEXT,
  quote_id TEXT,
  amount_fen INTEGER,
  args_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  invalidated_at TEXT,
  invalid_reason TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (proposal_id) REFERENCES v39_proposals(proposal_id),
  UNIQUE (proposal_id)

) STRICT;

CREATE TABLE v39_idempotency (
  scope TEXT NOT NULL,
  key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('SUCCEEDED','FAILED')),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  PRIMARY KEY (scope, key)

) STRICT;

CREATE TABLE v39_inventory_events (
  event_id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  trip_id TEXT NOT NULL,
  service_date TEXT NOT NULL,
  seat_class TEXT NOT NULL,
  segment_index INTEGER NOT NULL,
  delta_held INTEGER NOT NULL,
  delta_sold INTEGER NOT NULL,
  hold_id TEXT,
  order_id TEXT,
  change_id TEXT,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL

) STRICT;
CREATE INDEX ix_inventory_events_scope
  ON v39_inventory_events(scenario_id, trip_id, service_date, seat_class);

CREATE TABLE v39_audit_events (
  event_id TEXT PRIMARY KEY,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT,
  detail_json TEXT NOT NULL,
  request_id TEXT,
  created_at TEXT NOT NULL

) STRICT;
CREATE INDEX ix_audit_aggregate ON v39_audit_events(aggregate_type, aggregate_id, created_at);

CREATE TRIGGER trg_refund_items_scope
BEFORE INSERT ON v39_refund_items
BEGIN
  SELECT RAISE(ABORT,'REFUND_ITEM_SCOPE')
  WHERE NOT EXISTS (
    SELECT 1 FROM v39_refund_requests r
    JOIN v39_order_items i ON i.item_id=NEW.order_item_id
    WHERE r.refund_id=NEW.refund_id AND r.order_id=NEW.order_id
      AND i.order_id=NEW.order_id AND i.item_status='ACTIVE'
      AND NEW.amount_fen <= i.fare_fen
  );
END;

CREATE TRIGGER trg_transactions_refund_scope
BEFORE INSERT ON v39_transactions
WHEN NEW.transaction_type='REFUND'
BEGIN
  SELECT RAISE(ABORT,'REFUND_TRANSACTION_SCOPE')
  WHERE NOT EXISTS (
    SELECT 1 FROM v39_refund_requests r
    WHERE r.refund_id=NEW.refund_id AND r.order_id=NEW.order_id
      AND NEW.amount_fen <= r.net_fen
  );
END;

CREATE TRIGGER trg_allocations_scope
BEFORE INSERT ON v39_transaction_allocations
BEGIN
  SELECT RAISE(ABORT,'ALLOCATION_SCOPE')
  WHERE NOT EXISTS (
    SELECT 1 FROM v39_transactions t
    JOIN v39_order_items i ON i.item_id=NEW.order_item_id
    WHERE t.transaction_id=NEW.transaction_id AND t.order_id=NEW.order_id
      AND i.order_id=NEW.order_id
  )
  OR ((SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=NEW.transaction_id)+NEW.amount_fen)
     > (SELECT amount_fen FROM v39_transactions WHERE transaction_id=NEW.transaction_id);
END;

CREATE TRIGGER trg_transactions_alloc_complete
BEFORE UPDATE OF status ON v39_transactions
WHEN NEW.status='SUCCEEDED'
BEGIN
  SELECT RAISE(ABORT,'ALLOCATION_SUM_MISMATCH')
  WHERE NEW.allocated_fen <> NEW.amount_fen
     OR (SELECT COALESCE(SUM(amount_fen),0) FROM v39_transaction_allocations WHERE transaction_id=NEW.transaction_id) <> NEW.amount_fen;
END;

CREATE TRIGGER trg_retained_owner_scope
BEFORE INSERT ON v39_hold_segments
WHEN NEW.inventory_role='RETAINED'
BEGIN
  SELECT RAISE(ABORT,'RETAINED_SOURCE_SCOPE')
  WHERE NOT EXISTS (
    SELECT 1 FROM v39_holds h
    JOIN v39_orders o ON o.order_id=NEW.source_order_id
    WHERE h.hold_id=NEW.source_hold_id
      AND h.order_id=o.order_id
      AND h.owner_phone=o.owner_phone
      AND h.scenario_id=NEW.scenario_id
      AND o.dataset_version=NEW.dataset_version
      AND h.trip_id=NEW.trip_id
      AND h.service_date=NEW.service_date
      AND h.seat_class=NEW.seat_class
      AND EXISTS (SELECT 1 FROM v39_hold_segments hs WHERE hs.hold_id=h.hold_id AND hs.segment_index=NEW.segment_index)
  );
END;

CREATE TRIGGER trg_transactions_must_start_pending
BEFORE INSERT ON v39_transactions
WHEN NEW.status<>'PENDING'
BEGIN
  SELECT RAISE(ABORT,'TRANSACTION_MUST_START_PENDING');
END;

CREATE TRIGGER trg_change_retained_owner_scope
BEFORE INSERT ON v39_change_segments
WHEN NEW.role='RETAINED'
BEGIN
  SELECT RAISE(ABORT,'RETAINED_SOURCE_SCOPE')
  WHERE NOT EXISTS (
    SELECT 1 FROM v39_holds h
    JOIN v39_orders o ON o.order_id=NEW.source_order_id
    WHERE h.hold_id=NEW.source_hold_id
      AND h.order_id=o.order_id
      AND h.owner_phone=o.owner_phone
      AND h.scenario_id=NEW.scenario_id
      AND o.dataset_version=NEW.dataset_version
      AND h.trip_id=NEW.trip_id
      AND h.service_date=NEW.service_date
      AND h.seat_class=NEW.seat_class
      AND EXISTS (SELECT 1 FROM v39_hold_segments hs WHERE hs.hold_id=h.hold_id AND hs.segment_index=NEW.segment_index)
  );
END;
