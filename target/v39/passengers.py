"""Finite placeholder detection, not real-name or identity verification."""
import unicodedata

PLACEHOLDERS = frozenset({
    '请提供乘客姓名', '请填写乘客姓名', '请输入乘客姓名', '请补充乘客姓名',
    '请提供姓名', '请填写姓名', '请输入姓名', '乘客姓名', '姓名',
    '待提供', '待补充', '待填写', '未提供', '未知',
    'tbd', 'unknown', 'passenger_name', 'your_name',
    'please provide passenger name',
})


def has_placeholders(names):
    return isinstance(names, list) and any(
        isinstance(n, str) and unicodedata.normalize('NFKC', n).strip(
            ' \t\r\n。.:：<>[]【】()（）').casefold() in PLACEHOLDERS
        for n in names)


def require_names(names, count):
    # Preserve synthetic, single-character and international passenger names.
    if (not isinstance(names, list) or len(names) != count
            or any(not isinstance(n, str) or not n.strip() for n in names)):
        raise ValueError('PASSENGER_MISMATCH')
    if has_placeholders(names):
        raise ValueError('PASSENGER_NAME_REQUIRED')
