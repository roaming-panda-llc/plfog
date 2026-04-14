"""Wipe products + tab entries/charges, then drop legacy split fields.

This is a one-time, irreversible migration tied to the v1.7 product-revenue-
splits feature. It assumes the operator has backed up the database before
running it. Re-applying it on an already-migrated database is a no-op for the
data wipe (everything is already gone) and the schema changes are idempotent
under Django's migration framework.
"""

from django.db import migrations


def wipe_billing_data(apps, schema_editor):
    Product = apps.get_model("billing", "Product")
    TabEntry = apps.get_model("billing", "TabEntry")
    TabCharge = apps.get_model("billing", "TabCharge")

    # Delete in dependency order: TabEntry FK -> TabCharge, Product;
    # TabCharge FK -> Tab (kept). Wiping TabEntry/TabCharge first is safest.
    TabEntry.objects.all().delete()
    TabCharge.objects.all().delete()
    Product.objects.all().delete()


def cannot_reverse(apps, schema_editor):
    raise RuntimeError(
        "Migration 0010 is irreversible: it wipes Product/TabEntry/TabCharge data. "
        "Restore from a database backup if you need to roll back."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_product_revenue_split_tabentry_split"),
    ]

    operations = [
        migrations.RunPython(wipe_billing_data, cannot_reverse),
        # Drop the legacy DB-level CHECK constraint first so SQLite doesn't
        # rebuild the table with a reference to the about-to-be-dropped column.
        migrations.RemoveConstraint(
            model_name="product",
            name="product_admin_percent_override_range",
        ),
        migrations.RemoveField(model_name="product", name="admin_percent_override"),
        migrations.RemoveField(model_name="product", name="split_mode"),
        migrations.RemoveField(model_name="product", name="is_active"),
        migrations.RemoveField(model_name="tabentry", name="admin_percent"),
        migrations.RemoveField(model_name="tabentry", name="split_mode"),
        migrations.RemoveField(model_name="tabentry", name="guild"),
        migrations.RemoveField(model_name="tabentry", name="split_guild_ids"),
    ]
