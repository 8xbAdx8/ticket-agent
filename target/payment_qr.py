"""Order-identification QR only: yuan amounts, no payment URL or credentials."""
from decimal import Decimal, InvalidOperation
import io
import json


def yuan(value):
    """Validate the existing orders.amount unit (yuan), never convert from fen."""
    if isinstance(value, bool):
        raise ValueError('订单金额无效')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('0.01')):
            raise ValueError('订单金额无效')
        return amount.quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('订单金额无效') from exc


def payment_payload(order_id, amount, amount_yuan):
    if not isinstance(order_id, str) or not order_id.strip() or len(order_id) > 100:
        raise ValueError('订单号无效')
    total = yuan(amount)
    if total != yuan(amount_yuan):
        raise ValueError('订单金额单位不一致')
    return {'order_id': order_id, 'amount': float(total), 'amount_yuan': str(total),
            'currency': 'CNY', 'amount_unit': 'yuan', 'demo': True}


def render_qr(order_id, amount, amount_yuan) -> bytes:
    """Encode the supplied authoritative order fields as a PNG; no side effects."""
    import qrcode
    from PIL.PngImagePlugin import PngInfo
    payload = json.dumps(payment_payload(order_id, amount, amount_yuan),
                         ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')
    metadata = PngInfo()
    metadata.add_text('ticket_demo_payment', payload)
    output = io.BytesIO()
    image.save(output, format='PNG', pnginfo=metadata)
    return output.getvalue()
