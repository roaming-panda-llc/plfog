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
    """Create a funding snapshot from current vote preferences with optional customisation."""
    title = request.POST.get("title", "").strip()
    voter_filter = request.POST.get("voter_filter", "")
    pool_raw = request.POST.get("pool_override", "").strip()

    pool_override: int | None = None
    if pool_raw:
        try:
            pool_override = int(pool_raw)
            if pool_override < 0:
                messages.error(request, "Funding pool cannot be negative.")
                return redirect("admin:index")
        except ValueError:
            messages.error(request, "Funding pool must be a whole dollar amount.")
            return redirect("admin:index")

    snapshot = FundingSnapshot.take(
        title=title,
        voter_filter=voter_filter,
        pool_override=pool_override,
    )

    if snapshot is None:
        messages.warning(request, "No votes matched the selected filters.")
        return redirect("admin:index")

    messages.success(request, f"Snapshot '{snapshot.cycle_label}' created — ${snapshot.funding_pool} pool.")
    return redirect("admin:index")
