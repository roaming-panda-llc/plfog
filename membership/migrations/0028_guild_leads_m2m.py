from typing import Any

from django.db import migrations, models


def _copy_fk_to_m2m(apps: Any, schema_editor: Any) -> None:
    """Copy Guild.guild_lead FK assignments into the new guild_leaderships M2M table."""
    Guild = apps.get_model("membership", "Guild")
    for guild in Guild.objects.exclude(guild_lead__isnull=True):
        guild.guild_leaderships.add(guild.guild_lead_id)


def _restore_fk_from_m2m(apps: Any, schema_editor: Any) -> None:
    """Restore Guild.guild_lead from the first entry in guild_leaderships (for reversal).

    NOTE: If a guild had multiple leads, only the first (arbitrary ordering) is preserved.
    This data loss is inherent to the M2M→FK direction and is expected on reversal.
    """
    Guild = apps.get_model("membership", "Guild")
    for guild in Guild.objects.all():
        first_lead = guild.guild_leaderships.first()
        if first_lead is not None:
            guild.guild_lead_id = first_lead.pk
            guild.save(update_fields=["guild_lead"])


class Migration(migrations.Migration):
    dependencies = [
        ("membership", "0027_calendarevent_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="guild_leaderships",
            field=models.ManyToManyField(
                blank=True,
                help_text="Guilds this member leads.",
                related_name="guild_leads",
                to="membership.guild",
            ),
        ),
        migrations.RunPython(
            _copy_fk_to_m2m,
            _restore_fk_from_m2m,
        ),
        migrations.RemoveField(
            model_name="guild",
            name="guild_lead",
        ),
    ]
