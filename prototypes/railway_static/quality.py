"""Deterministic integrity and coordinate-origin checks; no geodetic claims."""
import csv, json, hashlib
from collections import defaultdict
from .models import SHA256

def scalar(db, sql): return db.execute(sql).fetchone()[0]

def coordinates(db, path):
    by_name = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f): by_name[row['station_name']].append(row)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = list(db.execute('SELECT stop_id,stop_name,stop_lat,stop_lon FROM source_stations'))
    shared = defaultdict(list)
    for sid, name, lat, lon in rows: shared[(lat,lon)].append(sid)
    for sid, name, lat, lon in rows:
        matches = by_name.get(name, [])
        state = 'UNVERIFIED_DERIVED' if not matches else 'SOURCE_TABLE_MATCHED'
        db.execute('INSERT INTO station_coordinate_quality VALUES (?,?,?,?,?,0)',
                   (sid,state,source_hash,json.dumps(matches,ensure_ascii=False),json.dumps(shared[(lat,lon)])))

def assess(db):
    fk = {}
    for a,k,b,bk in [('source_trips','route_id','source_routes','route_id'),('source_routes','agency_id','source_agency','agency_id'),
       ('source_stop_times','trip_id','source_trips','trip_id'),('source_stop_times','stop_id','source_stations','stop_id'),
       ('source_trips','service_id','source_calendar_dates','service_id'),('source_trips','shape_id','source_shapes','shape_id')]:
        fk[a+'.'+k] = scalar(db,f"SELECT count(*) FROM {a} a WHERE a.{k}<>'' AND NOT EXISTS(SELECT 1 FROM {b} b WHERE a.{k}=b.{bk})")
    duplicate_keys = {}
    for t,k in [('source_stations','stop_id'),('source_trips','trip_id'),('source_routes','route_id'),
                ('source_stop_times','trip_id,stop_sequence'),('source_calendar_dates','service_id,date'),('source_shapes','shape_id,shape_pt_sequence')]:
        duplicate_keys[t] = scalar(db,f'SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM {t} GROUP BY {k} HAVING count(*)>1)')
    counts = {k:scalar(db,'SELECT count(*) FROM '+t) for k,t in {
      'raw_trips':'source_trips','raw_stops':'source_stop_times','stations':'source_stations',
      'anomalous_records':'trip_quarantine','effective_trips':'effective_trips','effective_stops':'effective_stop_times'}.items()}
    counts.update(quarantined_trips=scalar(db,'SELECT count(DISTINCT trip_id) FROM trip_quarantine'),
      unverified_coordinates=scalar(db,"SELECT count(*) FROM station_coordinate_quality WHERE classification='UNVERIFIED_DERIVED'"),
      missing_shapes=scalar(db,"SELECT count(*) FROM source_trips WHERE shape_id=''"),
      duplicate_station_names=scalar(db,'SELECT count(*) FROM (SELECT stop_name FROM source_stations GROUP BY stop_name HAVING count(*)>1)'),
      shared_coordinate_groups=scalar(db,'SELECT count(*) FROM (SELECT stop_lat,stop_lon FROM source_stations GROUP BY stop_lat,stop_lon HAVING count(*)>1)'),
      aliases=scalar(db,'SELECT count(*) FROM trip_aliases'))
    leakage=scalar(db,'SELECT count(*) FROM effective_stop_times s JOIN trip_quarantine q ON s.trip_id=q.trip_id')
    return dict(counts=counts, foreign_keys=fk, duplicate_keys=duplicate_keys,
                quarantine_leaked_stop_rows=leakage, rights_status='RIGHTS_REVIEW_PENDING', usage_scope='LOCAL_DEMO_ONLY')
