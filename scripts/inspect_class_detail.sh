#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
exec .venv/bin/python manage.py shell <<'PY'
from django.test import Client
from django.contrib.auth import get_user_model
from classes.models import ClassOffering

User = get_user_model()
u = User.objects.filter(is_superuser=True).first() or User.objects.first()
c = Client()
c.force_login(u)
off = ClassOffering.objects.first()
print(f"class: {off.pk} status={off.status}")
r = c.get(f"/classes/admin/{off.pk}/")
html = r.content.decode()
for line in html.splitlines():
    s = line.strip()
    if ('archive' in s.lower() or 'open-confirm' in s or 'pl-modal-backdrop' in s
            or 'confirm_id' in s or "del-" in s or 'x-data' in s and 'open' in s):
        print(s[:220])
PY
