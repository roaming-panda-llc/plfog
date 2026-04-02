"""Forms for the membership app."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from core.models import Invite

from .models import Member


class MemberAdminForm(forms.ModelForm):
    """Admin form for Member with optional User creation."""

    create_user = forms.BooleanField(
        required=False,
        label="Create login immediately",
        help_text="Creates a User account so this person can log in right away.",
    )

    class Meta:
        model = Member
        fields = "__all__"


class InviteMemberForm(forms.Form):
    """Form for inviting a new member by email."""

    email = forms.EmailField(help_text="The person will receive a signup link at this address.")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        if Member.objects.filter(email__iexact=email).exclude(status=Member.Status.INVITED).exists():
            raise ValidationError("A member with this email already exists.")
        if Invite.objects.filter(email__iexact=email, accepted_at__isnull=True).exists():
            raise ValidationError("A pending invite for this email already exists.")
        return email
