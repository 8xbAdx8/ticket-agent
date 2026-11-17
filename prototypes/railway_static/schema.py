"""Only a new, separately located database may be created by the importer."""
TABLES = {
 'agency': ('source_agency', 'agency_id agency_name agency_url agency_timezone'),
 'stops': ('source_stations', 'stop_id stop_name stop_lat stop_lon location_type'),
 'routes': ('source_routes', 'route_id agency_id route_short_name route_type'),
 'trips': ('source_trips', 'route_id service_id trip_id trip_short_name trip_headsign shape_id'),
 'stop_times': ('source_stop_times', 'trip_id arrival_time departure_time stop_id stop_sequence'),
 'calendar_dates': ('source_calendar_dates', 'service_id date exception_type'),
 'shapes': ('source_shapes', 'shape_id shape_pt_lat shape_pt_lon shape_pt_sequence'),
 'translations': ('source_translations', 'table_name field_name language translation record_id'),
 'feed_info': ('source_feed_info', 'feed_publisher_name feed_publisher_url feed_lang feed_start_date feed_end_date feed_version'),
}

def create_schema(db):
    db.execute('CREATE TABLE source_metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)')
    for table, fields in TABLES.values():
        db.execute('CREATE TABLE '+table+' ('+','.join(f+' TEXT NOT NULL' for f in fields.split())+', raw_json TEXT NOT NULL)')
    db.executescript('''
      CREATE TABLE station_coordinate_quality(stop_id TEXT PRIMARY KEY, classification TEXT NOT NULL,
        source_sha256 TEXT NOT NULL, source_matches_json TEXT NOT NULL, shared_ids_json TEXT NOT NULL,
        independently_verified INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE trip_quarantine(trip_id TEXT NOT NULL, stop_sequence INTEGER NOT NULL,
        stop_id TEXT NOT NULL, reason TEXT NOT NULL, arrival_time TEXT NOT NULL,
        departure_time TEXT NOT NULL, source_sha256 TEXT NOT NULL, PRIMARY KEY(trip_id,stop_sequence));
      CREATE TABLE trip_aliases(alias TEXT NOT NULL,trip_id TEXT NOT NULL,valid_from TEXT NOT NULL,
        valid_to TEXT NOT NULL,verification_status TEXT NOT NULL,evidence_reference TEXT NOT NULL,
        source TEXT NOT NULL,PRIMARY KEY(alias,trip_id,valid_from));
      CREATE VIEW effective_trips AS SELECT t.* FROM source_trips t
        WHERE NOT EXISTS(SELECT 1 FROM trip_quarantine q WHERE q.trip_id=t.trip_id);
      CREATE VIEW effective_stop_times AS SELECT s.* FROM source_stop_times s
        JOIN effective_trips t ON s.trip_id=t.trip_id;
    ''')
