"""Views for the member hub."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from billing.exceptions import NoPaymentMethodError, TabLimitExceededError, TabLockedError
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
    # Admins see every member regardless of status or show_in_directory.
    if request.capabilities.is_admin:
        base_qs = Member.objects.all()
    else:
        base_qs = Member.objects.filter(status=Member.Status.ACTIVE, show_in_directory=True)
    members = (
        base_qs
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
    """Guild detail page — shows about text, active products, and cart interface."""
    guild = get_object_or_404(Guild, pk=pk)
    ctx = _get_hub_context(request)
    products = guild.products.filter(is_active=True).order_by("name")
    member = _get_member(request)

    tab: Tab | None = None
    if member is not None:
        tab, _created = Tab.objects.get_or_create(member=member)

    from membership.models import Guild as _Guild

    can_manage = request.capabilities.can_manage_guild(guild)
    manage_context: dict[str, Any] = {}
    if can_manage:
        products_json = []
        for p in products.select_related("revenue_split"):
            split_rows = []
            if p.revenue_split_id is not None:
                for r in p.revenue_split.recipients.order_by("pk"):
                    split_rows.append({
                        "entity": "admin" if r.guild_id is None else str(r.guild_id),
                        "percent": str(r.percent),
                    })
            products_json.append({
                "id": p.pk,
                "name": p.name,
                "description": p.description,
                "price": str(p.price),
                "recipients": split_rows,
            })
        manage_context = {
            "active_guilds": list(_Guild.objects.filter(is_active=True).order_by("name").values("pk", "name")),
            "products_json": json.dumps(products_json),
        }

    # Members list for lead/officer pickers. Shown to anyone who can manage
    # this guild (admins always, leads, and existing officers).
    picker_members: list[dict[str, Any]] = []
    if can_manage:
        picker_members = list(
            Member.objects.filter(status=Member.Status.ACTIVE)
            .order_by("full_legal_name")
            .values("pk", "full_legal_name")
        )

    # Leadership roster as a single list, lead first, then titled roles.
    # Each row: {role_pk (None for the lead), member_pk, member_name, title}
    leadership_rows: list[dict[str, Any]] = []
    if guild.guild_lead_id:
        leadership_rows.append({
            "role_pk": None,
            "member_pk": guild.guild_lead_id,
            "member_name": guild.guild_lead.display_name,
            "title": "Guild Lead",
            "is_lead": True,
        })
    for r in guild.officer_roles.select_related("member").order_by("title", "member__full_legal_name"):
        leadership_rows.append({
            "role_pk": r.pk,
            "member_pk": r.member_id,
            "member_name": r.member.display_name,
            "title": r.title,
            "is_lead": False,
        })
    leadership_json = json.dumps(leadership_rows)

    return render(
        request,
        "hub/guild_detail.html",
        {
            **ctx,
            "guild": guild,
            "products": products,
            "tab": tab,
            "can_manage": can_manage,
            "picker_members": picker_members,
            "leadership_json": leadership_json,
            **manage_context,
        },
    )


@login_required
@require_POST
def guild_update(request: HttpRequest, pk: int) -> JsonResponse:
    """Update a guild's fields. Admin/guild-officer only.

    Members/officers can edit name + about. Admins can additionally edit
    is_active, notes, and guild_lead (admin-only metadata fields).
    """
    guild = get_object_or_404(Guild, pk=pk)
    if not request.capabilities.can_manage_guild(guild):
        return JsonResponse({"ok": False, "error": "You don't have permission to edit this guild."}, status=403)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        return JsonResponse({"ok": False, "error": f"Invalid JSON: {exc}"}, status=400)

    name = (payload.get("name") or "").strip()
    about = payload.get("about")
    if about is None:
        about = guild.about
    about = (about or "").strip()

    if not name:
        return JsonResponse({"ok": False, "error": "Name is required."}, status=400)

    guild.name = name
    guild.about = about
    update_fields = ["name", "about"]

    if request.capabilities.is_admin and "guild_lead_id" in payload:
        lead_id = payload["guild_lead_id"]
        guild.guild_lead_id = int(lead_id) if lead_id else None
        update_fields.append("guild_lead")

    guild.save(update_fields=update_fields)

    # Officer roles — managers can replace the full roster.
    # Payload: "officer_roles": [{"member_id": 42, "title": "Treasurer"}, ...]
    if "officer_roles" in payload:
        from membership.models import GuildOfficerRole
        rows = payload["officer_roles"]
        if not isinstance(rows, list):
            return JsonResponse({"ok": False, "error": "officer_roles must be a list."}, status=400)
        cleaned: list[tuple[int, str]] = []
        for r in rows:
            try:
                mid = int(r["member_id"])
                title = str(r["title"]).strip()
            except (KeyError, TypeError, ValueError):
                return JsonResponse({"ok": False, "error": "Each role needs member_id and title."}, status=400)
            if not title:
                return JsonResponse({"ok": False, "error": "Title cannot be empty."}, status=400)
            cleaned.append((mid, title))
        # Replace: delete all existing, recreate. Simplest for a small roster.
        guild.officer_roles.all().delete()
        for mid, title in cleaned:
            GuildOfficerRole.objects.create(guild=guild, member_id=mid, title=title)

    current_roles = [
        {"role_pk": r.pk, "member_id": r.member_id, "title": r.title}
        for r in guild.officer_roles.select_related("member").order_by("title")
    ]
    return JsonResponse({
        "ok": True,
        "guild": {
            "pk": guild.pk,
            "name": guild.name,
            "about": guild.about,
            "guild_lead_id": guild.guild_lead_id,
            "officer_roles": current_roles,
        },
    })


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

    active_products = {p.pk: p for p in guild.products.filter(is_active=True)}
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

    # Piggyback the updated tab balance on the HX-Trigger header so the cart
    # JS can dispatch a window event and the header pill updates in place.
    trigger_payload = json.loads(success_response["HX-Trigger"])
    trigger_payload["tabBalanceUpdated"] = {"balance": str(tab.current_balance)}
    success_response["HX-Trigger"] = json.dumps(trigger_payload)

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
            try:
                if not tab.can_add_entry:
                    raise NoPaymentMethodError("Payment method required.")
                form.apply_to_tab(tab, added_by=request.user, is_self_service=True)  # type: ignore[arg-type]
                response = HttpResponse(status=204)
                trigger_toast(response, "Added to your tab!", "success")
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
    from billing.forms import VoidTabEntryForm

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
                if not tab.can_add_entry:
                    raise NoPaymentMethodError("You need a payment method on file before adding charges.")
                form.apply_to_tab(
                    tab,
                    added_by=request.user,  # type: ignore[arg-type]  # @login_required guarantees User
                    is_self_service=True,
                )
                messages.success(request, "Item added to your tab.")
                return redirect("hub_tab_detail")
            except NoPaymentMethodError:
                messages.error(request, "You need a payment method on file before adding charges.")
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
            "void_form": VoidTabEntryForm(),
        },
    )


@login_required
@require_POST
def void_tab_entry(request: HttpRequest, entry_pk: int) -> HttpResponse:
    """Void a pending tab entry. Only the owning member can void their own entries."""
    from billing.forms import VoidTabEntryForm
    from billing.models import TabEntry as TabEntryModel
    from hub.toast import trigger_toast

    member = _get_member(request)
    if member is None:  # pragma: no cover — defensive; signal auto-creates Member on User creation
        return HttpResponse(status=404)

    entry = get_object_or_404(TabEntryModel, pk=entry_pk, tab__member=member)

    form = VoidTabEntryForm(request.POST)
    if form.is_valid():
        try:
            entry.void(user=request.user, reason=form.cleaned_data["reason"])  # type: ignore[arg-type]
            response = HttpResponse(status=204)
            trigger_toast(response, "Charge voided.", "success")
            return response
        except ValueError as e:
            response = HttpResponse(status=400)
            trigger_toast(response, str(e), "error")
            return response

    response = HttpResponse(status=400)
    trigger_toast(response, "Reason is required.", "error")
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
