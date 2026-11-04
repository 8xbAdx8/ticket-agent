"""Read-only static queries. All stop results join the whole-trip allow view."""
import json,sqlite3
from pathlib import Path
from .models import SHA256,envelope
from .calendar import parse_day,actual_time

class Dataset:
    def __init__(self,path):
        self.db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
        self.db.row_factory=sqlite3.Row
        self.metadata={r['key']:json.loads(r['value_json']) for r in self.db.execute('SELECT * FROM source_metadata')}
        if self.metadata.get('source_sha256')!=SHA256 or self.metadata.get('schema_version')!=1:
            self.db.close();raise ValueError('DATASET_IDENTITY_MISMATCH')

    def close(self):self.db.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def info(self):
        from .quality import assess
        return envelope('FOUND',dict(self.metadata,quality=assess(self.db),
                                    quality_status='QUARANTINED_WITH_KNOWN_LIMITATIONS'))

    def stations(self,name):
        # instr makes wildcard characters literal rather than SQL patterns.
        rows=[dict(r) for r in self.db.execute('SELECT * FROM source_stations WHERE instr(stop_name,?)>0 ORDER BY stop_name,stop_id',(name,))]
        return envelope('FOUND' if rows else 'NO_MATCH',rows,selection_required=len(rows)>1)

    def station(self,stop_id):
        row=self.db.execute('SELECT s.*,q.classification,q.independently_verified,q.shared_ids_json FROM source_stations s JOIN station_coordinate_quality q USING(stop_id) WHERE stop_id=?',(stop_id,)).fetchone()
        return envelope('FOUND' if row else 'NO_MATCH',dict(row) if row else None)

    def _day(self,value):
        day=parse_day(value).strftime('%Y%m%d');low,high=self.metadata['coverage']
        return day,low<=day<=high

    @staticmethod
    def _active(alias='t'):
        return f"EXISTS(SELECT 1 FROM source_calendar_dates c WHERE c.service_id={alias}.service_id AND c.date=? AND c.exception_type='1') AND NOT EXISTS(SELECT 1 FROM source_calendar_dates c WHERE c.service_id={alias}.service_id AND c.date=? AND c.exception_type='2')"

    @staticmethod
    def _trip(r):
        r=dict(r);r['shape_status']='AVAILABLE' if r['shape_id'] else 'SHAPE_UNAVAILABLE'
        return r

    def trains(self,service_date):
        day,covered=self._day(service_date)
        if not covered:return envelope('OUT_OF_COVERAGE',[])
        rows=[self._trip(r) for r in self.db.execute('SELECT t.* FROM effective_trips t WHERE '+self._active()+' ORDER BY trip_id',(day,day))]
        return envelope('FOUND' if rows else 'NO_MATCH',rows,service_date=day)

    def trip(self,trip_id,service_date):
        day,covered=self._day(service_date)
        if not covered:return envelope('OUT_OF_COVERAGE',[])
        if self.db.execute('SELECT 1 FROM trip_quarantine WHERE trip_id=?',(trip_id,)).fetchone():return envelope('QUARANTINED',[])
        row=self.db.execute('SELECT t.* FROM effective_trips t WHERE trip_id=? AND '+self._active(),(trip_id,day,day)).fetchone()
        if not row:return envelope('NO_MATCH',[])
        stops=[dict(r) for r in self.db.execute('SELECT s.*,p.stop_name FROM effective_stop_times s JOIN source_stations p USING(stop_id) WHERE trip_id=? ORDER BY sequence_index',(trip_id,))]
        for s in stops:
            s['arrival_at']=actual_time(day,s['arrival_time']);s['departure_at']=actual_time(day,s['departure_time'])
        return envelope('FOUND',dict(trip=self._trip(row),stops=stops),service_date=day)

    def direct(self,from_id,to_id,service_date):
        day,covered=self._day(service_date)
        if not covered:return envelope('OUT_OF_COVERAGE',[])
        for sid in (from_id,to_id):
            if not self.db.execute('SELECT 1 FROM source_stations WHERE stop_id=?',(sid,)).fetchone():
                candidates=self.stations(sid)['data']
                return envelope('AMBIGUOUS_STATION' if len(candidates)>1 else 'STATION_ID_REQUIRED',[],station_candidates=candidates)
        rows=self.db.execute('''SELECT t.*,a.arrival_time origin_arrival,a.departure_time origin_departure,
            b.arrival_time destination_arrival,b.departure_time destination_departure,
            a.sequence_index origin_sequence,b.sequence_index destination_sequence
            FROM effective_trips t JOIN effective_stop_times a ON a.trip_id=t.trip_id
            JOIN effective_stop_times b ON b.trip_id=t.trip_id
            WHERE a.stop_id=? AND b.stop_id=? AND a.sequence_index<b.sequence_index AND '''+self._active()+' ORDER BY a.departure_seconds,t.trip_id',
            (from_id,to_id,day,day))
        result=[]
        for row in rows:
            r=self._trip(row);r.update(departure_at=actual_time(day,r['origin_departure']),arrival_at=actual_time(day,r['destination_arrival']))
            result.append(r)
        return envelope('FOUND' if result else 'NO_MATCH',result,service_date=day)
