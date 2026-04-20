"""Seed ClassSettings singleton with default waiver text."""

from django.db import migrations


def forward(apps, schema_editor):
    from classes.models import DEFAULT_LIABILITY_TEXT, DEFAULT_MODEL_RELEASE_TEXT

    ClassSettings = apps.get_model("classes", "ClassSettings")
    ClassSettings.objects.update_or_create(
        pk=1,
        defaults={
            "liability_waiver_text": DEFAULT_LIABILITY_TEXT,
            "model_release_waiver_text": DEFAULT_MODEL_RELEASE_TEXT,
        },
    )


def reverse(apps, schema_editor):
    ClassSettings = apps.get_model("classes", "ClassSettings")
    ClassSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [("classes", "0007_registration_registrationreminder_waiver_and_more")]
    operations = [migrations.RunPython(forward, reverse)]
