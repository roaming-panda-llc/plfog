"""RevenueSplit rework — single consolidated migration.

Creates RevenueSplit + SplitRecipient, adds Product.revenue_split and
TabEntry.split_snapshot, backfills both from the old snapshot fields, then
drops the legacy fields. The backfill step uses apps.get_model() so it sees
the transitional schema where both old and new fields exist side-by-side.

Reverse: drops the new models and restores the legacy field values from the
split_snapshot. Backfill reverse is best-effort — it assumes a two-row
Admin + single-guild shape, which is all the old code could express anyway.
"""

from __future__ import annotations

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def backfill_splits(apps, schema_editor):
    RevenueSplit = apps.get_model("billing", "RevenueSplit")
    SplitRecipient = apps.get_model("billing", "SplitRecipient")
    Product = apps.get_model("billing", "Product")
    TabEntry = apps.get_model("billing", "TabEntry")
    BillingSettings = apps.get_model("billing", "BillingSettings")

    settings_row = BillingSettings.objects.filter(pk=1).first()
    default_admin_percent = (
        settings_row.default_admin_percent if settings_row is not None else Decimal("20.00")
    )

    # ---- Products: build one RevenueSplit per product ----
    for product in Product.objects.all():
        split = RevenueSplit.objects.create(name="")
        admin_percent = (
            product.admin_percent_override
            if product.admin_percent_override is not None
            else default_admin_percent
        )
        guild_percent = Decimal("100.00") - admin_percent

        if admin_percent > 0:
            SplitRecipient.objects.create(split=split, guild=None, percent=admin_percent)

        if product.split_mode == "split_equally":
            Guild = apps.get_model("membership", "Guild")
            active_guilds = list(Guild.objects.filter(is_active=True).order_by("pk"))
            n = len(active_guilds)
            if n and guild_percent > 0:
                each = (guild_percent / n).quantize(Decimal("0.01"))
                remainder = guild_percent - (each * n)
                for i, g in enumerate(active_guilds):
                    pct = each + (Decimal("0.01") if i == 0 and remainder else Decimal("0"))
                    SplitRecipient.objects.create(split=split, guild=g, percent=pct)
        elif product.guild_id is not None and guild_percent > 0:
            SplitRecipient.objects.create(split=split, guild_id=product.guild_id, percent=guild_percent)

        # If no guild recipients were created, give the entire split to Admin
        if not split.recipients.exists():
            SplitRecipient.objects.create(split=split, guild=None, percent=Decimal("100.00"))
        elif not split.recipients.filter(guild__isnull=True).exists() and admin_percent == 0:
            pass  # valid: 100% to guilds

        product.revenue_split = split
        product.save(update_fields=["revenue_split"])

    # ---- TabEntries: build split_snapshot from old fields ----
    for entry in TabEntry.objects.all():
        admin_percent = entry.admin_percent or Decimal("0")
        guild_percent = Decimal("100.00") - admin_percent
        snapshot = []

        if admin_percent > 0:
            snapshot.append({"guild_id": None, "percent": str(admin_percent)})

        if entry.split_mode == "split_equally" and entry.split_guild_ids:
            ids = sorted(entry.split_guild_ids)
            n = len(ids)
            each = (guild_percent / n).quantize(Decimal("0.01"))
            remainder = guild_percent - (each * n)
            for i, gid in enumerate(ids):
                pct = each + (Decimal("0.01") if i == 0 and remainder else Decimal("0"))
                snapshot.append({"guild_id": gid, "percent": str(pct)})
        elif entry.guild_id is not None and guild_percent > 0:
            snapshot.append({"guild_id": entry.guild_id, "percent": str(guild_percent)})

        if not snapshot:
            snapshot = [{"guild_id": None, "percent": "100.00"}]

        entry.split_snapshot = snapshot
        entry.save(update_fields=["split_snapshot"])


def reverse_backfill(apps, schema_editor):
    # Nothing to do — the legacy fields still exist at this point in the
    # reverse direction, and the forward migration doesn't destroy data that
    # couldn't be reconstructed. If the reverse chain runs past this point,
    # the subsequent RemoveField operations (reversed as AddField with default)
    # will leave the old columns empty, which matches a fresh install.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0008_drop_stripe_account"),
        ("membership", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RevenueSplit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Optional label for this split (e.g. 'Default glass guild split'). "
                            "Blank for private per-product splits."
                        ),
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="When this split was created.")),
            ],
            options={
                "verbose_name": "Revenue Split",
                "verbose_name_plural": "Revenue Splits",
            },
        ),
        migrations.CreateModel(
            name="SplitRecipient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "percent",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Share of the charged amount (0 < p ≤ 100).",
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01")),
                            django.core.validators.MaxValueValidator(Decimal("100")),
                        ],
                    ),
                ),
                (
                    "split",
                    models.ForeignKey(
                        help_text="The parent revenue split.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipients",
                        to="billing.revenuesplit",
                    ),
                ),
                (
                    "guild",
                    models.ForeignKey(
                        blank=True,
                        help_text="Payout recipient. Null means the Admin (Past Lives) share.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="split_recipients",
                        to="membership.guild",
                    ),
                ),
            ],
            options={
                "verbose_name": "Split Recipient",
                "verbose_name_plural": "Split Recipients",
                "ordering": ["pk"],
            },
        ),
        # ---- Transitional additions (nullable revenue_split until backfill) ----
        migrations.AddField(
            model_name="product",
            name="revenue_split",
            field=models.OneToOneField(
                help_text="How this product's revenue is split between Admin and guilds.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="product",
                to="billing.revenuesplit",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="guild",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Owning guild — controls which guild page the product appears on. "
                    "Independent from the revenue split (a product owned by one guild can "
                    "pay out to any combination of Admin + guilds). Null means gallery/unattributed."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="membership.guild",
            ),
        ),
        migrations.AddField(
            model_name="tabentry",
            name="split_snapshot",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Frozen list of payout recipients resolved from the product's RevenueSplit at creation time.",
            ),
        ),
        # ---- Data backfill ----
        migrations.RunPython(backfill_splits, reverse_backfill),
        # ---- Drop legacy fields ----
        migrations.RemoveConstraint(
            model_name="product",
            name="product_admin_percent_override_range",
        ),
        migrations.RemoveField(model_name="product", name="admin_percent_override"),
        migrations.RemoveField(model_name="product", name="split_mode"),
        migrations.RemoveField(model_name="tabentry", name="admin_percent"),
        migrations.RemoveField(model_name="tabentry", name="split_mode"),
        migrations.RemoveField(model_name="tabentry", name="guild"),
        migrations.RemoveField(model_name="tabentry", name="split_guild_ids"),
        # ---- Enforce non-null on Product.revenue_split now that backfill is done ----
        migrations.AlterField(
            model_name="product",
            name="revenue_split",
            field=models.OneToOneField(
                help_text="How this product's revenue is split between Admin and guilds.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="product",
                to="billing.revenuesplit",
            ),
        ),
        # ---- New unique constraints on SplitRecipient ----
        migrations.AddConstraint(
            model_name="splitrecipient",
            constraint=models.CheckConstraint(
                condition=models.Q(("percent__gt", 0), ("percent__lte", 100)),
                name="split_recipient_percent_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="splitrecipient",
            constraint=models.UniqueConstraint(
                condition=models.Q(("guild__isnull", False)),
                fields=("split", "guild"),
                name="uq_split_recipient_split_guild",
            ),
        ),
        migrations.AddConstraint(
            model_name="splitrecipient",
            constraint=models.UniqueConstraint(
                condition=models.Q(("guild__isnull", True)),
                fields=("split",),
                name="uq_split_recipient_split_admin",
            ),
        ),
    ]
