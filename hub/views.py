"""Views for the member hub."""

from __future__ import annotations

from typing import Any, TypedDict

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from billing.exceptions import TabLimitExceededError, TabLockedError
from billing.forms import CONTEXT_MEMBER_TAB_PAGE, TabItemForm
from billing.models import Product, Tab, TabCharge
from hub.forms import BetaFeedbackForm, EmailPreferencesForm, ProfileSettingsForm, VotePreferenceForm
from membership.cycle import get_cycle_context
from membership.models import FundingSnapshot, Guild, Member, VotePreference


class VoteStanding(TypedDict, total=False):
    guild_name: str
    total_points: int
    bar_pct: float


def _get_hub_context(request: HttpRequest) -> dict[str, Any]:
    """Build common sidebar context for all hub pages."""
    guilds = Guild.objects.order_by("name")
    initials = ""
    if request.user.is_authenticated:
        member: Member | None = getattr(request.user, "member", None)
        if member is not None:
            initials = member.initials
    return {
        "guilds": guilds,
        "user_initials": initials,
    }


def _get_member(request: HttpRequest) -> Member | None:
    """Get the Member for the logged-in user, or None.

    Callers must be decorated with @login_required.
    """
    member: Member | None = getattr(request.user, "member", None)
    return member


@login_required
def guild_voting(request: HttpRequest) -> HttpResponse:
    """Guild voting page — members submit or update their persistent guild preferences."""
    member = _get_member(request)
    ctx = _get_hub_context(request)
    cycle_ctx = get_cycle_context()

    preference: VotePreference | None = None
    if member is not None:
        preference = getattr(member, "vote_preference", None)

    latest_snapshot = FundingSnapshot.objects.order_by("-snapshot_at").first()

    # Live vote standings: tally points from all current VotePreference records
    vote_standings = _compute_live_standings()

    if member is None:
        messages.info(request, "Your account is not linked to a membership.")
        return render(
            request,
            "hub/guild_voting.html",
            {
                **ctx,
                **cycle_ctx,
                "member": None,
                "form": None,
                "preference": None,
                "latest_snapshot": latest_snapshot,
                "vote_standings": vote_standings,
            },
        )

    if request.method == "POST":
        form = VotePreferenceForm(request.POST)
        if form.is_valid():
            VotePreference.objects.update_or_create(
                member=member,
                defaults={
                    "guild_1st": form.cleaned_data["guild_1st"],
                    "guild_2nd": form.cleaned_data["guild_2nd"],
                    "guild_3rd": form.cleaned_data["guild_3rd"],
                },
            )
            action = "updated" if preference else "submitted"
            messages.success(request, f"Your vote has been {action}.")
            return redirect("hub_guild_voting")
    else:
        initial: dict[str, Any] = {}
        if preference is not None:
            initial = {
                "guild_1st": preference.guild_1st,
                "guild_2nd": preference.guild_2nd,
                "guild_3rd": preference.guild_3rd,
            }
        form = VotePreferenceForm(initial=initial)

    return render(
        request,
        "hub/guild_voting.html",
        {
            **ctx,
            **cycle_ctx,
            "member": member,
            "form": form,
            "preference": preference,
            "latest_snapshot": latest_snapshot,
            "vote_standings": vote_standings,
        },
    )


def _compute_live_standings() -> list[VoteStanding]:
    """Tally live vote points from all current VotePreference records.

    Returns a list of dicts sorted by total points descending:
        [{"guild_name": str, "total_points": int, "bar_pct": float}, ...]
    """
    guilds = Guild.objects.filter(is_active=True).annotate(
        first=Count("first_choice_votes"),
        second=Count("second_choice_votes"),
        third=Count("third_choice_votes"),
    )

    results: list[VoteStanding] = []
    for g in guilds:
        points = g.first * 5 + g.second * 3 + g.third * 2
        if points > 0:
            results.append(VoteStanding(guild_name=g.name, total_points=points))

    if not results:
        return []

    results.sort(key=lambda x: x["total_points"], reverse=True)
    max_points = results[0]["total_points"]
    for r in results:
        r["bar_pct"] = round(r["total_points"] / max_points * 100, 1)
    return results


@login_required
def member_directory(request: HttpRequest) -> HttpResponse:
    """Member directory page — lists all active members.

    Prefetches each member's primary allauth ``EmailAddress`` so
    ``Member.primary_email`` stays O(1) per member instead of firing a query
    on every template access. See the three-email-store note on
    ``Member.primary_email`` and docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
    """
    ctx = _get_hub_context(request)
    current_member = _get_member(request)
    members = (
        Member.objects.filter(status=Member.Status.ACTIVE, show_in_directory=True)
        .select_related("membership_plan", "user")
        .prefetch_related(
            Prefetch(
                "user__emailaddress_set",
                queryset=EmailAddress.objects.filter(primary=True),
                to_attr="_primary_emailaddresses",
            )
        )
        .order_by("full_legal_name")
    )
    return render(
        request,
        "hub/member_directory.html",
        {**ctx, "members": members, "current_member": current_member},
    )


@login_required
def snapshot_history(request: HttpRequest) -> HttpResponse:
    """Funding snapshot history page — lists all past snapshots."""
    ctx = _get_hub_context(request)
    snapshots = FundingSnapshot.objects.order_by("-snapshot_at")
    return render(request, "hub/snapshot_history.html", {**ctx, "snapshots": snapshots})


@login_required
def snapshot_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Funding snapshot detail page — shows full results for a single snapshot."""
    ctx = _get_hub_context(request)
    snapshot = get_object_or_404(FundingSnapshot, pk=pk)
    return render(request, "hub/snapshot_detail.html", {**ctx, "snapshot": snapshot})


@login_required
def guild_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Guild detail page — shows about text and active products."""
    guild = get_object_or_404(Guild, pk=pk)
    ctx = _get_hub_context(request)
    products = guild.products.filter(is_active=True).order_by("name")
    return render(request, "hub/guild_detail.html", {**ctx, "guild": guild, "products": products})


@login_required
def profile_settings(request: HttpRequest) -> HttpResponse:
    """Profile settings page."""
    member = _get_member(request)
    ctx = _get_hub_context(request)

    if member is None:
        messages.info(request, "Your account is not linked to a membership.")
        return render(request, "hub/profile_settings.html", {**ctx, "member": None, "form": None})

    if request.method == "POST":
        form = ProfileSettingsForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("hub_profile_settings")
    else:
        form = ProfileSettingsForm(instance=member)

    return render(request, "hub/profile_settings.html", {**ctx, "member": member, "form": form})


@login_required
def email_preferences(request: HttpRequest) -> HttpResponse:
    """Email preferences page."""
    ctx = _get_hub_context(request)

    if request.method == "POST":
        form = EmailPreferencesForm(request.POST)
        if form.is_valid():
            messages.success(request, "Email preferences updated.")
            return redirect("hub_email_preferences")
    else:
        form = EmailPreferencesForm(initial={"voting_results": True})

    return render(request, "hub/email_preferences.html", {**ctx, "form": form})


@login_required
def beta_feedback(request: HttpRequest) -> HttpResponse:
    """Beta feedback page — users can report bugs, request features, or leave general feedback."""
    ctx = _get_hub_context(request)

    user: User = request.user  # type: ignore[assignment]  # @login_required guarantees User

    if request.method == "POST":
        form = BetaFeedbackForm(request.POST)
        if form.is_valid():
            form.send(user=user)
            messages.success(request, "Thanks for your feedback! We'll review it soon.")
            return redirect("hub_beta_feedback")
    else:
        form = BetaFeedbackForm()

    return render(request, "hub/beta_feedback.html", {**ctx, "form": form})


@login_required
def tab_detail(request: HttpRequest) -> HttpResponse:
    """My Tab page — shows current balance, pending entries, and self-service add form."""
    member = _get_member(request)
    ctx = _get_hub_context(request)

    if member is None:
        messages.info(request, "Your account is not linked to a membership.")
        return render(request, "hub/tab_detail.html", {**ctx, "tab": None, "entries": [], "form": None})

    tab, _created = Tab.objects.get_or_create(member=member)
    entries = tab.entries.pending().select_related("product__guild").order_by("-created_at")
    products = Product.objects.filter(is_active=True).select_related("guild").order_by("guild__name", "name")

    if request.method == "POST":
        form = TabItemForm(request.POST, context=CONTEXT_MEMBER_TAB_PAGE, user=request.user)
        if form.is_valid():
            try:
                form.apply_to_tab(
                    tab,
                    added_by=request.user,  # type: ignore[arg-type]  # @login_required guarantees User
                    is_self_service=True,
                )
                messages.success(request, "Item added to your tab.")
                return redirect("hub_tab_detail")
            except TabLockedError:
                messages.error(request, "Your tab is locked. Please contact an admin.")
            except TabLimitExceededError:
                messages.error(request, "This item would exceed your tab limit.")
    else:
        form = TabItemForm(context=CONTEXT_MEMBER_TAB_PAGE, user=request.user)

    return render(
        request,
        "hub/tab_detail.html",
        {
            **ctx,
            "tab": tab,
            "entries": entries,
            "form": form,
            "products": products,
        },
    )


@login_required
def tab_history(request: HttpRequest) -> HttpResponse:
    """Tab History page — shows past billing charges with expandable details."""
    member = _get_member(request)
    ctx = _get_hub_context(request)

    if member is None:
        messages.info(request, "Your account is not linked to a membership.")
        return render(request, "hub/tab_history.html", {**ctx, "charges": []})

    tab, _created = Tab.objects.get_or_create(member=member)
    charges = tab.charges.exclude(status=TabCharge.Status.PENDING).order_by("-created_at").prefetch_related("entries")

    return render(request, "hub/tab_history.html", {**ctx, "charges": charges})
