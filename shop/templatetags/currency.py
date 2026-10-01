from decimal import Decimal, ROUND_HALF_UP

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def khr(value):
    try:
        amount = Decimal(str(value)) * Decimal(settings.CAMBODIA_KHR_PER_USD)
    except (TypeError, ValueError, ArithmeticError):
        return '៛0'
    return f'៛{amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP):,}'
