"""Version-pinned read-only adapter over the unchanged stage-eight prototype."""
from pathlib import Path
import hashlib
import threading
from prototypes.railway_static.query import Dataset
from target.v39.store import integer

SOURCE_SHA='3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030'
DATABASE_SHA='e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69'
VERSION='gtfs-20261101-063437'
DEFAULT_PATH=Path(__file__).resolve().parents[2]/'artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite'
_VERIFIED={}
_LOCK=threading.Lock()


class RailwayStatic:
    def __init__(self,path=DEFAULT_PATH):
        self.path=Path(path).resolve()
        stat=self.path.stat()
        identity=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)
        with _LOCK:
            if _VERIFIED.get(self.path)!=identity:
                h=hashlib.sha256()
                with self.path.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
                if h.hexdigest()!=DATABASE_SHA:raise ValueError('STATIC_DATA_IDENTITY_MISMATCH')
                _VERIFIED[self.path]=identity
        self.identity=identity

    def _open(self):
        stat=self.path.stat()
        if (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)!=self.identity:
            raise ValueError('STATIC_DATA_IDENTITY_MISMATCH')
        return Dataset(self.path)

    @staticmethod
    def envelope(result):
        result=dict(result)
        if result.get('status')=='QUARANTINED':result['status']='TRIP_QUARANTINED'
        result.update(dataset_version=VERSION,source_sha256=SOURCE_SHA,database_sha256=DATABASE_SHA,data_type='STATIC_SCHEDULE',real_time=False,availability_available=False,fare_available=False,booking_available=False)
        return result

    def stations(self,name,limit=50,cursor=None):
        if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('INVALID_STATION_NAME')
        integer(limit,'limit',1,50)
        if cursor is not None and (not isinstance(cursor,str) or not cursor.isdigit()):raise ValueError('INVALID_CURSOR')
        offset=int(cursor or 0)
        if offset>10000:raise ValueError('INVALID_CURSOR')
        with self._open() as db:result=db.stations(name.strip())
        rows=result['data'];result['data']=rows[offset:offset+limit]
        result.update(source='GTFS_SQLITE',total_count=len(rows),returned_count=len(result['data']),
                      limit=limit,has_more=offset+limit<len(rows),
                      query_parameters=dict(name=name.strip(),cursor=cursor))
        result['next_cursor']=str(offset+limit) if offset+limit<len(rows) else None
        result['selection_required']=len(rows)>1
        return self.envelope(result)

    def station(self,stop_id):
        with self._open() as db:return self.envelope(db.station(stop_id))

    def trip(self,trip_id,service_date):
        with self._open() as db:result=db.trip(trip_id,service_date)
        if result['status']=='FOUND':
            seen=set()
            for pos,s in enumerate(result['data']['stops']):
                seq=s['sequence_index']
                if seq in seen:raise ValueError('STATIC_SEQUENCE_AMBIGUOUS')
                seen.add(seq);s.update(raw_stop_sequence=s['stop_sequence'],position=pos)
        return self.envelope(result)

    def trips(self,service_date,origin_stop_id=None,destination_stop_id=None,train_no=None,limit=50,cursor=None,trip_id=None,seat_class=None):
        integer(limit,'limit',1,50)
        if bool(origin_stop_id)!=bool(destination_stop_id):raise ValueError('STATION_ID_REQUIRED')
        if trip_id:return self.trip(trip_id,service_date)
        with self._open() as db:
            result=db.direct(origin_stop_id,destination_stop_id,service_date) if origin_stop_id else db.trains(service_date)
        rows=result['data']
        if train_no:rows=[r for r in rows if train_no in (r.get('trip_short_name'),r.get('trip_headsign'))]
        if cursor is not None and (not isinstance(cursor,str) or not cursor.isdigit()):raise ValueError('INVALID_CURSOR')
        offset=int(cursor or 0)
        if offset>20000:raise ValueError('INVALID_CURSOR')
        result['data']=rows[offset:offset+limit];result['next_cursor']=str(offset+limit) if offset+limit<len(rows) else None
        result.update(source='GTFS_SQLITE',total_count=len(rows),returned_count=len(result['data']),
                      limit=limit,has_more=offset+limit<len(rows),query_parameters=dict(
                          service_date=service_date,origin_stop_id=origin_stop_id,
                          destination_stop_id=destination_stop_id,train_no=train_no,cursor=cursor))
        if result['status']=='FOUND' and not rows:result['status']='NO_MATCH'
        return self.envelope(result)

    def interval(self,trip_id,service_date,origin_stop_id,destination_stop_id):
        result=self.trip(trip_id,service_date)
        if result['status']!='FOUND':raise ValueError(result['status'])
        stops=result['data']['stops']
        origins=[i for i,s in enumerate(stops) if s['stop_id']==origin_stop_id]
        destinations=[i for i,s in enumerate(stops) if s['stop_id']==destination_stop_id]
        if len(origins)!=1 or len(destinations)!=1:raise ValueError('STATION_ID_REQUIRED')
        a,b=origins[0],destinations[0]
        if a>=b:raise ValueError('INVALID_INTERVAL')
        return dict(trip=result['data']['trip'],stops=stops,origin=stops[a],destination=stops[b],segments=list(range(a,b)),dataset_version=VERSION,source_sha256=SOURCE_SHA)
