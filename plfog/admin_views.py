"""Custom admin views."""

from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.models import Invite
from membership.forms import InviteMemberForm
from membership.models import FundingSnapshot


@staff_member_required
def invite_member(request: HttpRequest) -> HttpResponse:
    """Admin view to invite a new member by email."""
    if request.method == "POST":
        form = InviteMemberForm(request.POST)
        if form.is_valid():
            try:
                Invite.create_and_send(
                    email=form.cleaned_data["email"],
                    invited_by=request.user,
                )
                messages.success(request, f"Invite sent to {form.cleaned_data['email']}.")
                return redirect("admin:membership_member_changelist")
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = InviteMemberForm()
    context = {**admin.site.each_context(request), "form": form}
    return render(request, "admin/membership/invite_member.html", context)


@require_POST
@staff_member_required
def take_snapshot(request: HttpRequest) -> HttpResponse:
    """Create a funding snapshot from current vote preferences."""
    snapshot = FundingSnapshot.take()

    if snapshot is None:
        messages.warning(request, "No votes to snapshot.")
        return redirect("admin:index")

    messages.success(request, f"Snapshot for {snapshot.cycle_label} created successfully.")
    return redirect("admin:index")
