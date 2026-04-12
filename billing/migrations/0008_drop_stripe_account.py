"""Drop TabCharge.stripe_account FK and the StripeAccount model entirely.

As of v1.5.0, all charges route through the single platform Stripe account.
Per-guild OAuth Connect and direct-keys flows are gone. Existing rows have
their stripe_account_id nulled before the field is removed.
"""

from __future__ import annotations

from typing import Any

from django.db import migrations, models


def null_stripe_account_fks(apps: Any, schema_editor: Any) -> None:
    """Defensive: null out any TabCharge.stripe_account references before drop."""
    TabCharge = apps.get_model("billing", "TabCharge")
    TabCharge.objects.filter(stripe_account__isnull=False).update(stripe_account=None)


def reverse_noop(apps: Any, schema_editor: Any) -> None:
    """No-op reverse (explicitly approved — irreversible by design).

    StripeAccount is permanently removed. Reversing this migration requires
    restoring the model definition in models.py, which is outside the scope of
    a data-migration reverse function.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_tighten_tab_entry_snapshot"),
    ]

    operations = [
        migrations.RunPython(null_stripe_account_fks, reverse_noop),
        migrations.RemoveField(
            model_name="tabcharge",
            name="stripe_account",
        ),
        migrations.DeleteModel(
            name="StripeAccount",
        ),
        migrations.AlterField(
            model_name="tabcharge",
            name="application_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                editable=False,
                help_text="DEPRECATED — historical only, not written after v1.5.0.",
                max_digits=8,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="tabcharge",
            name="stripe_checkout_session_id",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="DEPRECATED — historical only, not written after v1.5.0.",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="tabcharge",
            name="stripe_checkout_url",
            field=models.URLField(
                blank=True,
                editable=False,
                help_text="DEPRECATED — historical only, not written after v1.5.0.",
            ),
        ),
    ]
