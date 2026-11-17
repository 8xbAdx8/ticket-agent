"""P06 高铁模拟行李计算；不对未定义的尺寸规则作推断。"""
from decimal import Decimal, InvalidOperation


def calculate_baggage(passenger_type, total_kg, length_cm, width_cm, height_cm):
    if passenger_type not in ('成人', '儿童'):
        raise ValueError('乘客类型仅支持成人或儿童')
    def number(value, label, allow_zero=False):
        try:
            n=Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(label+'必须是有效数字') from None
        if not n.is_finite() or n < 0 or (not allow_zero and n == 0):
            raise ValueError(label+'必须为'+('非负' if allow_zero else '正')+'有限数字')
        return n
    total=number(total_kg,'总重量',True)
    dimensions=[number(v,'尺寸') for v in (length_cm,width_cm,height_cm)]
    free=Decimal(20 if passenger_type=='成人' else 10)
    excess=max(Decimal(0),total-free)
    perimeter=sum(dimensions)
    return {'policy_ref':'P06','passenger_type':passenger_type,'total_kg':str(total),
            'free_kg':str(free),'excess_kg':str(excess),'rate_yuan_per_kg':'5',
            'weight_fee_yuan':str(excess*Decimal(5)), 'item_sum_cm':str(perimeter),
            'size_status':'符合' if perimeter<=160 else '超出160厘米；政策未说明后续处理或尺寸收费',
            'note':'仅计算一名旅客携带品总重量和一件物品尺寸；尺寸超限的处理与费用未定义，重量费用不等于总费用。'}
