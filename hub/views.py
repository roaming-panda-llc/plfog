"""Views for the member hub."""

from __future__ import annotations

from typing import Any, TypedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from billing.exceptions import NoPaymentMethodError, TabLimitExceededError, TabLockedError
from billing.models import Product, Tab, TabCharge
from hub.forms import (
    AddTabEntryForm,
    BetaFeedbackForm,
    EmailPreferencesForm,
    GuildPageForm,
    GuildProductForm,
    ProfileSettingsForm,
    VotePreferenceForm,
)
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
    """Member directory page — lists all active members."""
    ctx = _get_hub_context(request)
    current_member = _get_member(request)
    members = (
        Member.objects.filter(status=Member.Status.ACTIVE, show_in_directory=True)
        .select_related("membership_plan")
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
    """Guild detail page — shows about text, products, and guild lead info."""
    guild = get_object_or_404(Guild, pk=pk)
    ctx = _get_hub_context(request)
    products = guild.products.filter(is_active=True).order_by("name")
    member = _get_member(request)
    is_lead = (
        member is not None
        and guild.guild_lead is not None
        and guild.guild_lead == member
    )
    return render(
        request,
        "hub/guild_detail.html",
        {**ctx, "guild": guild, "products": products, "is_lead": is_lead},
    )


@login_required
def guild_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Guild edit page — guild lead edits about text and manages products."""
    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)

    if member is None or guild.guild_lead is None or guild.guild_lead != member:
        return HttpResponseForbidden()

    ctx = _get_hub_context(request)
    products = guild.products.filter(is_active=True).order_by("name")
    page_form = GuildPageForm(instance=guild)
    product_form = GuildProductForm()

    if request.method == "POST":
        if "add_product" in request.POST:
            product_form = GuildProductForm(request.POST)
            if product_form.is_valid():
                p = product_form.save(commit=False)
                p.guild = guild
                p.created_by = request.user  # type: ignore[assignment]
                p.save()
                return redirect("hub_guild_edit", pk=guild.pk)
        else:
            page_form = GuildPageForm(request.POST, instance=guild)
            if page_form.is_valid():
                page_form.save()
                return redirect("hub_guild_edit", pk=guild.pk)

    return render(
        request,
        "hub/guild_edit.html",
        {**ctx, "guild": guild, "products": products, "page_form": page_form, "product_form": product_form},
    )


@login_required
def guild_product_edit(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """Edit a single product belonging to this guild."""
    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)

    if member is None or guild.guild_lead is None or guild.guild_lead != member:
        return HttpResponseForbidden()

    product = get_object_or_404(Product, pk=product_pk, guild=guild)
    ctx = _get_hub_context(request)

    if request.method == "POST":
        form = GuildProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect("hub_guild_edit", pk=guild.pk)
    else:
        form = GuildProductForm(instance=product)

    return render(
        request,
        "hub/guild_product_edit.html",
        {**ctx, "guild": guild, "product": product, "form": form},
    )


@login_required
def guild_product_remove(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """Soft-delete a product (sets is_active=False)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)

    if member is None or guild.guild_lead is None or guild.guild_lead != member:
        return HttpResponseForbidden()

    product = get_object_or_404(Product, pk=product_pk, guild=guild)
    product.is_active = False
    product.save(update_fields=["is_active"])
    return redirect("hub_guild_edit", pk=guild.pk)


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
        form = AddTabEntryForm(request.POST)
        if form.is_valid():
            try:
                tab.add_entry(
                    description=form.cleaned_data["description"],
                    amount=form.cleaned_data["amount"],
                    added_by=request.user,  # type: ignore[arg-type]  # @login_required guarantees User
                    is_self_service=True,
                    product=form.cleaned_data.get("product"),
                )
                messages.success(request, "Item added to your tab.")
                return redirect("hub_tab_detail")
            except TabLockedError:
                messages.error(request, "Your tab is locked. Please contact an admin.")
            except NoPaymentMethodError:
                messages.error(request, "Please add a payment method before adding items to your tab.")
            except TabLimitExceededError:
                messages.error(request, "This item would exceed your tab limit.")
    else:
        form = AddTabEntryForm()

    return render(
        request,
        "hub/tab_detail.html",
        {**ctx, "tab": tab, "entries": entries, "form": form, "products": products},
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
