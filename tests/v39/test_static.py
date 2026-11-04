from datetime import datetime
import sqlite3
import pytest
from target.v39.static import RailwayStatic,DEFAULT_PATH,VERSION

@pytest.fixture(scope='module')
def static():return RailwayStatic()

def test_real_read_only_feed_identity_counts_and_quarantine(static):
    with static._open() as db:
        assert db.db.execute('SELECT count(*) FROM source_stations').fetchone()[0]==3169
        assert db.db.execute('SELECT count(*) FROM effective_trips').fetchone()[0]==11588
        assert db.db.execute('SELECT count(*) FROM effective_stop_times').fetchone()[0]==107669
        quarantined=db.db.execute('SELECT trip_id FROM trip_quarantine LIMIT 1').fetchone()[0]
        assert db.db.execute('SELECT count(DISTINCT trip_id) FROM trip_quarantine').fetchone()[0]==187
        assert db.db.execute('SELECT count(*) FROM trip_quarantine').fetchone()[0]==188
        with pytest.raises(sqlite3.OperationalError,match='readonly'):db.db.execute('DELETE FROM source_stations')
    assert static.trip(quarantined,'2026-11-03')['status']=='TRIP_QUARANTINED'

def test_real_cross_day_and_dense_sequences(static):
    rows=static.trips('2026-11-02',train_no='K5165')['data']
    assert rows
    result=static.trip(rows[0]['trip_id'],'2026-11-02')
    stops=result['data']['stops']
    assert [s['position'] for s in stops]==list(range(len(stops)))
    # V1.2.2 T046's 23:53 claim is contradicted by the original feed; preserved
    # matrix is not edited. Assert the actual source plus independent conversion.
    assert stops[-1]['arrival_time']=='30:51:00'
    assert stops[-1]['arrival_at']=='2026-11-03T06:51:00+08:00'
    from prototypes.railway_static.calendar import actual_time
    assert actual_time('20261102','47:53:00')=='2026-11-03T23:53:00+08:00'
    assert result['real_time'] is False and result['fare_available'] is False
    interval=static.interval(rows[0]['trip_id'],'2026-11-02',stops[0]['stop_id'],stops[-1]['stop_id'])
    assert interval['segments']==list(range(len(stops)-1))

def test_real_station_ambiguity_is_not_guessed(static):
    rows=static.stations('北京')['data']
    assert len(rows)>1
    result=static.stations('北京')
    assert result['selection_required'] is True
    assert static.trips('2026-01-01')['status']=='OUT_OF_COVERAGE'
    assert static.stations('NO_SUCH_STATION')['status']=='NO_MATCH'

def test_tampered_database_copy_rejected(tmp_path):
    path=tmp_path/'invalid.sqlite';path.write_bytes(b'not a dataset')
    with pytest.raises(ValueError,match='IDENTITY_MISMATCH'):RailwayStatic(path)
