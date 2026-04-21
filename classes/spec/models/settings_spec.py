"""BDD specs for ClassSettings singleton."""

from __future__ import annotations

from classes.models import DEFAULT_LIABILITY_TEXT, DEFAULT_MODEL_RELEASE_TEXT, ClassSettings


def describe_ClassSettings():
    def describe_load():
        def it_creates_singleton_on_first_call(db):
            settings = ClassSettings.load()
            assert settings.pk == 1

        def it_returns_same_instance_on_repeat_call(db):
            a = ClassSettings.load()
            b = ClassSettings.load()
            assert a.pk == b.pk == 1

        def it_seeds_default_waiver_text(db):
            settings = ClassSettings.load()
            assert settings.liability_waiver_text == DEFAULT_LIABILITY_TEXT
            assert settings.model_release_waiver_text == DEFAULT_MODEL_RELEASE_TEXT

        def it_has_sensible_defaults(db):
            settings = ClassSettings.load()
            assert settings.enabled_publicly is False
            assert settings.default_member_discount_pct == 10
            assert settings.reminder_hours_before == 24
            assert settings.instructor_approval_required is True

    def describe_save():
        def it_forces_pk_to_one(db):
            ClassSettings.objects.create(pk=99, liability_waiver_text="x", model_release_waiver_text="y")
            assert ClassSettings.objects.count() == 1
            assert ClassSettings.objects.first().pk == 1

        def it_creates_row_when_none_exists(db):
            ClassSettings.objects.all().delete()
            ClassSettings.objects.create(liability_waiver_text="fresh", model_release_waiver_text="fresh")
            assert ClassSettings.objects.count() == 1
            assert ClassSettings.objects.first().pk == 1

    def it_stringifies_as_class_settings(db):
        assert str(ClassSettings.load()) == "Class Settings"
