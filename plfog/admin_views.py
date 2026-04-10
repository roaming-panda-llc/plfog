"""Custom admin views."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Invite
from membership.forms import InviteMemberForm
from membership.models import FundingSnapshot, Member, VotePreference
from membership.vote_calculator import calculate_results


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


# ---------------------------------------------------------------------------
# Snapshot Analyzer — unified draft + stored views
# ---------------------------------------------------------------------------
#
# This replaces the old single-shot "Take Snapshot" modal. The analyzer serves
# two modes via the same template:
#
#   /admin/snapshots/draft/           → live VotePreference data, uncommitted
#   /admin/snapshots/<pk>/            → stored FundingSnapshot, read-only analysis
#
# Both modes run filters purely in Python over a list of vote dicts — no DB
# queries beyond the initial fetch. The commit endpoint always captures the
# full unfiltered state of live votes; filters are purely a visualization aid.
#
# See docs/superpowers/plans/2026-04-09-funding-snapshot-overhaul.md for
# background and the rationale for this shape.
# ---------------------------------------------------------------------------

MEMBER_TYPE_CHOICES = Member.MemberType.choices
FOG_ROLE_CHOICES = Member.FogRole.choices
DEFAULT_MINIMUM_POOL = Decimal("1000")


def _serialize_live_votes() -> list[dict[str, Any]]:
    """Snapshot live VotePreference rows into the same shape as FundingSnapshot.raw_votes."""
    preferences = VotePreference.objects.select_related(
        "member",
        "guild_1st",
        "guild_2nd",
        "guild_3rd",
    ).all()
    return [
        {
            "member_id": pref.member_id,
            "member_name": pref.member.display_name,
            "member_type": pref.member.member_type,
            "fog_role": pref.member.fog_role,
            "is_paying": pref.member.is_paying,
            "guild_1st_id": pref.guild_1st_id,
            "guild_1st_name": pref.guild_1st.name,
            "guild_2nd_id": pref.guild_2nd_id,
            "guild_2nd_name": pref.guild_2nd.name,
            "guild_3rd_id": pref.guild_3rd_id,
            "guild_3rd_name": pref.guild_3rd.name,
        }
        for pref in preferences
    ]


def _parse_is_paying(value: str) -> bool | None:
    """Normalize the is_paying filter query param. Empty string → None (both)."""
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def _apply_filters(
    raw_votes: list[dict[str, Any]],
    *,
    member_types: list[str],
    fog_roles: list[str],
    is_paying: bool | None,
) -> list[dict[str, Any]]:
    """Apply analyzer filters to a list of raw votes (in-memory, no DB work)."""
    filtered = raw_votes
    if member_types:
        filtered = [v for v in filtered if v["member_type"] in member_types]
    if fog_roles:
        filtered = [v for v in filtered if v["fog_role"] in fog_roles]
    if is_paying is not None:
        filtered = [v for v in filtered if v["is_paying"] is is_paying]
    return filtered


def _parse_minimum_pool(raw: str | None, default: Decimal = DEFAULT_MINIMUM_POOL) -> Decimal:
    """Parse a minimum_pool string. Falls back to default on empty or invalid input."""
    if not raw:
        return default
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return default
    if value < 0:
        return default
    return value


def _render_analyzer(
    request: HttpRequest,
    *,
    raw_votes: list[dict[str, Any]],
    snapshot: FundingSnapshot | None,
) -> HttpResponse:
    """Shared renderer for draft mode (snapshot=None) and stored mode."""
    # Legacy pre-refactor snapshots have empty raw_votes; bypass filter/recalc.
    is_legacy = snapshot is not None and not raw_votes

    member_types = request.GET.getlist("member_type")
    fog_roles = request.GET.getlist("fog_role")
    is_paying = _parse_is_paying(request.GET.get("is_paying", ""))

    if snapshot is not None:
        minimum_pool = snapshot.minimum_pool
        title_default = snapshot.cycle_label
    else:
        minimum_pool = _parse_minimum_pool(request.GET.get("minimum_pool"))
        title_default = request.GET.get("title", "").strip() or timezone.now().strftime("%B %Y")

    if is_legacy:
        assert snapshot is not None
        calc: dict[str, Any] = snapshot.results or {}
        filtered_votes: list[dict[str, Any]] = []
    else:
        filtered_votes = _apply_filters(
            raw_votes,
            member_types=member_types,
            fog_roles=fog_roles,
            is_paying=is_paying,
        )
        paying_count = sum(1 for v in filtered_votes if v["is_paying"])
        votes_for_calc = [
            {
                "guild_1st": v["guild_1st_name"],
                "guild_2nd": v["guild_2nd_name"],
                "guild_3rd": v["guild_3rd_name"],
            }
            for v in filtered_votes
        ]
        calc = calculate_results(
            votes_for_calc,
            paying_voter_count=paying_count,
            minimum_pool=minimum_pool,
        )

    non_paying_count = (
        sum(1 for v in filtered_votes if not v["is_paying"]) if not is_legacy else 0
    )
    paying_count = sum(1 for v in filtered_votes if v["is_paying"]) if not is_legacy else 0

    context = {
        **admin.site.each_context(request),
        "snapshot": snapshot,
        "mode": "stored" if snapshot is not None else "draft",
        "is_legacy": is_legacy,
        "title_default": title_default,
        "minimum_pool": minimum_pool,
        "calc": calc,
        "filtered_votes": sorted(filtered_votes, key=lambda v: v["member_name"].lower()),
        "filter_state": {
            "member_type": member_types,
            "fog_role": fog_roles,
            "is_paying": request.GET.get("is_paying", ""),
        },
        "member_type_choices": MEMBER_TYPE_CHOICES,
        "fog_role_choices": FOG_ROLE_CHOICES,
        "paying_count": paying_count,
        "non_paying_count": non_paying_count,
        "total_count": len(filtered_votes),
    }
    return render(request, "admin/snapshot_analyzer.html", context)


@staff_member_required
def snapshot_draft(request: HttpRequest) -> HttpResponse:
    """Analyzer running on live VotePreference data — no snapshot stored yet."""
    raw_votes = _serialize_live_votes()
    return _render_analyzer(request, raw_votes=raw_votes, snapshot=None)


@staff_member_required
def snapshot_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Analyzer running on a stored FundingSnapshot's raw_votes."""
    snapshot = get_object_or_404(FundingSnapshot, pk=pk)
    return _render_analyzer(request, raw_votes=list(snapshot.raw_votes), snapshot=snapshot)


@require_POST
@staff_member_required
def snapshot_take(request: HttpRequest) -> HttpResponse:
    """Commit a snapshot from current live VotePreference data.

    Filters on the draft page are purely for analysis — the commit always
    captures the full unfiltered state. Only title and minimum_pool carry over.
    """
    title = request.POST.get("title", "").strip()
    minimum_pool = _parse_minimum_pool(request.POST.get("minimum_pool"))

    snapshot = FundingSnapshot.take(title=title, minimum_pool=minimum_pool)
    if snapshot is None:
        messages.warning(request, "No votes yet — nothing to snapshot.")
        return redirect("admin_snapshot_draft")

    messages.success(
        request,
        f"Snapshot '{snapshot.cycle_label}' created — ${snapshot.funding_pool} pool.",
    )
    return redirect("admin_snapshot_detail", pk=snapshot.pk)


@require_POST
@staff_member_required
def snapshot_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a stored FundingSnapshot and return to the admin changelist."""
    snapshot = get_object_or_404(FundingSnapshot, pk=pk)
    cycle_label = snapshot.cycle_label
    snapshot.delete()
    messages.success(request, f"Deleted snapshot '{cycle_label}'.")
    return redirect("admin:membership_fundingsnapshot_changelist")
