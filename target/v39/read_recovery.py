"""Prove a corrected inventory read without erasing its original failed attempt."""


def inventory_recoveries(events):
    recovered={}
    rows=[e for e in events if e.get('event')=='tool_end' and e.get('executed') is True]
    for index,failed in enumerate(rows):
        if failed.get('tool')!='railway_check_inventory' or failed.get('ok') is not False:
            continue
        if (failed.get('result') or {}).get('error')!='STATION_ID_REQUIRED':
            continue
        original=failed.get('args') or {}
        for later_index in range(index+1,len(rows)):
            later=rows[later_index];args=later.get('args') or {};result=later.get('result') or {}
            if later.get('tool')!='railway_check_inventory' or later.get('ok') is not True:
                continue
            if result.get('status') not in ('SIMULATED_AVAILABLE','INVENTORY_SOLD_OUT','INVENTORY_INSUFFICIENT') or type(result.get('available')) is not int:
                continue
            endpoints=('origin_stop_id','destination_stop_id')
            if {k:v for k,v in original.items() if k not in endpoints}!={k:v for k,v in args.items() if k not in endpoints}:
                continue
            def same_station(field):
                name,station_id=original.get(field),args.get(field)
                if not name or not station_id:return False
                if name==station_id:return True
                for lookup in rows[index+1:later_index]:
                    data=lookup.get('result') or {}
                    if lookup.get('tool')!='railway_search_stations' or lookup.get('ok') is not True or data.get('status')!='FOUND':continue
                    if (lookup.get('args') or {}).get('name')!=name:continue
                    candidates=data.get('data') or []
                    if len(candidates)==1 and candidates[0].get('stop_name')==name and candidates[0].get('stop_id')==station_id:return True
                return False
            if all(same_station(field) for field in endpoints) and failed.get('call_id') and later.get('call_id'):
                recovered[failed['call_id']]=later['call_id'];break
    return recovered
