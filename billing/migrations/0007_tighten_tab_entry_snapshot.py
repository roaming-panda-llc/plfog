"""Tighten TabEntry.admin_percent to non-null after 0006 backfill.

Safe because 0006_backfill_split_fields populates every existing row, and
Tab.add_entry() now snapshots the field on every new row.
"""

from __future__ import annotations

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_backfill_split_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tabentry",
            name="admin_percent",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=5,
                help_text=(
                    "Admin percentage applied to this entry at the time it was created. "
                    "Guild share = amount * (1 - admin_percent/100)."
                ),
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                    django.core.validators.MaxValueValidator(Decimal("100")),
                ],
            ),
        ),
    ]
