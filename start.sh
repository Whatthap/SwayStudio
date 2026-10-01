#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
python manage.py shell -c "from django.core.management import call_command; from shop.models import Product; call_command('seed_products') if not Product.objects.exists() else None"
exec gunicorn config.wsgi:application