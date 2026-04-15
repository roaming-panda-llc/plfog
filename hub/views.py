"""Views for the member hub."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, TypedDict

from django.utils import timezone as dj_timezone

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from billing.exceptions import NoPaymentMethodError, TabLimitExceededError, TabLockedError
from billing.models import BillingSettings, Tab, TabCharge
from hub.calendar_service import refresh_stale_sources
from hub.forms import BetaFeedbackForm, EmailPreferencesForm, GuildEditForm, ProfileSettingsForm, VotePreferenceForm
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
    since = latest_snapshot.snapshot_at if latest_snapshot else None

    # Live vote standings: tally points from all current VotePreference records
    vote_standings = _compute_live_standings()
    new_vote_standings = _compute_new_votes_since(since)

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
                "new_vote_standings": new_vote_standings,
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
            "new_vote_standings": new_vote_standings,
        },
    )


def _compute_live_standings() -> list[VoteStanding]:
    """Tally live vote points from current VotePreference records.

    Only counts votes from members with a linked User — members imported from
    Airtable who never signed up to the app are excluded. See
    ``VotePreferenceQuerySet.from_signed_up_members``.

    Returns a list of dicts sorted by total points descending:
        [{"guild_name": str, "total_points": int, "bar_pct": float}, ...]
    """
    signed_up_1st = Q(first_choice_votes__member__user__isnull=False)
    signed_up_2nd = Q(second_choice_votes__member__user__isnull=False)
    signed_up_3rd = Q(third_choice_votes__member__user__isnull=False)
    # distinct=True is essential: annotating three reverse-FK Counts on the same
    # queryset cross-joins first/second/third_choice_votes, so without distinct
    # each Count is multiplied by the other two. A guild with 1/2/3 first/second/
    # third-place votes would show 6/6/6 and score 60 points instead of 17.
    guilds = Guild.objects.filter(is_active=True).annotate(
        first=Count("first_choice_votes", filter=signed_up_1st, distinct=True),
        second=Count("second_choice_votes", filter=signed_up_2nd, distinct=True),
        third=Count("third_choice_votes", filter=signed_up_3rd, distinct=True),
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


def _compute_new_votes_since(since: datetime | None) -> list[VoteStanding]:
    """Tally points from VotePreferences updated after ``since``.

    Represents the "new votes this month" view — votes cast or changed since
    the last snapshot was taken. If ``since`` is None (no prior snapshot),
    every signed-up vote is considered new.
    """
    first_q = Q(first_choice_votes__member__user__isnull=False)
    second_q = Q(second_choice_votes__member__user__isnull=False)
    third_q = Q(third_choice_votes__member__user__isnull=False)
    if since is not None:
        first_q &= Q(first_choice_votes__updated_at__gt=since)
        second_q &= Q(second_choice_votes__updated_at__gt=since)
        third_q &= Q(third_choice_votes__updated_at__gt=since)

    # See note on distinct=True in _compute_live_standings — same cross-join
    # multiplication applies here.
    guilds = Guild.objects.filter(is_active=True).annotate(
        first=Count("first_choice_votes", filter=first_q, distinct=True),
        second=Count("second_choice_votes", filter=second_q, distinct=True),
        third=Count("third_choice_votes", filter=third_q, distinct=True),
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


def _can_edit_guild(request: HttpRequest, guild: Guild) -> bool:
    """Return True when the request's user may edit this guild.

    Handles anonymous users and users with no linked Member gracefully.
    """
    if not request.user.is_authenticated:  # pragma: no cover — defensive; callers are @login_required
        return False
    member: Member | None = getattr(request.user, "member", None)
    if member is None:
        return False
    return member.can_edit_guild(guild)


@login_required
def guild_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Guild detail page — shows about text, active products, and cart interface."""
    from billing.forms import CONTEXT_MEMBER_GUILD_PAGE, TabItemForm, build_product_split_formset
    from billing.models import Product

    guild = get_object_or_404(
        Guild.objects.prefetch_related("products__splits__guild"),
        pk=pk,
    )
    ctx = _get_hub_context(request)
    products = guild.products.order_by("name").prefetch_related("splits__guild")
    member = _get_member(request)

    tab: Tab | None = None
    if member is not None:
        tab, _created = Tab.objects.get_or_create(member=member)

    eyop_form = TabItemForm(context=CONTEXT_MEMBER_GUILD_PAGE, user=request.user, guild=guild)

    can_edit_this_guild = _can_edit_guild(request, guild)
    guild_edit_form = GuildEditForm(instance=guild) if can_edit_this_guild else None
    product_form = None
    product_splits_formset = None
    all_guilds = None
    if can_edit_this_guild:
        from billing.forms import ProductForm

        product_form = ProductForm()
        product_splits_formset = build_product_split_formset(instance=Product())
        all_guilds = Guild.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "hub/guild_detail.html",
        {
            **ctx,
            "guild": guild,
            "products": products,
            "tab": tab,
            "eyop_form": eyop_form,
            "can_edit_this_guild": can_edit_this_guild,
            "guild_edit_form": guild_edit_form,
            "product_form": product_form,
            "product_splits_formset": product_splits_formset,
            "all_guilds": all_guilds,
        },
    )


def _require_can_edit_guild(request: HttpRequest, guild: Guild) -> HttpResponse | None:
    """Return a 403 response if the user cannot edit ``guild``, else None."""
    if not _can_edit_guild(request, guild):
        return HttpResponse("Forbidden", status=403)
    return None


@login_required
@require_POST
def guild_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """POST-only — update the guild's name and about text. Admin, officer, or that guild's lead only."""
    guild = get_object_or_404(Guild, pk=pk)
    forbidden = _require_can_edit_guild(request, guild)
    if forbidden is not None:
        return forbidden

    form = GuildEditForm(request.POST, instance=guild)
    if form.is_valid():
        form.save()
        messages.success(request, "Guild updated.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return redirect("hub_guild_detail", pk=guild.pk)


def _surface_product_errors(request: HttpRequest, form: Any, formset: Any) -> None:
    """Flash per-field form + formset errors onto ``request`` as messages."""
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    for non_form_error in formset.non_form_errors():
        messages.error(request, f"Splits: {non_form_error}")
    for idx, form_errors in enumerate(formset.errors):
        for field, errors in form_errors.items():
            for error in errors:
                messages.error(request, f"Split row {idx + 1} ({field}): {error}")
    if not (
        form.errors or formset.non_form_errors() or any(formset.errors)
    ):  # pragma: no cover — defensive; is_valid()=False implies at least one error source
        messages.error(request, "Could not add product — see errors below.")


@login_required
@require_POST
def guild_product_create(request: HttpRequest, pk: int) -> HttpResponse:
    """POST-only — create a Product for this guild with its revenue splits.

    Permission: admin / guild_officer / this guild's lead.
    """
    from billing.forms import ProductForm, build_product_split_formset
    from billing.models import Product

    guild = get_object_or_404(Guild, pk=pk)
    forbidden = _require_can_edit_guild(request, guild)
    if forbidden is not None:
        return forbidden

    form = ProductForm(data=request.POST)
    formset = build_product_split_formset(data=request.POST, instance=Product())

    if form.is_valid() and formset.is_valid():
        product = form.save(commit=False)
        product.guild = guild  # always bind to the page's guild
        product.save()
        formset.instance = product
        formset.save()
        messages.success(request, f"Added product '{product.name}'.")
    else:
        _surface_product_errors(request, form, formset)

    return redirect("hub_guild_detail", pk=guild.pk)


@login_required
@require_POST
def guild_product_update(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """POST-only — update a Product (and its revenue splits) for this guild.

    Permission: admin / guild_officer / this guild's lead.
    """
    from billing.forms import ProductForm, build_product_split_formset
    from billing.models import Product

    guild = get_object_or_404(Guild, pk=pk)
    forbidden = _require_can_edit_guild(request, guild)
    if forbidden is not None:
        return forbidden

    product = get_object_or_404(Product, pk=product_pk, guild=guild)
    form = ProductForm(data=request.POST, instance=product)
    # The Alpine modal posts fresh splits rows (no PKs) regardless of mode, so
    # we replace the existing splits wholesale rather than diffing them. Build
    # the formset against an unsaved Product instance so it treats every row
    # as new; the actual link to ``product`` happens on save() below.
    formset = build_product_split_formset(data=request.POST, instance=Product())

    if form.is_valid() and formset.is_valid():
        updated = form.save(commit=False)
        updated.guild = guild  # always bind to the page's guild
        updated.save()
        updated.splits.all().delete()
        formset.instance = updated
        formset.save()
        messages.success(request, f"Updated product '{updated.name}'.")
    else:
        _surface_product_errors(request, form, formset)

    return redirect("hub_guild_detail", pk=guild.pk)


@login_required
@require_POST
def guild_product_delete(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """POST-only — delete a product from this guild. Permission same as guild_edit."""
    from billing.models import Product

    guild = get_object_or_404(Guild, pk=pk)
    forbidden = _require_can_edit_guild(request, guild)
    if forbidden is not None:
        return forbidden

    product = get_object_or_404(Product, pk=product_pk, guild=guild)
    name = product.name
    product.delete()
    messages.success(request, f"Deleted product '{name}'.")
    return redirect("hub_guild_detail", pk=guild.pk)


@login_required
@require_POST
def guild_cart_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    """Batch-add cart items to the member's tab. Expects JSON body with items array."""
    from hub.toast import trigger_toast

    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)
    if member is None:  # pragma: no cover — defensive; signal auto-creates Member on User creation
        return JsonResponse({"error": "No linked membership."}, status=400)

    tab, _created = Tab.objects.get_or_create(member=member)
    if not tab.can_add_entry:
        return JsonResponse({"error": "Payment method required."}, status=400)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    items = body.get("items", [])
    if not items:
        return JsonResponse({"error": "Cart is empty."}, status=400)

    active_products = {p.pk: p for p in guild.products.all()}
    entries_created = 0

    for item in items:
        product_pk = item.get("product_pk")
        quantity = item.get("quantity", 1)
        product = active_products.get(product_pk)
        if product is None:
            return JsonResponse({"error": f"Product {product_pk} not found."}, status=400)

        for _ in range(int(quantity)):
            try:
                tab.add_entry(
                    description=product.name,
                    amount=product.price,
                    added_by=request.user,  # type: ignore[arg-type]
                    is_self_service=True,
                    product=product,
                )
                entries_created += 1
            except (TabLockedError, TabLimitExceededError) as e:
                response = JsonResponse({"error": str(e)}, status=400)
                trigger_toast(response, str(e), "error")
                return response

    success_response = HttpResponse(status=204)
    item_word = "item" if entries_created == 1 else "items"
    trigger_toast(success_response, f"{entries_created} {item_word} added to your tab!", "success")
    return success_response


@login_required
@require_http_methods(["GET", "POST"])
def guild_eyop_form(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the EYOP form partial (GET) or process submission (POST)."""
    from billing.forms import CONTEXT_MEMBER_GUILD_PAGE, TabItemForm
    from hub.toast import trigger_toast

    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)
    if member is None:  # pragma: no cover — defensive; signal auto-creates Member on User creation
        return HttpResponse("No linked membership.", status=400)

    tab, _created = Tab.objects.get_or_create(member=member)

    if request.method == "POST":
        form = TabItemForm(request.POST, context=CONTEXT_MEMBER_GUILD_PAGE, user=request.user, guild=guild)
        if form.is_valid():
            quantity = form.cleaned_data["quantity"]
            try:
                if not tab.can_add_entry:
                    raise NoPaymentMethodError("Payment method required.")
                for _ in range(quantity):
                    form.apply_to_tab(tab, added_by=request.user, is_self_service=True)  # type: ignore[arg-type]
                response = HttpResponse(status=204)
                word = "item" if quantity == 1 else "items"
                trigger_toast(response, f"{quantity} {word} added to your tab!", "success")
                return response
            except NoPaymentMethodError:
                response = HttpResponse(status=400)
                trigger_toast(response, "You need a payment method on file.", "error")
                return response
            except TabLockedError:
                response = HttpResponse(status=400)
                trigger_toast(response, "Your tab is locked.", "error")
                return response
            except TabLimitExceededError:
                response = HttpResponse(status=400)
                trigger_toast(response, "This would exceed your tab limit.", "error")
                return response

        return render(request, "hub/partials/eyop_form.html", {"eyop_form": form, "guild": guild})

    form = TabItemForm(context=CONTEXT_MEMBER_GUILD_PAGE, user=request.user, guild=guild)
    return render(request, "hub/partials/eyop_form.html", {"eyop_form": form, "guild": guild})


@login_required
def user_settings(request: HttpRequest) -> HttpResponse:
    """Tabbed user settings page — Profile + Emails (manage addresses + preferences).

    Two forms POST to this endpoint, disambiguated by the ``form_id`` hidden field:
    ``profile`` (member info) and ``email_prefs`` (notification toggles). Email
    address management (add, primary, verify, remove) POSTs to allauth's
    ``account_email`` URL, which is overridden in ``plfog.urls`` to redirect back
    here after each action.
    """
    from allauth.account.forms import AddEmailForm
    from allauth.account.models import EmailAddress

    ctx = _get_hub_context(request)
    member = _get_member(request)

    profile_form: ProfileSettingsForm | None
    if request.method == "POST" and request.POST.get("form_id") == "profile":
        if member is None:
            messages.error(request, "Your account is not linked to a membership.")
            return redirect("hub_user_settings")
        profile_form = ProfileSettingsForm(request.POST, instance=member)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect(f"{request.path}?tab=profile")
    elif member is not None:
        profile_form = ProfileSettingsForm(instance=member)
    else:
        profile_form = None

    prefs_form: EmailPreferencesForm
    if request.method == "POST" and request.POST.get("form_id") == "email_prefs":
        prefs_form = EmailPreferencesForm(request.POST)
        if prefs_form.is_valid():
            messages.success(request, "Email preferences updated.")
            return redirect(f"{request.path}?tab=emails")
    else:
        prefs_form = EmailPreferencesForm(initial={"voting_results": True})

    add_email_form = AddEmailForm(user=request.user)
    email_addresses = list(EmailAddress.objects.filter(user=request.user).order_by("-primary", "email"))
    primary_email = next((ea for ea in email_addresses if ea.primary), None)
    primary_verified_json = "true" if primary_email is None or primary_email.verified else "false"

    # Whitelist the tab param — it flows into an Alpine x-data JS expression, so
    # HTML escaping alone isn't enough to stop a payload like ?tab='+alert(1)+'.
    tab_param = request.GET.get("tab", "profile")
    active_tab = tab_param if tab_param in {"profile", "emails"} else "profile"

    if member is None and request.method == "GET" and not request.GET.get("tab"):
        messages.info(request, "Your account is not linked to a membership.")

    return render(
        request,
        "hub/user_settings.html",
        {
            **ctx,
            "member": member,
            "profile_form": profile_form,
            "prefs_form": prefs_form,
            "add_email_form": add_email_form,
            "email_addresses": email_addresses,
            "primary_verified_json": primary_verified_json,
            "active_tab": active_tab,
        },
    )


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
@require_http_methods(["GET"])
def tab_detail(request: HttpRequest) -> HttpResponse:
    """My Tab page — shows current balance, pending entries, and saved payment method."""
    member = _get_member(request)
    ctx = _get_hub_context(request)

    if member is None:
        messages.info(request, "Your account is not linked to a membership.")
        return render(request, "hub/tab_detail.html", {**ctx, "tab": None, "entries": []})

    tab, _created = Tab.objects.get_or_create(member=member)
    entries = tab.entries.pending().select_related("product__guild").order_by("-created_at")

    return render(
        request,
        "hub/tab_detail.html",
        {
            **ctx,
            "tab": tab,
            "entries": entries,
            "next_charge_at": BillingSettings.load().next_charge_at(),
        },
    )


@login_required
@require_POST
def void_tab_entry(request: HttpRequest, entry_pk: int) -> HttpResponse:
    """Remove a pending tab entry. Only the owning member can remove their own entries."""
    from billing.models import TabEntry as TabEntryModel
    from hub.toast import trigger_toast

    member = _get_member(request)
    if member is None:  # pragma: no cover — defensive; signal auto-creates Member on User creation
        return HttpResponse(status=404)

    entry = get_object_or_404(TabEntryModel, pk=entry_pk, tab__member=member)

    try:
        entry.void(user=request.user, reason="Removed by member")  # type: ignore[arg-type]
    except ValueError as e:
        response = HttpResponse(status=400)
        trigger_toast(response, str(e), "error")
        return response

    response = HttpResponse(status=204)
    trigger_toast(response, "Charge removed.", "success")
    return response


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


_CALENDAR_PAGE_SIZE = 10


def _get_calendar_context(
    request: HttpRequest, week_offset: int = 0, month_offset: int = 0, event_page: int = 1
) -> dict[str, Any]:
    """Build context for both the full calendar page and the HTMX partial.

    Args:
        week_offset: Weeks relative to the current week (negative = past, positive = future).
        month_offset: Months relative to the current month (negative = past, positive = future).
        event_page: 1-based page number for the event list (PAGE_SIZE events per page).
    """
    import calendar as _cal
    from collections import defaultdict
    from datetime import date as date_type

    from core.models import SiteConfiguration
    from membership.models import CalendarEvent, Guild

    def _shift_month(d: date_type, months: int) -> date_type:
        """Return the first day of the month shifted by `months`."""
        m = d.month - 1 + months
        return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)

    now = dj_timezone.now()
    today = now.date()

    # Navigated week
    current_week_start = today - timedelta(days=today.weekday())
    week_start = current_week_start + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    # Navigated month
    nav_month_first = _shift_month(today.replace(day=1), month_offset)
    nav_month_last_day = _cal.monthrange(nav_month_first.year, nav_month_first.month)[1]
    nav_month_last = nav_month_first.replace(day=nav_month_last_day)

    # Fetch only events covering the navigated week and month ranges
    fetch_from = min(week_start, nav_month_first)
    fetch_to = max(week_end, nav_month_last)

    all_events = list(
        CalendarEvent.objects.filter(start_dt__date__gte=fetch_from, start_dt__date__lte=fetch_to)
        .select_related("guild")
        .order_by("start_dt")
    )

    # Week event list: events whose start date falls within the navigated week
    week_events = [e for e in all_events if week_start <= e.start_dt.date() <= week_end]

    # Month event list: events whose start date falls within the navigated month (paginated)
    raw_month_events = [e for e in all_events if nav_month_first <= e.start_dt.date() <= nav_month_last]
    total_pages = max(1, (len(raw_month_events) + _CALENDAR_PAGE_SIZE - 1) // _CALENDAR_PAGE_SIZE)
    event_page = max(1, min(event_page, total_pages))
    page_start = (event_page - 1) * _CALENDAR_PAGE_SIZE
    month_events = raw_month_events[page_start : page_start + _CALENDAR_PAGE_SIZE]

    guilds_with_calendars = list(Guild.objects.filter(is_active=True, calendar_url__gt="").order_by("name"))

    config = SiteConfiguration.load()
    general_enabled = bool(config.general_calendar_url)
    general_color = config.general_calendar_color
    classes_enabled = config.sync_classes_enabled
    classes_color = config.classes_calendar_color

    source_colors: dict[str, str] = {"general": general_color, "classes": classes_color}
    for g in guilds_with_calendars:
        source_colors[str(g.pk)] = g.calendar_color

    # Group events by date for calendar grid dots
    events_by_date: dict = defaultdict(list)
    for evt in all_events:
        events_by_date[evt.start_dt.date()].append(evt)

    # Week label (e.g. "Apr 14 – 20, 2026" or "Apr 28 – May 4, 2026")
    if week_start.month == week_end.month and week_start.year == week_end.year:
        week_label = f"{week_start.strftime('%b %-d')} – {week_end.strftime('%-d')}, {week_end.year}"
    else:
        week_label = f"{week_start.strftime('%b %-d')} – {week_end.strftime('%b %-d')}, {week_end.year}"

    # Week grid: 7 days starting from navigated Monday
    week_days = [
        {
            "date": week_start + timedelta(days=i),
            "is_today": (week_start + timedelta(days=i)) == today,
            "events": events_by_date.get(week_start + timedelta(days=i), []),
        }
        for i in range(7)
    ]

    # Month label (e.g. "April 2026")
    month_label = nav_month_first.strftime("%B %Y")

    # Month grid: navigated month padded to complete 7-column rows (Mon–Sun)
    month_headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    leading = nav_month_first.weekday()
    trailing = (6 - nav_month_last.weekday()) % 7

    month_days = []
    for i in range(leading):
        d = nav_month_first - timedelta(days=leading - i)
        month_days.append({"date": d, "is_today": d == today, "in_month": False, "events": events_by_date.get(d, [])})
    for day_num in range(1, nav_month_last_day + 1):
        d = nav_month_first.replace(day=day_num)
        month_days.append({"date": d, "is_today": d == today, "in_month": True, "events": events_by_date.get(d, [])})
    for i in range(1, trailing + 1):
        d = nav_month_last + timedelta(days=i)
        month_days.append({"date": d, "is_today": d == today, "in_month": False, "events": events_by_date.get(d, [])})

    return {
        "week_events": week_events,
        "month_events": month_events,
        "event_page": event_page,
        "event_total_pages": total_pages,
        "guilds_with_calendars": guilds_with_calendars,
        "general_enabled": general_enabled,
        "general_color": general_color,
        "classes_enabled": classes_enabled,
        "classes_color": classes_color,
        "source_colors": source_colors,
        "week_days": week_days,
        "week_label": week_label,
        "week_offset": week_offset,
        "month_days": month_days,
        "month_headers": month_headers,
        "month_label": month_label,
        "month_offset": month_offset,
        "now": now,
    }


@login_required
def community_calendar(request: HttpRequest) -> HttpResponse:
    """Community Calendar page — upcoming events from all guild and general calendars."""
    ctx = _get_hub_context(request)
    cal_ctx = _get_calendar_context(request)

    default_filters = []
    if cal_ctx["general_enabled"]:
        default_filters.append("general")
    if cal_ctx["classes_enabled"]:
        default_filters.append("classes")
    for g in cal_ctx["guilds_with_calendars"]:
        default_filters.append(str(g.pk))

    cal_ctx["default_filters_json"] = json.dumps(default_filters).replace('"', '\\"')
    return render(request, "hub/community_calendar.html", {**ctx, **cal_ctx})


@login_required
def calendar_events_partial(request: HttpRequest) -> HttpResponse:
    """HTMX partial — refreshes stale calendar sources and returns updated event HTML."""
    refresh_stale_sources()
    try:
        week_offset = max(-52, min(52, int(request.GET.get("week_offset", 0))))
        month_offset = max(-24, min(24, int(request.GET.get("month_offset", 0))))
        event_page = max(1, int(request.GET.get("page", 1)))
    except (ValueError, TypeError):
        week_offset = 0
        month_offset = 0
        event_page = 1
    cal_ctx = _get_calendar_context(request, week_offset=week_offset, month_offset=month_offset, event_page=event_page)
    return render(request, "hub/partials/calendar_content.html", cal_ctx)


def _ical_escape(value: str) -> str:
    """Escape special characters per RFC 5545 §3.3.11."""
    value = value.replace("\\", "\\\\")
    value = value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    value = value.replace(";", "\\;").replace(",", "\\,")
    return value


@login_required
def calendar_export_ics(request: HttpRequest) -> HttpResponse:
    """Download a combined iCal file of all upcoming events."""
    from membership.models import CalendarEvent

    now = dj_timezone.now()
    horizon = now + timedelta(days=90)
    events = (
        CalendarEvent.objects.filter(start_dt__gte=now, start_dt__lte=horizon)
        .select_related("guild")
        .order_by("start_dt")
    )

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Past Lives Makerspace//Community Calendar//EN",
        "X-WR-CALNAME:Past Lives Community Calendar",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for evt in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{evt.uid}",
            f"SUMMARY:{_ical_escape(evt.title)}",
        ]
        if evt.all_day:
            lines += [
                f"DTSTART;VALUE=DATE:{evt.start_dt.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{evt.end_dt.strftime('%Y%m%d')}",
            ]
        else:
            lines += [
                f"DTSTART:{evt.start_dt.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{evt.end_dt.strftime('%Y%m%dT%H%M%SZ')}",
            ]
        if evt.description:
            lines.append(f"DESCRIPTION:{_ical_escape(evt.description[:250])}")
        if evt.location:
            lines.append(f"LOCATION:{evt.location}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    ical_content = "\r\n".join(lines) + "\r\n"

    response = HttpResponse(ical_content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="past-lives-calendar.ics"'
    return response
