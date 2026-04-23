"""Copy MailChimp + Google Analytics values from ClassSettings to SiteConfiguration.

Runs BEFORE 0011 removes the columns from ClassSettings. Forward = copy values
to the core.SiteConfiguration singleton (non-empty values win). Reverse = best
effort: copy values back from SiteConfiguration to ClassSettings if both rows
exist. Neither side creates a row where none existed — this migration only
touches existing singletons.
"""

from __future__ import annotations

from django.db import migrations


def _copy_to_site_settings(apps, _schema_editor):
    ClassSettings = apps.get_model("classes", "ClassSettings")
    SiteConfiguration = apps.get_model("core", "SiteConfiguration")
    src = ClassSettings.objects.filter(pk=1).first()
    if src is None:
        return
    site = SiteConfiguration.objects.filter(pk=1).first()
    if site is None:
        return
    dirty = False
    for field in ("mailchimp_api_key", "mailchimp_list_id", "google_analytics_measurement_id"):
        value = getattr(src, field, "") or ""
        if value and not getattr(site, field, ""):
            setattr(site, field, value)
            dirty = True
    if dirty:
        site.save()


def _copy_back_to_class_settings(apps, _schema_editor):
    ClassSettings = apps.get_model("classes", "ClassSettings")
    SiteConfiguration = apps.get_model("core", "SiteConfiguration")
    site = SiteConfiguration.objects.filter(pk=1).first()
    dst = ClassSettings.objects.filter(pk=1).first()
    if site is None or dst is None:
        return
    for field in ("mailchimp_api_key", "mailchimp_list_id", "google_analytics_measurement_id"):
        if hasattr(dst, field):
            setattr(dst, field, getattr(site, field, "") or "")
    dst.save()


class Migration(migrations.Migration):
    dependencies = [
        ("classes", "0010_alter_category_hero_image_alter_classoffering_image_and_more"),
        ("core", "0010_siteconfiguration_google_analytics_measurement_id_and_more"),
    ]

    operations = [
        migrations.RunPython(_copy_to_site_settings, _copy_back_to_class_settings),
    ]
