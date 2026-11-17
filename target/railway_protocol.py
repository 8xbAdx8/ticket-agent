"""Versioned query-only wire contract. No Agent, credentials or database imports."""
from datetime import date, datetime, timezone
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OPERATIONS = {'left-ticket': '/v1/trains/search', 'route': '/v1/trains/route',
              'transfer-ticket': '/v1/trains/transfer-search'}
STATUSES = Literal['FOUND', 'NO_MATCH', 'NO_AVAILABILITY', 'AVAILABILITY_UNKNOWN',
                   'SNAPSHOT_MISSING', 'SNAPSHOT_EXPIRED', 'OUT_OF_COVERAGE',
                   'SOURCE_UNAVAILABLE', 'INVALID_SNAPSHOT', 'LIVE_DISABLED', 'FIXTURE_MISSING']
SYNTHETIC = 'SYNTHETIC_TEST_FIXTURE'
UPSTREAM_COMMIT = '4183eac1302087e5724506e79453a92145053a95'


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def station(value):
    if not isinstance(value, str) or not re.fullmatch(r'[\u3400-\u9fffA-Za-z· ]{1,40}', value) or value != value.strip():
        raise ValueError('INVALID_STATION')
    return value


def day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('INVALID_DATE')
    return value


def stamp(value):
    d = datetime.fromisoformat(value)
    if d.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return value


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_FIELD')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Query(Strict):
    from_station: str
    to_station: str
    train_date: str
    train_code: str | None = None
    seat_type: Literal['二等座', '一等座', '商务座'] | None = None
    middle_station: str | None = None

    _station = field_validator('from_station', 'to_station')(station)
    _day = field_validator('train_date')(day)

    @field_validator('middle_station')
    @classmethod
    def middle(cls, v):
        return station(v) if v is not None else v

    @field_validator('train_code')
    @classmethod
    def code(cls, v):
        if v is not None and not re.fullmatch(r'[GDCZTKYSLA]\d{1,5}', v):
            raise ValueError('INVALID_TRAIN_CODE')
        return v

    @model_validator(mode='after')
    def different(self):
        if self.from_station == self.to_station or self.middle_station in (self.from_station, self.to_station):
            raise ValueError('IDENTICAL_STATION')
        return self


class Train(Strict):
    train_no: str = Field(pattern=r'^[GDCZTKYSLA]\d{1,5}$')
    from_city: str
    to_city: str
    date: str
    depart: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    arrive: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    duration_min: int = Field(ge=1, le=2880)
    kind: Literal['高铁', '普速'] = '高铁'
    seat_type: Literal['二等座', '一等座', '商务座']
    price: float | None = Field(ge=0, le=100000)
    seats_left: int | None = Field(ge=0, le=100000)
    availability: Literal['AVAILABLE', 'SOLD_OUT', 'UNKNOWN']
    _station = field_validator('from_city', 'to_city')(station)
    _day = field_validator('date')(day)

    @model_validator(mode='after')
    def consistent(self):
        expected = 'UNKNOWN' if self.seats_left is None else 'AVAILABLE' if self.seats_left > 0 else 'SOLD_OUT'
        h, m = map(int, self.depart.split(':')); ah, am = map(int, self.arrive.split(':'))
        if self.availability != expected or (h*60+m+self.duration_min) % 1440 != ah*60+am or self.from_city == self.to_city:
            raise ValueError('INCONSISTENT_TRAIN')
        return self


class Stop(Strict):
    station_no: int = Field(ge=1, le=500)
    station_name: str
    arrive_time: str | None
    depart_time: str | None
    _station = field_validator('station_name')(station)

    @field_validator('arrive_time', 'depart_time')
    @classmethod
    def clock(cls, v):
        if v is not None and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', v):
            raise ValueError('INVALID_STOP_TIME')
        return v


class Leg(Strict):
    train_no: str = Field(pattern=r'^[GDCZTKYSLA]\d{1,5}$')
    from_city: str
    to_city: str
    date: str | None
    depart: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    arrive: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    seat_type: Literal['二等座', '一等座', '商务座']
    price: float | None = Field(ge=0, le=100000)
    seats_left: int | None = Field(ge=0, le=100000)
    availability: Literal['AVAILABLE', 'SOLD_OUT', 'UNKNOWN']
    _station = field_validator('from_city', 'to_city')(station)

    @field_validator('date')
    @classmethod
    def optional_day(cls, v):
        return day(v) if v is not None else v

    @model_validator(mode='after')
    def stock(self):
        expected = 'UNKNOWN' if self.seats_left is None else 'AVAILABLE' if self.seats_left > 0 else 'SOLD_OUT'
        if self.availability != expected or self.from_city == self.to_city:
            raise ValueError('INCONSISTENT_TRANSFER_LEG')
        return self


class Transfer(Strict):
    middle_station: str
    legs: list[Leg] = Field(min_length=2, max_length=2)
    _station = field_validator('middle_station')(station)

    @model_validator(mode='after')
    def continuous(self):
        if self.legs[0].to_city != self.middle_station or self.legs[1].from_city != self.middle_station:
            raise ValueError('DISCONNECTED_TRANSFER')
        return self


def train_status(rows):
    if not rows:
        return 'NO_MATCH'
    if any(t.seats_left is not None and t.seats_left > 0 for t in rows):
        return 'FOUND'
    if all(t.seats_left == 0 for t in rows):
        return 'NO_AVAILABILITY'
    return 'AVAILABILITY_UNKNOWN'


def transfer_status(rows):
    if not rows:
        return 'NO_MATCH'
    if any(all(t.seats_left is not None and t.seats_left > 0 for t in r.legs) for r in rows):
        return 'FOUND'
    if all(any(t.seats_left == 0 for t in r.legs) for r in rows):
        return 'NO_AVAILABILITY'
    return 'AVAILABILITY_UNKNOWN'


class Metadata(Strict):
    source_verified_independently: Literal[False] = False
    real_time: Literal[False] = False
    observed_at: str
    upstream_commit: str | None = None
    origin_requests: int = Field(default=0, ge=0, le=6)
    _stamp = field_validator('observed_at')(stamp)


class Error(Strict):
    code: str = Field(pattern=r'^[A-Z_]{1,60}$')
    message: str = Field(max_length=200)


class Response(Strict):
    schema_version: Literal['1.0'] = '1.0'
    provider: Literal['12306_train_assistant', 'local_synthetic_test_service', 'disabled']
    source_type: Literal['LIVE', 'SYNTHETIC_TEST_FIXTURE', 'DISABLED']
    operation: Literal['left-ticket', 'route', 'transfer-ticket']
    query_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    requested_at: str
    data_as_of: str | None
    query: Query
    status: STATUSES
    trains: list[Train] = Field(max_length=500)
    stops: list[Stop] = Field(max_length=500)
    transfers: list[Transfer] = Field(max_length=100)
    source_metadata: Metadata
    error: Error | None
    _stamp = field_validator('requested_at')(stamp)

    @field_validator('data_as_of')
    @classmethod
    def as_of(cls, v):
        return stamp(v) if v is not None else v

    @model_validator(mode='after')
    def consistent(self):
        expected = {'LIVE': '12306_train_assistant', SYNTHETIC: 'local_synthetic_test_service', 'DISABLED': 'disabled'}
        if self.provider != expected[self.source_type]:
            raise ValueError('PROVIDER_CLASSIFICATION_MISMATCH')
        if self.source_type == 'DISABLED' and self.error is None:
            raise ValueError('DISABLED_WITH_SUCCESS')
        if self.source_type == 'LIVE' and self.source_metadata.upstream_commit != UPSTREAM_COMMIT:
            raise ValueError('UNPINNED_UPSTREAM')
        start = datetime.fromisoformat(self.requested_at)
        observed = datetime.fromisoformat(self.source_metadata.observed_at)
        if not 0 <= (observed-start).total_seconds() <= 120 or (observed-datetime.now(timezone.utc)).total_seconds() > 300:
            raise ValueError('INVALID_QUERY_TIMESTAMP')
        if self.data_as_of is not None and datetime.fromisoformat(self.data_as_of) > observed:
            raise ValueError('FUTURE_DATA_AS_OF')
        if self.error is not None:
            if self.status not in ('SOURCE_UNAVAILABLE', 'LIVE_DISABLED') or self.trains or self.stops or self.transfers:
                raise ValueError('ERROR_RESULT_MISMATCH')
            return self
        if self.operation == 'left-ticket':
            if self.stops or self.transfers or self.status != train_status(self.trains):
                raise ValueError('TICKET_STATUS_MISMATCH')
        elif self.operation == 'route':
            if self.trains or self.transfers or self.status != ('FOUND' if self.stops else 'NO_MATCH'):
                raise ValueError('ROUTE_STATUS_MISMATCH')
        elif self.trains or self.stops or self.status != transfer_status(self.transfers):
            raise ValueError('TRANSFER_STATUS_MISMATCH')
        keys = [(t.train_no, t.date, t.from_city, t.to_city, t.seat_type) for t in self.trains]
        if len(keys) != len(set(keys)) or any(t.date != self.query.train_date for t in self.trains):
            raise ValueError('DUPLICATE_OR_WRONG_DATE')
        stops = [s.station_no for s in self.stops]
        if stops != sorted(set(stops)):
            raise ValueError('INVALID_STOP_SEQUENCE')
        transfer_keys = [tuple((t.train_no, t.date, t.depart, t.seat_type) for t in item.legs) for item in self.transfers]
        if len(transfer_keys) != len(set(transfer_keys)):
            raise ValueError('DUPLICATE_TRANSFER')
        return self
