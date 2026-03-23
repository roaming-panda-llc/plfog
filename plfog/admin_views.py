"""Custom admin views."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from membership.models import FundingSnapshot


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
