"""Read-only GTFS evidence for the V3.10 DSL quality gate."""
import re
import sqlite3

from target.scenario_output_contract import UNKNOWN, result_shape, snapshot_shape, traverse
from target.scenario_v310 import CHAT_REFERENCE, assert_value, lookup, resolve, valid_path
from target.v39.static import RailwayStatic

STATIC_METHODS = {
    'railway_search_stations': 'stations',
    'railway_query_trips': 'trips',
    'railway_trip_stops': 'trip',
}
TRAIN = re.compile(r'(?<![A-Za-z0-9])[GDCZTKYSL]\d{1,5}(?![A-Za-z0-9])', re.IGNORECASE | re.ASCII)
INDEXED_TRAIN = re.compile(r'result\.data\.([0-9]+)\.trip_short_name\Z')
TRIP_REFERENCE = re.compile(r'\$(\w+)\.data\.([0-9]+)\.trip_id\Z', re.ASCII)
LOOKUP_ERRORS = (KeyError, IndexError, ValueError, TypeError)
STATIC_ERRORS = (OSError, sqlite3.Error, *LOOKUP_ERRORS)
ISO_DATE = re.compile(r'(?<![0-9])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9])')
STOP_ID = re.compile(r'(?<![A-Za-z0-9])[A-Z]{3}(?![A-Za-z0-9])')
RUNTIME_ERRORS = {
    'railway_pay_order': {'AMOUNT_MISMATCH'},
    'confirm': {'V39_CONTEXT_REQUIRED', 'DATABASE_RECEIPT_NOT_VERIFIED', 'PAYMENT_FAILED'},
    'foreign_confirm': {'PROPOSAL_NOT_FOUND'},
    'foreign_order': {'ORDER_FORBIDDEN'},
}


def issue(code, step, message, path=None):
    result = dict(code=code, step=step, message=message)
    if path is not None:
        result['path'] = path
    return result


def prompt_sample():
    """Bounded sample from the adapter used by the registry."""
    try:
        static = RailwayStatic()
        args = dict(service_date='2026-11-05', origin_stop_id='AOH',
                    destination_stop_id='HGH', train_no='G7331', limit=1)
        trips = static.trips(**args)
        row = trips['data'][0]
        stop_args = dict(trip_id=row['trip_id'], service_date=args['service_date'])
        detail = static.trip(**stop_args)
        stops = detail['data']['stops']
        return {
            'dataset_sha256': detail['database_sha256'],
            'railway_query_trips': {'args': args, 'result': {
                'status': trips['status'], 'returned_count': trips['returned_count'],
                'data': [{k: row[k] for k in ('trip_short_name', 'trip_id')}],
            }},
            'railway_trip_stops': {'args': stop_args, 'result_shape': {
                'status': detail['status'],
                'data': {'trip': {k: detail['data']['trip'][k] for k in ('trip_id', 'trip_short_name')},
                         'stops': [{k: stops[0][k] for k in ('stop_id', 'stop_name', 'stop_sequence')}]},
            }, 'actual_full_stop_count': len(stops), 'stops_sample_only': True},
        }
    except STATIC_ERRORS:
        return {'status': 'STATIC_EVIDENCE_UNAVAILABLE'}


def train_targets(case):
    context = case.get('generation_requirements')
    if isinstance(context, dict):
        requested = TRAIN.findall(' '.join(str(context.get(k, '')) for k in ('objective', 'constraints')))
        if requested:
            return {t.upper() for t in requested}
    text = ' '.join([case['objective'], case['title'], *case['conversation']])
    targets = {t.upper() for t in TRAIN.findall(text)}
    if targets:
        return targets
    return {
        check['value'].upper()
        for step in case['integration_steps'] if step.get('tool') == 'railway_query_trips'
        for check in step['checks']
        if INDEXED_TRAIN.fullmatch(check['path']) and check['op'] in ('eq', 'contains')
        and isinstance(check['value'], str) and TRAIN.fullmatch(check['value'])
    }


def argument_references(value):
    if isinstance(value, str) and value.startswith('$'):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from argument_references(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from argument_references(nested)


def validate_evidence(case, schemas, validator):
    """Verify static lookups in isolation. Never dispatch or run a candidate."""
    issues, warnings, evidence = [], [], []
    snapshot = snapshot_shape()
    shapes, values, queried = {}, {}, {}
    verified_trains, verified_stops, verified_counts, verified_first_stops = set(), set(), set(), set()
    request = case.get('generation_requirements')
    request = request if isinstance(request, dict) else {}
    objective = str(request.get('objective', ''))
    constraints = str(request.get('constraints', ''))
    positive = not re.search(r'拒绝|禁用|阻止|不存在|失效|无匹配|blocked|no_match|invalid', objective, re.I)
    asks_query = bool(re.search(r'查询|车次|经停|railway_query_trips|trip_stops', objective, re.I))
    asks_stops = bool(re.search(r'经停|trip_stops', objective + constraints, re.I))
    asks_count = bool(re.search(r'站数|车站数量|经停.{0,6}数量|stop count', objective + constraints, re.I))
    dates = set(ISO_DATE.findall(objective))
    station_tokens = list(dict.fromkeys(STOP_ID.findall(objective)))
    station_ids = None
    targets = train_targets(case)
    read_only_scope = bool(targets and asks_stops and re.search(r'只读|不创建订单|零订单|不下单|read.only', objective + constraints, re.I))
    requires_no_order_check = read_only_scope and 'metrics.order_count' in constraints
    requires_flag_first = bool(re.search(r'先[^。；]{0,32}flag', objective + constraints, re.I)
                               and re.search(r'flag\.enabled\s*=\s*true', constraints, re.I))
    no_order_check = False
    explicit_flags = set()
    static = None
    enabled, read_only = True, False
    for index, step in enumerate(case['integration_steps']):
        def reject(code, message, path=None):
            issues.append(issue(code, index, f'step {index}: {message}', path))

        def reference_ready(ref):
            path = ref[1:]
            root = path.partition('.')[0]
            if not valid_path(path) or root not in shapes:
                reject('UNBOUND_REFERENCE', f'unbound reference: {ref}', ref)
                return False
            if root in values:
                try:
                    lookup(values, path)
                except LOOKUP_ERRORS:
                    reject('MISSING_REFERENCE', f'output reference missing: {ref}', ref)
                    return False
            else:
                try:
                    if traverse(shapes[root], path.split('.')[1:]) is UNKNOWN:
                        warnings.append(f'step {index}: reference has no verified output shape: {ref}')
                except KeyError:
                    reject('MISSING_REFERENCE', f'output reference missing: {ref}', ref)
                    return False
            return True

        kind = step['kind']
        name = step.get('tool') if kind == 'tool' else None
        raw_args = step.get('args', {}) if name else {}
        refs = list(argument_references(raw_args))
        if kind in ('confirm', 'foreign_confirm', 'foreign_order'):
            refs += list(argument_references(step.get('proposal', step.get('order'))))
        if kind == 'chat':
            refs += ['$' + path for path in CHAT_REFERENCE.findall(step['message'])]
        ready = all([reference_ready(ref) for ref in refs])
        result = None
        if kind == 'flag' and type(step.get('enabled')) is bool:
            enabled = step['enabled']
            result = {'enabled': enabled}
        if kind == 'history':
            read_only = step['enabled']
            result = {'read_only': read_only}
        args = None
        expected_error = step.get('expected_error')
        if name and ready and (read_only or not enabled):
            result = {'error': 'READ_ONLY_HISTORY' if read_only else 'V39_CONTEXT_REQUIRED'}
        elif name and ready and all(ref[1:].partition('.')[0] in values for ref in refs):
            args = resolve(raw_args, values)
            if not validator(schemas[name]).is_valid(args):
                result = {'error': 'INVALID_RAILWAY_ARGUMENTS'}
                if expected_error != result['error']:
                    reject('RESOLVED_TOOL_ARGUMENTS_INVALID', f'resolved tool arguments do not match {name}', 'args')
            elif expected_error == 'INVALID_RAILWAY_ARGUMENTS':
                reject('EXPECTED_ERROR_MISMATCH', f'arguments conform to {name}', 'expected_error')
            elif name in STATIC_METHODS:
                try:
                    if static is None:
                        static = RailwayStatic()
                    result = getattr(static, STATIC_METHODS[name])(**args)
                except ValueError as exc:
                    if str(exc) == 'STATIC_DATA_IDENTITY_MISMATCH':
                        warnings.append(f'step {index}: verified static dataset unavailable')
                    else:
                        result = {'error': str(exc)}
                except (OSError, sqlite3.Error):
                    warnings.append(f'step {index}: verified static dataset unavailable')
        if result is not None and result.get('error') != expected_error:
            reject('EXPECTED_ERROR_MISMATCH', f"observed error {result.get('error')!r}, expected {expected_error!r}", 'expected_error')
        if result is None and expected_error and expected_error not in RUNTIME_ERRORS.get(name or kind, set()):
            warnings.append(f'step {index}: no evidence for expected error {expected_error}')

        if name in STATIC_METHODS and ready and result is None and refs:
            warnings.append(f'step {index}: static tool inputs depend on unverified runtime output')

        shapes['state'] = snapshot['state']
        shape = result if result is not None else result_shape(step)
        alias = step.get('as')
        if alias:
            shapes[alias] = shape
            if result is not None:
                values[alias] = result

        if read_only_scope and (kind not in ('tool', 'flag', 'history') or (name and name not in STATIC_METHODS)):
            reject('READ_ONLY_SCOPE_VIOLATION', 'requested static lookup cannot include a business action', 'kind')
        if requires_flag_first and name in STATIC_METHODS and True not in explicit_flags:
            reject('FLAG_ORDER_MISMATCH', 'verify enabled=true before the static lookups', 'kind')

        if name == 'railway_query_trips' and targets and not step.get('expected_error'):
            train = raw_args.get('train_no')
            if not isinstance(train, str) or train not in targets or 'trip_id' in raw_args:
                reject('TRAIN_FILTER_REQUIRED', f'use exact train_no from {sorted(targets)} for the list query', 'args.train_no')
            else:
                indices = {
                    int(match[1]) for check in step['checks']
                    if (match := INDEXED_TRAIN.fullmatch(check['path']))
                    and check['op'] == 'eq' and check['value'] == train
                }
                if not indices:
                    reject('TRAIN_SELECTION_UNVERIFIED', f'assert trip_short_name is {train} for the selected row', 'checks')
                if indices and result is not None and not result.get('error'):
                    records = result.get('data', [])
                    verified = {
                        pos for pos in indices if isinstance(records, list) and pos < len(records)
                        and records[pos].get('trip_short_name') == train
                    }
                    if not verified:
                        reject('TRAIN_MISMATCH', f'no asserted row matches {train}', 'result.data')
                    if verified and request and positive and asks_query:
                        if len(dates) == 1 and args['service_date'] not in dates:
                            reject('REQUESTED_DATE_MISMATCH', 'query date differs from the requested date', 'args.service_date')
                            verified.clear()
                        if station_ids is None:
                            try:
                                station_ids = [token for token in station_tokens if static.station(token)['status'] == 'FOUND']
                            except STATIC_ERRORS:
                                warnings.append(f'step {index}: requested station IDs could not be verified')
                                station_ids = []
                                verified.clear()
                        if len(station_ids) == 2 and [args.get('origin_stop_id'), args.get('destination_stop_id')] != station_ids:
                            reject('REQUESTED_ROUTE_MISMATCH', 'query must use the requested origin and destination', 'args')
                            verified.clear()
                    if verified:
                        verified_trains.add(train)
                    if alias:
                        queried[alias] = (verified, args['service_date'], train)

        stop_train = None
        if name == 'railway_trip_stops' and targets and not step.get('expected_error'):
            trip_ref = raw_args.get('trip_id', '')
            match = TRIP_REFERENCE.fullmatch(trip_ref) if isinstance(trip_ref, str) and valid_path(trip_ref[1:]) else None
            selected = queried.get(match[1]) if match else None
            if not selected or int(match[2]) not in selected[0]:
                reject('TRIP_REFERENCE_UNVERIFIED', 'trip_id must reference the verified row of the train query', 'args.trip_id')
            elif ready and result is not None and not result.get('error'):
                if str(result.get('service_date')) != str(selected[1]).replace('-', ''):
                    reject('TRIP_DATE_MISMATCH', 'stop lookup must use the verified service date', 'args.service_date')
                elif result['status'] == 'FOUND' and result['data']['trip']['trip_short_name'] == selected[2]:
                    stop_train = selected[2]
                    verified_stops.add(stop_train)
                else:
                    reject('TRIP_DETAIL_MISMATCH', 'stop lookup did not return the verified train', 'result.data.trip')

        for check in step['checks']:
            path = check['path']
            check_refs = list(argument_references(check['value']))
            if not all([reference_ready(ref) for ref in check_refs]):
                continue
            if read_only_scope and path in ('metrics.order_count', 'metrics.hold_count', 'metrics.transaction_count') and not check_refs:
                metric = path.split('.')[1]
                if not assert_value(check, {'metrics': {metric: 0}}, {})['ok']:
                    reject('READ_ONLY_ORDER_COUNT_MISMATCH', 'read-only scenario starts with zero orders, holds and transactions', path)
                if path == 'metrics.order_count' and check['op'] == 'eq' and type(check['value']) is int and check['value'] == 0:
                    no_order_check = True
            try:
                if result is not None and path.startswith('result.'):
                    actual = lookup({'result': result}, path)
                else:
                    actual = traverse(dict(snapshot, result=shape), path.split('.'))
            except LOOKUP_ERRORS:
                reject('OUTPUT_PATH_INVALID', f'unsupported output path: {path}', path)
                continue
            if actual is UNKNOWN:
                warnings.append(f'step {index}: unverified output shape: {path}')
                continue
            if check['op'] == 'len' and isinstance(actual, dict):
                message = 'use result.data.stops for stop counts' if name == 'railway_trip_stops' else 'object is not an array'
                reject('OUTPUT_TYPE_MISMATCH', message, path)
                continue
            if result is None or not path.startswith('result.'):
                continue
            if any(ref[1:].partition('.')[0] not in values for ref in check_refs):
                warnings.append(f'step {index}: check depends on unverified runtime output: {path}')
                continue
            assertion = assert_value(check, {'result': result}, values)
            code = 'STATIC_ASSERTION_MISMATCH' if name in STATIC_METHODS else 'DETERMINISTIC_ASSERTION_MISMATCH'
            if check['op'] == 'len' and isinstance(actual, (list, str)):
                assertion['actual'] = len(actual)
                if name == 'railway_trip_stops' and path == 'result.data.stops':
                    code = 'STOP_COUNT_MISMATCH'
            evidence.append(dict(step=index, tool=name, **assertion))
            if assertion['ok'] and code == 'STOP_COUNT_MISMATCH' and stop_train:
                verified_counts.add(stop_train)
            if assertion['ok'] and stop_train and check['op'] == 'eq' and path == 'result.data.stops.0.stop_id':
                verified_first_stops.add(stop_train)
            if assertion['ok'] and kind == 'flag' and path == 'result.enabled' and check['op'] == 'eq':
                explicit_flags.add(result['enabled'])
            if not assertion['ok']:
                reject(code, f'{path} check failed: expected {assertion["expected"]!r}, observed {assertion["actual"]!r}', path)
    if request:
        if targets and positive and asks_query:
            if not targets <= verified_trains:
                issues.append(issue('REQUESTED_TRAIN_NOT_VERIFIED', None, 'requested train query is missing or unverified'))
            if asks_stops and not targets <= verified_stops:
                issues.append(issue('REQUESTED_STOPS_NOT_VERIFIED', None, 'requested full stop lookup is missing or unverified'))
            if asks_count and not targets <= verified_counts:
                issues.append(issue('REQUESTED_STOP_COUNT_NOT_VERIFIED', None, 'requested stop count needs a verified length assertion'))
            if '首站' in objective + constraints and not targets <= verified_first_stops:
                issues.append(issue('REQUESTED_FIRST_STOP_NOT_VERIFIED', None, 'requested first stop needs an exact stop_id assertion'))
        if requires_no_order_check and not no_order_check:
            issues.append(issue('REQUESTED_ORDER_COUNT_NOT_CHECKED', None, 'include metrics.order_count=0 for the read-only case'))
        for literal, expected in (('true', True), ('false', False)):
            if re.search(r'flag\.enabled\s*=\s*' + literal, constraints, re.I) and expected not in explicit_flags:
                issues.append(issue('REQUESTED_FLAG_NOT_VERIFIED', None, f'flag.enabled={literal} needs an explicit matching check'))
    return issues, sorted(set(warnings)), evidence

