"""Dataset identity and honest capability envelopes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'artifacts/runtime/railway-dataset-preparation-20261102-gtfs'
SHA256 = '3877dbc0ebc0392afef4b111dd9ba837c97eb4aa45788542919be53d52a12030'
COMMIT = 'adb0852237d7d4a529c9ee4daa9d7d5ebb1b6ab8'
RELEASE = 'gtfs-20261101-063437'

def envelope(status, data, **extra):
    return dict(status=status, data=data, data_source='CHINESE_RAILWAY_GTFS',
                data_type='STATIC_SCHEDULE', real_time=False,
                availability_available=False, fare_available=False, booking_available=False,
                availability='UNKNOWN', fare=None, data_version='20261101', source_sha256=SHA256,
                rights_status='RIGHTS_REVIEW_PENDING', usage_scope='LOCAL_DEMO_ONLY', **extra)
