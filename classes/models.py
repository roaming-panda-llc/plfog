"""Models for the Classes app."""

from __future__ import annotations

from django.db import models

DEFAULT_LIABILITY_TEXT = """ASSUMPTION OF RISK AND WAIVER OF LIABILITY

I understand that participation in classes, workshops, and activities at Past Lives Makerspace ("PLM") involves inherent risks, including but not limited to: exposure to tools, machinery, and equipment; risk of cuts, burns, eye injury, hearing damage, and other physical harm; and exposure to dust, fumes, chemicals, and other materials.

I voluntarily assume all risks associated with my participation. I hereby release, waive, and discharge PLM, its owners, officers, employees, instructors, volunteers, and agents from any and all liability, claims, demands, or causes of action arising out of or related to my participation, including negligence.

I agree to follow all safety rules, instructions, and guidelines provided by PLM and its instructors. I understand that failure to do so may result in removal from the class without refund.

I confirm that I am at least 18 years of age (or have a parent/guardian signing on my behalf), that I am physically able to participate, and that I carry my own health insurance or accept financial responsibility for any medical treatment I may require.

Past Lives Makerspace LLC, 2808 SE 9th Ave, Portland, OR 97202"""


DEFAULT_MODEL_RELEASE_TEXT = """MODEL RELEASE AND CONSENT TO USE OF IMAGE

I grant Past Lives Makerspace ("PLM"), its employees, and agents the right to photograph, video record, and otherwise capture my likeness during classes and events, and to use such images for promotional, educational, and marketing purposes including but not limited to: website, social media, printed materials, and press.

I waive any right to inspect or approve the finished images or the use to which they may be applied. I release PLM from any claims arising from the use of my likeness.

I understand that I may revoke this consent at any time by notifying PLM in writing at info@pastlives.space."""


class ClassSettings(models.Model):
    enabled_publicly = models.BooleanField(
        default=False,
        help_text="When False, /classes/ public routes return 404. Admin + instructor dashboards stay available.",
    )
    liability_waiver_text = models.TextField(help_text="Full liability waiver text shown to all registrants.")
    model_release_waiver_text = models.TextField(
        help_text="Full model-release waiver text shown when a class requires it."
    )
    default_member_discount_pct = models.PositiveIntegerField(
        default=10, help_text="Percent discount auto-applied to registrations from verified Members (0 = no discount)."
    )
    reminder_hours_before = models.PositiveIntegerField(
        default=24, help_text="Hours before a class session to send the reminder email."
    )
    instructor_approval_required = models.BooleanField(
        default=True, help_text="When on, new classes go to admin for review before being published."
    )
    mailchimp_api_key = models.CharField(max_length=255, blank=True, help_text="MailChimp API key for auto-subscribe.")
    mailchimp_list_id = models.CharField(
        max_length=255, blank=True, help_text="MailChimp list ID for class registrants."
    )
    google_analytics_measurement_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="GA4 measurement ID (e.g. G-XXXXXXX). Leave blank to disable GA tag.",
    )
    confirmation_email_footer = models.TextField(
        blank=True, help_text="Custom footer appended to confirmation emails."
    )

    class Meta:
        verbose_name = "Class Settings"
        verbose_name_plural = "Class Settings"

    def __str__(self) -> str:
        return "Class Settings"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "ClassSettings":
        obj, _created = cls.objects.get_or_create(
            pk=1,
            defaults={
                "liability_waiver_text": DEFAULT_LIABILITY_TEXT,
                "model_release_waiver_text": DEFAULT_MODEL_RELEASE_TEXT,
            },
        )
        return obj
