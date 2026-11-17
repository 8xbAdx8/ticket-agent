"""Offline importer; no existing database or source file is opened for writing."""
import csv,io,json,hashlib,sqlite3,zipfile
from datetime import datetime,timezone
from pathlib import Path
from .models import ROOT,SOURCE,SHA256,COMMIT,RELEASE
from .schema import TABLES,create_schema
from .quarantine import isolate
from .quality import coordinates,assess
from .calendar import parse_time,parse_day

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_archive(path):
    if path.stat().st_size!=62375903 or sha(path)!=SHA256:
        raise ValueError('SOURCE_IDENTITY_MISMATCH')
    with zipfile.ZipFile(path) as z:
        if set(z.namelist()) != {n+'.txt' for n in TABLES} or z.testzip() is not None:
            raise ValueError('INVALID_ARCHIVE')

def import_dataset(destination):
    destination=Path(destination).resolve()
    if not destination.is_relative_to((ROOT/'artifacts/runtime').resolve()) or destination.exists():
        raise ValueError('NEW_ISOLATED_RUNTIME_DATABASE_REQUIRED')
    original=SOURCE/'output_gtfs.zip';validate_archive(original)
    # Fixed original materials must match the assessment's frozen byte manifest.
    verified=json.loads((SOURCE/'final-verification.json').read_text(encoding='utf-8'))['evidence_sha256']
    for name in ['source/LICENSE','source/README.md','source/coordinates.csv','commit.json','tag.json','release.json','download-receipt.json']:
        if sha(SOURCE/name)!=verified[name]:raise ValueError('SOURCE_MATERIAL_MISMATCH:'+name)
    destination.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(destination)
    try:
        create_schema(db);manifest={}
        with zipfile.ZipFile(original) as z:
            for name,(table,columns) in TABLES.items():
                with z.open(name+'.txt') as f:
                    reader=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',newline=''))
                    if reader.fieldnames!=columns.split():raise ValueError('SCHEMA_MISMATCH:'+name)
                    batch=[];n=0
                    for row in reader:
                        if None in row or any(v is None for v in row.values()):raise ValueError('MALFORMED_CSV')
                        batch.append([row[k] for k in reader.fieldnames]+[json.dumps(row,ensure_ascii=False)])
                        if len(batch)==10000:
                            db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in batch[0])+')',batch);n+=len(batch);batch=[]
                    if batch:db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in batch[0])+')',batch);n+=len(batch)
                manifest[name]={'rows':n,'columns':columns.split()}
        for table,cols in [('source_trips','trip_id'),('source_stations','stop_id'),('source_routes','route_id'),('source_agency','agency_id'),('source_calendar_dates','service_id,date'),('source_shapes','shape_id,shape_pt_sequence'),('source_stop_times','trip_id,stop_sequence')]:
            db.execute('CREATE UNIQUE INDEX idx_'+table+' ON '+table+'('+cols+')')
        db.execute('CREATE INDEX idx_stop_station ON source_stop_times(stop_id,trip_id)')
        db.execute('CREATE INDEX idx_train_label ON source_trips(trip_short_name)')
        # Raw GTFS strings remain intact; normalized values are separate columns.
        db.execute('ALTER TABLE source_stop_times ADD arrival_seconds INTEGER')
        db.execute('ALTER TABLE source_stop_times ADD departure_seconds INTEGER')
        db.execute('ALTER TABLE source_stop_times ADD sequence_index INTEGER')
        db.create_function('gtfs_seconds',1,parse_time)
        db.execute('UPDATE source_stop_times SET arrival_seconds=gtfs_seconds(arrival_time),departure_seconds=gtfs_seconds(departure_time),sequence_index=CAST(stop_sequence AS INTEGER)')
        for day,typ in db.execute('SELECT date,exception_type FROM source_calendar_dates'):
            parse_day(day)
            if typ not in ('1','2'):raise ValueError('INVALID_EXCEPTION')
        coordinates(db,SOURCE/'source/coordinates.csv');isolate(db)
        metadata={'schema_version':1,'release':RELEASE,'commit':COMMIT,'source_sha256':SHA256,'feed_version':'20261101',
          'download_receipt':json.loads((SOURCE/'download-receipt.json').read_text(encoding='utf-8')),
          'imported_at':datetime.now(timezone.utc).isoformat(),'timezone':'Asia/Shanghai','license_declaration':'CC BY 4.0',
          'rights_status':'RIGHTS_REVIEW_PENDING','usage_scope':'LOCAL_DEMO_ONLY','coordinate_source_sha256':sha(SOURCE/'source/coordinates.csv'),
          'coverage':list(db.execute('SELECT min(date),max(date) FROM source_calendar_dates').fetchone()),'shape_status_rule':'empty shape_id => SHAPE_UNAVAILABLE'}
        for k,v in metadata.items():db.execute('INSERT INTO source_metadata VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)))
        quality=assess(db)
        if any(quality['foreign_keys'].values()) or any(quality['duplicate_keys'].values()):raise ValueError('INTEGRITY_FAILED')
        if quality['counts']['anomalous_records']!=188 or quality['counts']['quarantined_trips']!=187 or quality['counts']['effective_trips']!=11588:
            raise ValueError('COUNTS_DIFFER_FROM_PINNED_ASSESSMENT')
        db.commit()
        return dict(metadata=metadata,files=manifest,quality=quality,database=str(destination),original_unchanged=sha(original)==SHA256)
    except Exception:
        db.rollback()
        raise  # Keep incomplete new output for diagnosis, never overwrite/reuse it.
    finally:db.close()
