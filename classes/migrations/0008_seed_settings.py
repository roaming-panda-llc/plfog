"""Seed ClassSettings singleton with default waiver text.

Waiver text is inlined here (not imported from classes.models) because
migrations are frozen snapshots — importing live constants makes this
migration unreplayable if those constants are later renamed or removed.
"""

from django.db import migrations

LIABILITY_TEXT = """ASSUMPTION OF RISK AND WAIVER OF LIABILITY

I understand that participation in classes, workshops, and activities at Past Lives Makerspace ("PLM") involves inherent risks, including but not limited to: exposure to tools, machinery, and equipment; risk of cuts, burns, eye injury, hearing damage, and other physical harm; and exposure to dust, fumes, chemicals, and other materials.

I voluntarily assume all risks associated with my participation. I hereby release, waive, and discharge PLM, its owners, officers, employees, instructors, volunteers, and agents from any and all liability, claims, demands, or causes of action arising out of or related to my participation, including negligence.

I agree to follow all safety rules, instructions, and guidelines provided by PLM and its instructors. I understand that failure to do so may result in removal from the class without refund.

I confirm that I am at least 18 years of age (or have a parent/guardian signing on my behalf), that I am physically able to participate, and that I carry my own health insurance or accept financial responsibility for any medical treatment I may require.

Past Lives Makerspace LLC, 2808 SE 9th Ave, Portland, OR 97202"""


MODEL_RELEASE_TEXT = """MODEL RELEASE AND CONSENT TO USE OF IMAGE

I grant Past Lives Makerspace ("PLM"), its employees, and agents the right to photograph, video record, and otherwise capture my likeness during classes and events, and to use such images for promotional, educational, and marketing purposes including but not limited to: website, social media, printed materials, and press.

I waive any right to inspect or approve the finished images or the use to which they may be applied. I release PLM from any claims arising from the use of my likeness.

I understand that I may revoke this consent at any time by notifying PLM in writing at info@pastlives.space."""


def forward(apps, schema_editor):
    ClassSettings = apps.get_model("classes", "ClassSettings")
    ClassSettings.objects.update_or_create(
        pk=1,
        defaults={
            "liability_waiver_text": LIABILITY_TEXT,
            "model_release_waiver_text": MODEL_RELEASE_TEXT,
        },
    )


def reverse(apps, schema_editor):
    ClassSettings = apps.get_model("classes", "ClassSettings")
    ClassSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [("classes", "0007_registration_registrationreminder_waiver_and_more")]
    operations = [migrations.RunPython(forward, reverse)]
