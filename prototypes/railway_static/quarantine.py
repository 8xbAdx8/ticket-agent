"""Quarantine whole trips; original rows remain unchanged."""
from .calendar import parse_time
from .models import SHA256

def isolate(db):
    findings = []
    for tid, a, d, sid, seq in db.execute('SELECT trip_id,arrival_time,departure_time,stop_id,stop_sequence FROM source_stop_times'):
        if parse_time(a) > parse_time(d):
            findings.append((tid, int(seq), sid, 'ARRIVAL_AFTER_DEPARTURE', a, d, SHA256))
    db.executemany('INSERT INTO trip_quarantine VALUES (?,?,?,?,?,?,?)', findings)
    return findings
