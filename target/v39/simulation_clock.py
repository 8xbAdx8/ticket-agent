"""Persistent, paused business time. Never changes the system or API clock."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3,uuid
from target.v39.store import safe_path

LOCAL=timezone(timedelta(hours=8))


def real_now():return datetime.now(timezone.utc)


class SimulationClock:
    simulation=True

    def __init__(self,path,session_id,clock_id):
        self.path=safe_path(path);self.session_id=session_id;self.clock_id=clock_id
        self.snapshot()

    @classmethod
    def create(cls,path,session_id,anchor,dataset_version):
        path=safe_path(path)
        if anchor.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb'):pass
        identity=uuid.uuid4().hex
        with closing(sqlite3.connect(path)) as c:
            c.executescript('CREATE TABLE clock(id INTEGER PRIMARY KEY CHECK(id=1),clock_id TEXT NOT NULL,session_id TEXT NOT NULL,dataset_version TEXT NOT NULL,anchor TEXT NOT NULL,current TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL); CREATE TABLE clock_events(revision INTEGER PRIMARY KEY,from_time TEXT NOT NULL,to_time TEXT NOT NULL,recorded_at TEXT NOT NULL);')
            value=anchor.astimezone(timezone.utc).isoformat()
            c.execute('INSERT INTO clock VALUES(1,?,?,?,?,?,0,?)',(identity,session_id,dataset_version,value,value,real_now().isoformat()));c.commit()
        return cls(path,session_id,identity)

    def _row(self,c):
        c.row_factory=sqlite3.Row
        row=c.execute('SELECT * FROM clock WHERE id=1').fetchone()
        if not row or row['session_id']!=self.session_id or row['clock_id']!=self.clock_id:raise ValueError('SIMULATION_CLOCK_SCOPE_MISMATCH')
        return dict(row)

    def snapshot(self):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as c:r=self._row(c)
        return dict(clock_id=r['clock_id'],mode='PAUSED',simulation=True,timezone='Asia/Shanghai',
                    now=datetime.fromisoformat(r['current']).astimezone(LOCAL).isoformat(),
                    anchor=r['anchor'],revision=r['revision'],dataset_version=r['dataset_version'])

    def __call__(self):return datetime.fromisoformat(self.snapshot()['now']).astimezone(timezone.utc)

    def advance(self,seconds,*,revision):
        if type(seconds) is not int or not 0<seconds<=604800:raise ValueError('INVALID_CLOCK_ADVANCE')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=15,isolation_level=None)) as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                r=self._row(c)
                if type(revision) is not int or r['revision']!=revision:raise ValueError('SIMULATION_CLOCK_STALE')
                value=(datetime.fromisoformat(r['current'])+timedelta(seconds=seconds)).isoformat()
                c.execute('UPDATE clock SET current=?,revision=revision+1 WHERE id=1',(value,))
                c.execute('INSERT INTO clock_events VALUES(?,?,?,?)',(revision+1,r['current'],value,real_now().isoformat()));c.commit()
            except BaseException:c.rollback();raise
        return self.snapshot()


def dataset_anchor(static):
    # Only use actual active service days belonging to non-quarantined trips.
    with static._open() as db:
        row=db.db.execute("SELECT MIN(c.date) FROM source_calendar_dates c JOIN effective_trips t ON t.service_id=c.service_id WHERE c.exception_type='1'").fetchone()
    if not row or not row[0]:raise ValueError('SIMULATION_SERVICE_DAY_MISSING')
    return datetime.strptime(row[0],'%Y%m%d').replace(tzinfo=LOCAL)
