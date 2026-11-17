import pytest

from web.business_panels import booking_inputs


DOCUMENT = '11010519491231002X'
PHONE = '19900000001'


@pytest.mark.parametrize(('text', 'expected'), [
    ('单名', ['单名']),
    ('三三，二二', ['三三', '二二']),
    (' 甲、、乙 ， 丙,丁；戊;\r\n己 ', list('甲乙丙丁戊己')),
    ('、,；;\n  ， ', []),
])
def test_booking_name_separators(text, expected):
    names, errors = booking_inputs(text, DOCUMENT, PHONE)
    assert names == expected
    assert bool(errors) is (not expected)


def test_over_six_names_are_rejected_without_truncation():
    names, errors = booking_inputs('甲、乙、丙、丁、戊、己、庚', DOCUMENT, PHONE)
    assert len(names) == 7
    assert len(errors) == 1 and errors[0].startswith('乘客姓名：')


@pytest.mark.parametrize(('document', 'phone', 'fields'), [
    ('', '', ('身份证号码', '手机号码')),
    ('123', PHONE, ('身份证号码',)),
    (DOCUMENT, '123', ('手机号码',)),
    (DOCUMENT.lower(), ' ' + PHONE + ' ', ()),
    ('１' * 18, PHONE, ('身份证号码',)),
    (DOCUMENT, '1' + '９' * 10, ('手机号码',)),
])
def test_booking_diagnostics_identify_only_invalid_fields(document, phone, fields):
    names, errors = booking_inputs('三三，二二', document, phone)
    assert names == ['三三', '二二']
    assert tuple(msg.split('：')[0] for msg in errors) == fields
