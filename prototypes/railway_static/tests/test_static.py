"""Phase8-only deterministic checks using the complete fixed real GTFS."""
import ast,csv,io,itertools,json,os,sqlite3,tempfile,unittest,zipfile,hashlib
from pathlib import Path
from datetime import datetime
from prototypes.railway_static.models import SOURCE,SHA256,ROOT
from prototypes.railway_static.importer import validate_archive,import_dataset
from prototypes.railway_static.schema import TABLES
from prototypes.railway_static.calendar import parse_time,actual_time,service_active,parse_day
from prototypes.railway_static.query import Dataset

class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=Path(os.environ['PHASE8_DB']);cls.d=Dataset(cls.path);cls.db=cls.d.db
        cls.bad=[];cls.original_ids=set();cls.original_stops=[]
        with zipfile.ZipFile(SOURCE/'output_gtfs.zip') as z:
            with z.open('trips.txt') as f:
                cls.original_ids={r['trip_id'] for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'))}
            with z.open('stop_times.txt') as f:
                for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig')):
                    def independent(v):
                        h,m,s=[int(x) for x in v.split(':')];return h*3600+m*60+s
                    cls.original_stops.append(r)
                    if independent(r['arrival_time'])>independent(r['departure_time']):cls.bad.append(r)
        cls.bad_ids={r['trip_id'] for r in cls.bad};cls.good_ids=cls.original_ids-cls.bad_ids

    @classmethod
    def tearDownClass(cls):cls.d.close()
    def scalar(self,sql,*args):return self.db.execute(sql,args).fetchone()[0]
    def test_01_zip_identity(self):
        self.assertEqual(hashlib.sha256((SOURCE/'output_gtfs.zip').read_bytes()).hexdigest(),SHA256);validate_archive(SOURCE/'output_gtfs.zip')
    def test_02_wrong_zip_rejected(self):
        with tempfile.TemporaryDirectory(dir=os.environ['PHASE8_OUT']) as t:
            p=Path(t)/'wrong.zip';p.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'SOURCE_IDENTITY'):validate_archive(p)
    def test_03_all_nine_files_present(self):
        with zipfile.ZipFile(SOURCE/'output_gtfs.zip') as z:self.assertEqual(set(z.namelist()),{n+'.txt' for n in TABLES})
    def test_04_every_raw_csv_row_preserved(self):
        with zipfile.ZipFile(SOURCE/'output_gtfs.zip') as z:
            for name,(table,fields) in TABLES.items():
                with z.open(name+'.txt') as f:
                    expected=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',newline=''))
                    actual=self.db.execute('SELECT raw_json,'+fields.replace(' ', ',')+' FROM '+table+' ORDER BY rowid')
                    for i,(a,b) in enumerate(itertools.zip_longest(expected,actual)):
                        if a is None or b is None or a!=json.loads(b[0]) or tuple(a[k] for k in fields.split())!=tuple(b)[1:]:self.fail(f'{name} raw row mismatch {i}')
    def test_05_raw_primary_keys(self):
        for t,k in [('source_trips','trip_id'),('source_stations','stop_id'),('source_stop_times','trip_id,stop_sequence')]:
            self.assertEqual(self.scalar(f'SELECT count(*) FROM (SELECT {k} FROM {t} GROUP BY {k} HAVING count(*)>1)'),0)
    def test_06_foreign_keys(self):
        from prototypes.railway_static.quality import assess
        self.assertFalse(any(assess(self.db)['foreign_keys'].values()))
    def test_07_independent_188_records(self):self.assertEqual(len(self.bad),188)
    def test_08_independent_187_trips(self):self.assertEqual(len(self.bad_ids),187)
    def test_09_exact_quarantine_set(self):
        self.assertEqual({r[0] for r in self.db.execute('SELECT DISTINCT trip_id FROM trip_quarantine')},self.bad_ids)
    def test_10_quarantine_full_provenance(self):
        actual={(r['trip_id'],str(r['stop_sequence']),r['stop_id'],r['arrival_time'],r['departure_time']) for r in self.db.execute('SELECT * FROM trip_quarantine')}
        self.assertEqual(actual,{tuple(r[k] for k in ['trip_id','stop_sequence','stop_id','arrival_time','departure_time']) for r in self.bad})
        self.assertEqual(self.scalar('SELECT count(*) FROM trip_quarantine WHERE source_sha256<>?',SHA256),0)
    def test_11_no_valid_trip_lost(self):
        self.assertEqual({r[0] for r in self.db.execute('SELECT trip_id FROM effective_trips')},self.good_ids);self.assertEqual(len(self.good_ids),11588)
    def test_12_no_quarantined_stops_in_view(self):
        expected={(r['trip_id'],r['stop_sequence']) for r in self.original_stops if r['trip_id'] not in self.bad_ids}
        self.assertEqual({tuple(r) for r in self.db.execute('SELECT trip_id,stop_sequence FROM effective_stop_times')},expected)
    def test_13_every_quarantined_trip_api_excludes_all_stops(self):
        for tid in self.bad_ids:self.assertEqual(self.d.trip(tid,'2026-11-02')['data'],[])
    def test_14_date_query_exact_all_dates(self):
        by_day={}
        for row in self.db.execute('SELECT trip_id,date FROM source_trips JOIN source_calendar_dates USING(service_id) WHERE exception_type=\'1\''):
            if row['trip_id'] not in self.bad_ids:by_day.setdefault(row['date'],set()).add(row['trip_id'])
        for day,expected in by_day.items():self.assertEqual({r['trip_id'] for r in self.d.trains(day)['data']},expected)
    def test_15_coordinates_independent_source_gap(self):
        with (SOURCE/'source/coordinates.csv').open(encoding='utf-8-sig') as f:names={r['station_name'] for r in csv.DictReader(f)}
        expected={r['stop_id'] for r in self.db.execute('SELECT * FROM source_stations') if r['stop_name'] not in names}
        actual={r[0] for r in self.db.execute("SELECT stop_id FROM station_coordinate_quality WHERE classification='UNVERIFIED_DERIVED'")}
        self.assertEqual(len(actual),26);self.assertEqual(actual,expected)
    def test_16_coordinate_matches_not_verified(self):
        self.assertEqual(self.scalar('SELECT count(*) FROM station_coordinate_quality WHERE independently_verified<>0'),0)
        self.assertEqual(self.scalar("SELECT count(*) FROM station_coordinate_quality WHERE classification='SOURCE_TABLE_MATCHED'"),3143)
    def test_17_missing_shape_3558(self):self.assertEqual(self.scalar("SELECT count(*) FROM source_trips WHERE shape_id=''"),3558)
    def test_18_missing_shape_valid_not_removed(self):
        expected={r['trip_id'] for r in self.db.execute("SELECT trip_id FROM source_trips WHERE shape_id=''")}-self.bad_ids
        self.assertEqual({r['trip_id'] for r in self.db.execute("SELECT trip_id FROM effective_trips WHERE shape_id=''")},expected)
    def test_19_duplicate_station_names_23(self):self.assertEqual(self.scalar('SELECT count(*) FROM (SELECT stop_name FROM source_stations GROUP BY stop_name HAVING count(*)>1)'),23)
    def test_20_shared_coordinates_27(self):self.assertEqual(self.scalar('SELECT count(*) FROM (SELECT stop_lat,stop_lon FROM source_stations GROUP BY stop_lat,stop_lon HAVING count(*)>1)'),27)
    def test_21_no_station_identity_merged(self):
        self.assertEqual(self.scalar('SELECT count(*) FROM source_stations'),3169);self.assertEqual(self.d.station('UUH/')['status'],'FOUND')
    def test_22_aliases_empty(self):self.assertEqual(self.scalar('SELECT count(*) FROM trip_aliases'),0)
    def test_23_removal_overrides_addition(self):
        rows=[dict(service_id='s',date='20261102',exception_type=t) for t in ['1','2']]
        self.assertFalse(service_active(rows,'s','2026-11-02'));self.assertFalse(service_active(list(reversed(rows)),'s','20261102'))
    def test_24_calendar_different_service_and_dates(self):
        rows=[dict(service_id='a',date='20261102',exception_type='1')]
        self.assertTrue(service_active(rows,'a','20261102'));self.assertFalse(service_active(rows,'b','20261102'));self.assertFalse(service_active(rows,'a','20261103'))
    def test_25_calendar_removal_only(self):self.assertFalse(service_active([dict(service_id='a',date='20261102',exception_type='2')],'a','20261102'))
    def test_26_extended_gtfs_time(self):
        self.assertEqual(parse_time('47:53:00'),172380);self.assertEqual(actual_time('20261102','47:53:00'),'2026-11-03T23:53:00+08:00')
    def test_27_real_overnight(self):
        r=self.d.trip('01000K516502','20261102');self.assertEqual(r['data']['stops'][-1]['arrival_at'],'2026-11-03T06:51:00+08:00')
    def test_28_invalid_time_not_repaired(self):
        for x in ['23:60:00','-01:00:00','24:00','bad']:
            with self.assertRaises(ValueError):parse_time(x)
    def test_29_no_modulo_or_raw_time_repair(self):
        r=self.db.execute("SELECT * FROM source_stop_times WHERE trip_id='02000K706610' AND stop_sequence='9'").fetchone()
        self.assertEqual((r['arrival_time'],r['departure_time']),('47:53:00','24:15:00'))
    def test_30_direct_correct_order(self):
        r=self.d.direct('VNP','AOH','20261102');self.assertEqual(r['status'],'FOUND')
        for t in r['data']:self.assertLess(t['origin_sequence'],t['destination_sequence']);self.assertNotIn(t['trip_id'],self.bad_ids)
    def test_31_direct_reversed_not_same_trip(self):
        a={r['trip_id'] for r in self.d.direct('VNP','AOH','20261102')['data']};b={r['trip_id'] for r in self.d.direct('AOH','VNP','20261102')['data']};self.assertFalse(a&b)
    def test_32_direct_overnight(self):
        rows=self.d.direct('HBB','HJB','20261102')['data'];r=next(r for r in rows if r['trip_id']=='01000K516502');self.assertEqual(r['arrival_at'],'2026-11-03T06:51:00+08:00')
    def test_33_ambiguous_station(self):
        self.assertEqual(self.d.direct('哈尔滨','HJB','20261102')['status'],'AMBIGUOUS_STATION');self.assertGreater(len(self.d.stations('哈尔滨')['data']),1)
    def test_34_exact_id_required_even_unique_name(self):self.assertEqual(self.d.direct('北京南','AOH','20261102')['status'],'STATION_ID_REQUIRED')
    def test_35_date_outside_coverage(self):
        for day in ['20261016','20270120']:self.assertEqual(self.d.trains(day)['status'],'OUT_OF_COVERAGE')
    def test_36_boundary_dates(self):
        for day in ['20261017','20270119']:self.assertIn(self.d.trains(day)['status'],['FOUND','NO_MATCH'])
    def test_37_no_match_is_not_sold_out(self):
        r=self.d.direct('VNP','VNP','20261102');self.assertEqual(r['status'],'NO_MATCH');self.assertEqual(r['availability'],'UNKNOWN');self.assertFalse(r['availability_available'])
    def test_38_nonexistent_train(self):self.assertEqual(self.d.trip('not-a-trip','20261102')['status'],'NO_MATCH')
    def test_39_invalid_date(self):
        for value in ['2026-02-30','Nov 2',20261102]:
            with self.assertRaises(ValueError):parse_day(value)
    def test_40_six_interfaces_have_source_flags(self):
        for r in [self.d.info(),self.d.stations('哈尔滨'),self.d.station('VNP'),self.d.trains('20261102'),self.d.trip('01000K516502','20261102'),self.d.direct('VNP','AOH','20261102')]:
            self.assertEqual(r['source_sha256'],SHA256);self.assertEqual(r['data_type'],'STATIC_SCHEDULE');self.assertFalse(r['real_time']);self.assertFalse(r['booking_available']);self.assertFalse(r['fare_available']);self.assertFalse(r['availability_available'])
    def test_41_rights_and_local_scope(self):
        self.assertEqual(self.d.metadata['rights_status'],'RIGHTS_REVIEW_PENDING');self.assertEqual(self.d.metadata['usage_scope'],'LOCAL_DEMO_ONLY')
    def test_42_database_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):self.db.execute("DELETE FROM trip_aliases")
    def test_43_importer_rejects_existing_database(self):
        with self.assertRaisesRegex(ValueError,'NEW_ISOLATED'):import_dataset(self.path)
    def test_44_importer_rejects_business_target(self):
        with self.assertRaisesRegex(ValueError,'NEW_ISOLATED'):import_dataset(ROOT/'data/business.sqlite')
    def test_45_no_network_or_production_imports(self):
        for file in (ROOT/'prototypes/railway_static').glob('*.py'):
            for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Import):mods=[a.name.split('.')[0] for a in node.names]
                elif isinstance(node,ast.ImportFrom):mods=[(node.module or '').split('.')[0]]
                else:continue
                self.assertFalse(set(mods)&{'socket','urllib','requests','httpx','web','target','services'},file)
    def test_46_original_zip_still_unchanged(self):self.assertEqual(hashlib.sha256((SOURCE/'output_gtfs.zip').read_bytes()).hexdigest(),SHA256)
    def test_47_fixture_still_unchanged(self):self.assertEqual(hashlib.sha256((ROOT/'data/fixtures/train-v1.json').read_bytes()).hexdigest(),'54506ae02354dfaa7366f1c32cd75cee6ed04176b5c04a121898ebdae89253d1')
    def test_48_all_bad_trip_endpoints_direct_api(self):
        for tid in self.bad_ids:
            rows=[r for r in self.original_stops if r['trip_id']==tid]
            result=self.d.direct(rows[0]['stop_id'],rows[-1]['stop_id'],'20261102')
            self.assertNotIn(tid,{r['trip_id'] for r in result['data']})
    def test_49_exception_two_in_actual_query_engine(self):
        from prototypes.railway_static.schema import create_schema
        with tempfile.TemporaryDirectory(dir=os.environ['PHASE8_OUT']) as tmp:
            path=Path(tmp)/'exception.sqlite';c=sqlite3.connect(path);create_schema(c)
            for k,v in self.d.metadata.items():c.execute('INSERT INTO source_metadata VALUES (?,?)',(k,json.dumps(v)))
            trip=self.db.execute("SELECT * FROM source_trips WHERE trip_short_name='G1'").fetchone()
            c.execute('INSERT INTO source_trips VALUES (?,?,?,?,?,?,?)',tuple(trip))
            c.execute('INSERT INTO source_calendar_dates VALUES (?,?,?,?)',(trip['service_id'],'20261102','1','{}'));c.commit()
            with Dataset(path) as d:self.assertEqual(len(d.trains('20261102')['data']),1)
            c.execute('INSERT INTO source_calendar_dates VALUES (?,?,?,?)',(trip['service_id'],'20261102','2','{}'));c.commit()
            with Dataset(path) as d:self.assertEqual(d.trains('20261102')['status'],'NO_MATCH')
            c.close()
    def test_50_known_trip_not_running_within_coverage(self):
        tid='24000000G10L'
        service=self.db.execute('SELECT service_id FROM source_trips WHERE trip_id=?',(tid,)).fetchone()[0]
        all_days={r[0] for r in self.db.execute('SELECT DISTINCT date FROM source_calendar_dates')}
        train_days={r[0] for r in self.db.execute("SELECT date FROM source_calendar_dates WHERE service_id=? AND exception_type='1'",(service,))}
        absent=next(iter(all_days-train_days))
        self.assertEqual(self.d.trip(tid,absent)['status'],'NO_MATCH')
    def test_51_info_reports_actual_quality_and_coverage(self):
        info=self.d.info()['data']
        self.assertEqual(info['quality']['counts']['quarantined_trips'],len(self.bad_ids))
        self.assertEqual(info['quality']['counts']['effective_trips'],len(self.good_ids))
        self.assertEqual(info['coverage'],['20261017','20270119'])
        self.assertEqual(info['quality_status'],'QUARANTINED_WITH_KNOWN_LIMITATIONS')

if __name__=='__main__':unittest.main()
