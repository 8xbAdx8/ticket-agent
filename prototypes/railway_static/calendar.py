"""Service-day arithmetic. Extended GTFS hours are not clock-hour modulo 24."""
import re
from datetime import date, datetime, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8), name='Asia/Shanghai')

def parse_day(value):
    if not isinstance(value, str):
        raise ValueError('INVALID_DATE')
    if re.fullmatch(r'\d{8}', value):
        return datetime.strptime(value, '%Y%m%d').date()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value)
    raise ValueError('INVALID_DATE')

def parse_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{2,}:\d{2}:\d{2}', value):
        raise ValueError('INVALID_GTFS_TIME')
    hours, minutes, seconds = map(int, value.split(':'))
    if minutes > 59 or seconds > 59:
        raise ValueError('INVALID_GTFS_TIME')
    return hours * 3600 + minutes * 60 + seconds

def actual_time(service_date, gtfs_time):
    return (datetime.combine(parse_day(service_date), datetime.min.time(), SHANGHAI)
            + timedelta(seconds=parse_time(gtfs_time))).isoformat()

def service_active(rows, service_id, day):
    """Explicit calendar_dates only: removal wins conflicting exception entries."""
    target = parse_day(day).strftime('%Y%m%d')
    types = {str(r['exception_type']) for r in rows
             if r['service_id'] == service_id and r['date'] == target}
    return '1' in types and '2' not in types
