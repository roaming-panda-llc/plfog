"""Backfill TabEntry snapshot split fields from existing Product data.

For every existing TabEntry:
- admin_percent = BillingSettings.default_admin_percent (or 20.00 if missing)
- split_mode = SINGLE_GUILD (default)
- split_guild_ids = []
- guild_id = product.guild_id if the entry has a product, else NULL

Also zero-out any null TabCharge.application_fee so later code doesn't need to
branch on the null case.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import migrations


def backfill(apps: Any, schema_editor: Any) -> None:
    BillingSettings = apps.get_model("billing", "BillingSettings")
    Product = apps.get_model("billing", "Product")
    TabEntry = apps.get_model("billing", "TabEntry")
    TabCharge = apps.get_model("billing", "TabCharge")

    bs = BillingSettings.objects.filter(pk=1).first()
    default_pct = bs.default_admin_percent if bs and bs.default_admin_percent is not None else Decimal("20.00")

    # Build a product -> guild_id lookup to avoid N+1 queries
    product_guilds = dict(Product.objects.values_list("pk", "guild_id"))

    updates: list = []
    for entry in TabEntry.objects.all().only(
        "pk", "product_id", "admin_percent", "split_mode", "split_guild_ids", "guild_id"
    ):
        entry.admin_percent = default_pct
        entry.split_mode = "single_guild"
        entry.split_guild_ids = []
        if entry.product_id is not None:
            entry.guild_id = product_guilds.get(entry.product_id)
        else:
            entry.guild_id = None
        updates.append(entry)

    if updates:
        TabEntry.objects.bulk_update(
            updates,
            fields=["admin_percent", "split_mode", "split_guild_ids", "guild_id"],
            batch_size=500,
        )

    # Normalise application_fee — zero out nulls so aggregation doesn't need
    # Coalesce() later and reports don't have to handle a null branch.
    TabCharge.objects.filter(application_fee__isnull=True).update(application_fee=Decimal("0.00"))


def reverse_backfill(apps: Any, schema_editor: Any) -> None:
    """Reverse: null out the backfilled split fields so 0007 can be reversed cleanly."""
    TabEntry = apps.get_model("billing", "TabEntry")
    TabEntry.objects.all().update(admin_percent=None, split_mode="single_guild", split_guild_ids=[], guild_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_add_split_fields"),
    ]

    operations = [
        migrations.RunPython(backfill, reverse_backfill),
    ]
