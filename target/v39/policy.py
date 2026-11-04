"""User-approved, versioned D9 B for V3.9.1 local simulation only."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from target.v39.store import integer

PRODUCT=json.loads(Path(__file__).with_name('policy_profile.json').read_text(encoding='utf8'))
VERSION=PRODUCT['version']


@dataclass(frozen=True)
class Policy:
    version: str = VERSION
    profile: str | None = PRODUCT['profile']
    approved: bool = PRODUCT['approved']
    partial_change: bool = PRODUCT['partial_change']
    further_refund: bool = PRODUCT['further_refund']
    max_changes: int = 1

    def require(self):
        if not self.approved or self.profile not in ('P02_STRICT','CHANGED_REFUND_P01'):
            raise ValueError('POLICY_PENDING_USER_DECISION')
        if type(self.approved) is not bool or self.max_changes!=1:raise ValueError('INVALID_POLICY')

    def refund(self, item_fares, departure, now, *, changed=False, already_refunded=False):
        self.require()
        if changed and self.profile=='P02_STRICT':raise ValueError('REFUND_NOT_ALLOWED')
        if already_refunded and not self.further_refund:raise ValueError('POLICY_FURTHER_REFUND_NOT_APPROVED')
        seconds=(datetime.fromisoformat(departure)-datetime.fromisoformat(now)).total_seconds()
        if seconds<=0:raise ValueError('REFUND_AFTER_DEPARTURE')
        rate=500 if seconds>172800 else 1000 if seconds>=86400 else 2000
        result=[]
        for value in item_fares:
            integer(value,'fare_fen',1)
            fee=(value*rate+5000)//10000
            result.append({'amount_fen':value,'fee_fen':fee,'net_fen':value-fee})
        return result

    def change(self, count, *, already_refunded=False):
        self.require();integer(count,'change_count',0,1)
        if count>=self.max_changes:raise ValueError('CHANGE_LIMIT_REACHED')
        if already_refunded and not self.partial_change:raise ValueError('POLICY_PARTIAL_CHANGE_NOT_APPROVED')
