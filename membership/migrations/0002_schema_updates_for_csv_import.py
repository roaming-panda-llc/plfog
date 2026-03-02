# Hand-written migration: schema updates for CSV import
#
# No data migration needed — project has no existing rows.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("membership", "0001_initial"),
    ]

    operations = [
        # ---------------------------------------------------------------
        # Member: make email optional, add billing_name, make join_date optional
        # ---------------------------------------------------------------
        migrations.AlterField(
            model_name="member",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AlterField(
            model_name="member",
            name="join_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="member",
            name="billing_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        # ---------------------------------------------------------------
        # Space: add width, depth, rate_per_sqft, is_rentable
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name="space",
            name="width",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="space",
            name="depth",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="space",
            name="rate_per_sqft",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name="space",
            name="is_rentable",
            field=models.BooleanField(default=True),
        ),
        # ---------------------------------------------------------------
        # Guild + GuildVote: new models
        # ---------------------------------------------------------------
        migrations.CreateModel(
            name="Guild",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "guild_lead",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="led_guilds",
                        to="membership.member",
                    ),
                ),
            ],
            options={
                "verbose_name": "Guild",
                "verbose_name_plural": "Guilds",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="GuildVote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "priority",
                    models.PositiveSmallIntegerField(choices=[(1, "First"), (2, "Second"), (3, "Third")]),
                ),
                (
                    "guild",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="votes",
                        to="membership.guild",
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guild_votes",
                        to="membership.member",
                    ),
                ),
            ],
            options={
                "verbose_name": "Guild Vote",
                "verbose_name_plural": "Guild Votes",
                "ordering": ["member", "priority"],
                "unique_together": {("member", "priority"), ("member", "guild")},
            },
        ),
        # ---------------------------------------------------------------
        # Lease: convert member FK → GenericForeignKey (content_type + object_id)
        # ---------------------------------------------------------------
        migrations.RemoveField(
            model_name="lease",
            name="member",
        ),
        migrations.AddField(
            model_name="lease",
            name="content_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="contenttypes.contenttype",
            ),
            # No data exists, so preserve_default is irrelevant but we set it
            # to False to document that this is non-nullable from the start.
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="lease",
            name="object_id",
            field=models.PositiveIntegerField(),
            preserve_default=False,
        ),
        # ---------------------------------------------------------------
        # Lease: add discount_reason, is_split, prepaid_through
        # ---------------------------------------------------------------
        migrations.AddField(
            model_name="lease",
            name="discount_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="lease",
            name="is_split",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="lease",
            name="prepaid_through",
            field=models.DateField(blank=True, null=True),
        ),
    ]
