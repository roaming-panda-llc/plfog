"""Views for billing — payment method setup, Stripe AJAX endpoints, admin actions."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib import messages as django_messages
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from billing import stripe_utils, webhook_handlers
from billing.exceptions import NoPaymentMethodError, TabLimitExceededError, TabLockedError
from billing.forms import AdminAddTabEntryForm
from billing.models import BillingSettings, StripeAccount, Tab, TabCharge, TabEntry

logger = logging.getLogger(__name__)

# Map Stripe event types to handler functions
_WEBHOOK_HANDLERS = {
    "setup_intent.succeeded": webhook_handlers.handle_setup_intent_succeeded,
    "payment_intent.succeeded": webhook_handlers.handle_payment_intent_succeeded,
    "payment_intent.payment_failed": webhook_handlers.handle_payment_intent_failed,
    "payment_method.detached": webhook_handlers.handle_payment_method_detached,
    "payment_method.updated": webhook_handlers.handle_payment_method_updated,
    "charge.dispute.created": webhook_handlers.handle_charge_dispute_created,
}


@login_required
def setup_payment_method(request: HttpRequest) -> HttpResponse:
    """Page with Stripe Elements for adding/replacing a payment method."""
    from membership.models import Member

    member: Member | None = getattr(request.user, "member", None)
    if member is None:
        return redirect("hub_tab_detail")

    tab, _created = Tab.objects.get_or_create(member=member)

    return render(
        request,
        "billing/setup_payment_method.html",
        {
            "tab": tab,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        },
    )


@login_required
@require_POST
def create_setup_intent_api(request: HttpRequest) -> JsonResponse:
    """AJAX endpoint — creates a Stripe SetupIntent and returns the client_secret."""
    from membership.models import Member

    member: Member | None = getattr(request.user, "member", None)
    if member is None:
        return JsonResponse({"error": "No membership found."}, status=400)

    tab, _created = Tab.objects.get_or_create(member=member)
    customer_id = tab.get_or_create_stripe_customer()
    result = stripe_utils.create_setup_intent(customer_id=customer_id)
    return JsonResponse(result)


@login_required
@require_POST
def confirm_setup(request: HttpRequest) -> HttpResponse:
    """Post-setup callback — updates Tab with the new payment method details."""
    from membership.models import Member

    member: Member | None = getattr(request.user, "member", None)
    if member is None:
        return redirect("hub_tab_detail")

    tab, _created = Tab.objects.get_or_create(member=member)

    payment_method_id = request.POST.get("payment_method_id", "")
    if not payment_method_id:
        return redirect("billing_setup_payment_method")

    tab.set_payment_method(payment_method_id)
    return redirect("hub_tab_detail")


@login_required
@require_POST
def remove_payment_method(request: HttpRequest) -> HttpResponse:
    """Detach the payment method from Stripe and clear Tab fields."""
    from membership.models import Member

    member: Member | None = getattr(request.user, "member", None)
    if member is None:
        return redirect("hub_tab_detail")

    tab, _created = Tab.objects.get_or_create(member=member)
    tab.clear_payment_method()
    return redirect("hub_tab_detail")


@csrf_exempt
@require_POST
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """Stripe webhook endpoint — verifies signature and dispatches to handlers."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe_utils.construct_webhook_event(payload=payload, sig_header=sig_header)
    except Exception:
        logger.exception("Webhook signature verification failed.")
        return HttpResponse(status=400)

    event_type = event.type if hasattr(event, "type") else event.get("type", "")
    handler = _WEBHOOK_HANDLERS.get(event_type)

    if handler:
        try:
            event_data = event.to_dict() if hasattr(event, "to_dict") else dict(event)
            handler(event_data)
        except Exception:
            logger.exception("Webhook handler error for event %s", event_type)
            return HttpResponse(status=500)
    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    return HttpResponse(status=200)


_VALID_TABS = {"overview", "open-tabs", "history", "settings", "stripe"}


@staff_member_required
def admin_tab_dashboard(request: HttpRequest) -> HttpResponse:
    """Admin payments dashboard — five-tab view of billing data."""
    from django.contrib import admin as django_admin
    from billing.forms import AdminAddTabEntryForm, BillingSettingsForm
    from billing.models import BillingSettings, Product, StripeAccount
    from membership.models import Guild

    active_tab = request.GET.get("tab", "overview")
    if active_tab not in _VALID_TABS:
        active_tab = "overview"

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # --- Overview stats ---
    total_outstanding = TabEntry.objects.pending().aggregate(
        total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField())
    )["total"]

    collected_this_month = TabCharge.objects.filter(
        status=TabCharge.Status.SUCCEEDED,
        charged_at__gte=month_start,
    ).aggregate(total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField()))["total"]

    failed_count = TabCharge.objects.filter(status=TabCharge.Status.FAILED).count()
    locked_count = Tab.objects.filter(is_locked=True).count()

    outstanding_tabs = (
        Tab.objects.filter(
            entries__tab_charge__isnull=True,
            entries__voided_at__isnull=True,
        )
        .distinct()
        .select_related("member")
    )

    failed_charges = (
        TabCharge.objects.filter(status=TabCharge.Status.FAILED)
        .select_related("tab__member")
        .order_by("-created_at")[:20]
    )

    # --- Open Tabs tab ---
    tab_filter = request.GET.get("filter", "outstanding")
    if tab_filter == "all":
        open_tabs = Tab.objects.select_related("member").order_by("member__full_legal_name")
    elif tab_filter == "failed":
        open_tabs = Tab.objects.filter(charges__status=TabCharge.Status.FAILED).distinct().select_related("member")
    else:  # outstanding (default)
        open_tabs = (
            Tab.objects.filter(
                entries__tab_charge__isnull=True,
                entries__voided_at__isnull=True,
            )
            .distinct()
            .select_related("member")
        )

    # --- History tab ---
    charge_status_filter = request.GET.get("status", "all")
    if charge_status_filter == "succeeded":
        history_charges = TabCharge.objects.succeeded().select_related("tab__member", "stripe_account")
    elif charge_status_filter == "failed":
        history_charges = TabCharge.objects.failed().select_related("tab__member", "stripe_account")
    elif charge_status_filter == "needs_retry":
        history_charges = TabCharge.objects.needs_retry().select_related("tab__member", "stripe_account")
    else:
        history_charges = TabCharge.objects.exclude(status=TabCharge.Status.PENDING).select_related(
            "tab__member", "stripe_account"
        )
    history_charges = history_charges.order_by("-created_at")

    history_collected = TabCharge.objects.filter(
        status=TabCharge.Status.SUCCEEDED,
        charged_at__gte=month_start,
    ).aggregate(total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField()))["total"]

    history_failed_count = TabCharge.objects.filter(
        status=TabCharge.Status.FAILED,
        created_at__gte=month_start,
    ).count()

    history_total_count = (
        TabCharge.objects.filter(created_at__gte=month_start).exclude(status=TabCharge.Status.PENDING).count()
    )

    history_succeeded_count = TabCharge.objects.filter(
        status=TabCharge.Status.SUCCEEDED,
        charged_at__gte=month_start,
    ).count()

    history_success_rate = int(history_succeeded_count / history_total_count * 100) if history_total_count else 100

    # --- Settings tab ---
    settings_obj = BillingSettings.load()
    settings_form = BillingSettingsForm(instance=settings_obj)

    # --- Stripe tab ---
    stripe_accounts = StripeAccount.objects.select_related("guild").order_by("display_name")
    products = Product.objects.select_related("guild").order_by("guild__name", "name")
    guilds = Guild.objects.filter(is_active=True).order_by("name")

    # --- Add Charge modal form ---
    add_charge_form = AdminAddTabEntryForm()

    context = {
        **django_admin.site.each_context(request),
        "active_tab": active_tab,
        "tab_filter": tab_filter,
        "charge_status_filter": charge_status_filter,
        # Overview
        "total_outstanding": total_outstanding,
        "collected_this_month": collected_this_month,
        "failed_count": failed_count,
        "locked_count": locked_count,
        "outstanding_tabs": outstanding_tabs,
        "failed_charges": failed_charges,
        # Open Tabs
        "open_tabs": open_tabs,
        # History
        "history_charges": history_charges,
        "history_collected": history_collected,
        "history_failed_count": history_failed_count,
        "history_success_rate": history_success_rate,
        # Settings
        "settings_form": settings_form,
        # Stripe
        "stripe_accounts": stripe_accounts,
        "products": products,
        "guilds": guilds,
        # Shared
        "add_charge_form": add_charge_form,
    }

    return render(request, "billing/admin_dashboard.html", context)


@staff_member_required
def admin_add_tab_entry(request: HttpRequest) -> HttpResponse:
    """Admin quick-add: add a charge to any member's tab."""
    from django.contrib import admin

    if request.method == "POST":
        form = AdminAddTabEntryForm(request.POST)
        if form.is_valid():
            member = form.cleaned_data["member"]
            tab, _created = Tab.objects.get_or_create(member=member)
            product = form.cleaned_data.get("product")
            try:
                tab.add_entry(
                    description=form.cleaned_data["description"],
                    amount=form.cleaned_data["amount"],
                    added_by=request.user,  # type: ignore[misc]
                    product=product,
                )
            except (TabLockedError, NoPaymentMethodError, TabLimitExceededError) as exc:
                django_messages.error(request, str(exc))
                context = {**admin.site.each_context(request), "form": form}
                return render(request, "billing/admin_add_entry.html", context)
            django_messages.success(request, f"Added ${form.cleaned_data['amount']} to {member.display_name}'s tab.")
            return redirect("billing_admin_dashboard")
    else:
        form = AdminAddTabEntryForm()

    context = {**admin.site.each_context(request), "form": form}
    return render(request, "billing/admin_add_entry.html", context)


@staff_member_required
def billing_admin_tab_detail_api(request: HttpRequest, tab_pk: int) -> JsonResponse:
    """Return JSON tab detail for the tab detail modal."""
    try:
        tab = Tab.objects.select_related("member").get(pk=tab_pk)
    except Tab.DoesNotExist:
        from django.http import Http404

        raise Http404

    pending_entries = list(
        tab.entries.filter(tab_charge__isnull=True, voided_at__isnull=True)
        .select_related("product__guild")
        .order_by("-created_at")
        .values("description", "amount", "created_at")
    )

    charge_history = list(
        tab.charges.exclude(status=TabCharge.Status.PENDING)
        .order_by("-created_at")[:20]
        .values("amount", "status", "charged_at", "stripe_receipt_url")
    )

    payment_method = ""
    if tab.payment_method_brand and tab.payment_method_last4:
        payment_method = f"{tab.payment_method_brand} {tab.payment_method_last4}"

    return JsonResponse(
        {
            "member_name": tab.member.display_name,
            "balance": f"{tab.current_balance:.2f}",
            "limit": f"{tab.effective_tab_limit:.2f}",
            "payment_method": payment_method,
            "is_locked": tab.is_locked,
            "locked_reason": tab.locked_reason,
            "tab_pk": tab.pk,
            "pending_entries": [
                {
                    "description": e["description"],
                    "amount": f"{e['amount']:.2f}",
                    "date": e["created_at"].strftime("%-d %b") if e["created_at"] else "",
                }
                for e in pending_entries
            ],
            "charge_history": [
                {
                    "amount": f"{c['amount']:.2f}",
                    "status": c["status"],
                    "date": c["charged_at"].strftime("%-d %b %Y") if c["charged_at"] else "—",
                    "receipt_url": c["stripe_receipt_url"] or "",
                }
                for c in charge_history
            ],
        }
    )


@staff_member_required
@require_POST
def billing_admin_save_settings(request: HttpRequest) -> HttpResponse:
    """Save BillingSettings singleton from the Settings tab form."""
    from billing.forms import BillingSettingsForm

    settings_obj = BillingSettings.load()
    form = BillingSettingsForm(request.POST, instance=settings_obj)
    if form.is_valid():
        form.save()
        django_messages.success(request, "Billing settings saved.")
    else:
        django_messages.error(request, "Invalid settings — please check the form.")
    return redirect("/billing/admin/dashboard/?tab=settings")


@staff_member_required
@require_POST
def billing_admin_retry_charge(request: HttpRequest, charge_pk: int) -> JsonResponse:
    """Immediately retry a single failed charge. Returns JSON with new status."""
    import uuid as _uuid

    try:
        charge = TabCharge.objects.select_related("tab", "stripe_account").get(pk=charge_pk)
    except TabCharge.DoesNotExist:
        from django.http import Http404

        raise Http404

    idempotency_key = f"admin-retry-{charge.pk}-{_uuid.uuid4()}"
    success = charge.execute_stripe_charge(idempotency_key)
    if success:
        return JsonResponse({"status": "succeeded"})
    logger.exception("Admin retry failed for charge %s.", charge.pk)
    return JsonResponse({"status": "failed"})


@staff_member_required
def initiate_connect(request: HttpRequest, guild_id: int) -> HttpResponse:
    """Redirect admin to Stripe Connect OAuth to link a guild's account."""
    url = stripe_utils.get_connect_oauth_url(state=str(guild_id))
    return redirect(url)


@staff_member_required
@require_POST
def billing_test_direct_keys(request: HttpRequest) -> JsonResponse:
    """AJAX: verify a pasted Stripe secret key by calling accounts.retrieve('self').

    Returns 200 with `{ok: true, stripe_account_id, display_name, charges_enabled}`
    on success, or 200 with `{ok: false, error}` on failure (always 200 so the
    frontend can render the message inline).
    """
    secret_key = request.POST.get("secret_key", "").strip()
    if not secret_key:
        return JsonResponse({"ok": False, "error": "Secret key is required."})
    if not (secret_key.startswith("sk_test_") or secret_key.startswith("sk_live_") or secret_key.startswith("rk_")):
        return JsonResponse({"ok": False, "error": "Key must start with sk_test_, sk_live_, or rk_."})
    try:
        result = stripe_utils.verify_account_credentials(secret_key)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Stripe rejected the key: {exc}"})
    return JsonResponse({"ok": True, **result})


@staff_member_required
@require_POST
def billing_save_direct_keys(request: HttpRequest) -> HttpResponse:
    """Save (or update) a guild's direct-keys Stripe credentials."""
    from membership.models import Guild

    try:
        guild_id = int(request.POST["guild_id"])
    except (KeyError, ValueError):
        django_messages.error(request, "Guild is required.")
        return redirect("/billing/admin/dashboard/?tab=stripe")

    secret_key = request.POST.get("secret_key", "").strip()
    publishable_key = request.POST.get("publishable_key", "").strip()
    webhook_secret = request.POST.get("webhook_secret", "").strip()

    if not secret_key or not publishable_key:
        django_messages.error(request, "Secret key and publishable key are both required.")
        return redirect("/billing/admin/dashboard/?tab=stripe")

    try:
        verified = stripe_utils.verify_account_credentials(secret_key)
    except Exception as exc:
        django_messages.error(request, f"Could not verify the secret key: {exc}")
        return redirect("/billing/admin/dashboard/?tab=stripe")

    try:
        guild = Guild.objects.get(pk=guild_id)
    except Guild.DoesNotExist:
        django_messages.error(request, "Guild not found.")
        return redirect("/billing/admin/dashboard/?tab=stripe")

    StripeAccount.upsert_direct_keys(
        guild,
        stripe_account_id=verified["stripe_account_id"],
        display_name=verified["display_name"] or guild.name,
        secret_key=secret_key,
        publishable_key=publishable_key,
        webhook_secret=webhook_secret,
    )
    if webhook_secret:
        django_messages.success(
            request,
            f"Connected {guild.name} via direct API keys ({verified['stripe_account_id']}).",
        )
    else:
        django_messages.success(
            request,
            (
                f"Saved API keys for {guild.name}. Now go to the Stripe dashboard for this account, "
                "create a webhook pointing at /billing/webhooks/stripe/guild/"
                f"{guild.pk}/, then come back and paste the signing secret."
            ),
        )
    return redirect("/billing/admin/dashboard/?tab=stripe")


@csrf_exempt
@require_POST
def stripe_webhook_for_guild(request: HttpRequest, guild_id: int) -> HttpResponse:
    """Per-guild webhook endpoint for direct-keys mode.

    Verifies the signature using the guild's own webhook signing secret, then
    dispatches through the same handlers as the global webhook endpoint.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        account = StripeAccount.objects.get(
            guild_id=guild_id,
            auth_mode=StripeAccount.AuthMode.DIRECT_KEYS,
        )
    except StripeAccount.DoesNotExist:
        logger.warning("Direct-keys webhook hit for guild %s but no account exists.", guild_id)
        return HttpResponse(status=404)

    if not account.direct_webhook_secret:
        logger.warning("Direct-keys webhook hit for guild %s but no webhook secret is set.", guild_id)
        return HttpResponse(status=400)

    try:
        event = stripe_utils.construct_webhook_event_for_account(
            payload=payload,
            sig_header=sig_header,
            webhook_secret=account.direct_webhook_secret,
        )
    except Exception:
        logger.exception("Per-guild webhook signature verification failed for guild %s.", guild_id)
        return HttpResponse(status=400)

    event_type = event.type if hasattr(event, "type") else event.get("type", "")
    handler = _WEBHOOK_HANDLERS.get(event_type)
    if handler:
        try:
            event_data = event.to_dict() if hasattr(event, "to_dict") else dict(event)
            handler(event_data)
        except Exception:
            logger.exception("Per-guild webhook handler error for event %s", event_type)
            return HttpResponse(status=500)
    else:
        logger.debug("Unhandled per-guild webhook event type: %s", event_type)
    return HttpResponse(status=200)


@staff_member_required
def connect_callback(request: HttpRequest) -> HttpResponse:
    """Handle Stripe Connect OAuth callback."""
    from membership.models import Guild

    error = request.GET.get("error")
    if error:
        django_messages.error(request, f"Stripe Connect failed: {request.GET.get('error_description', error)}")
        return redirect("billing_admin_dashboard")

    try:
        code = request.GET["code"]
        guild_id = request.GET["state"]
    except KeyError:
        django_messages.error(request, "Stripe Connect callback is missing required parameters.")
        return redirect("billing_admin_dashboard")
    account_id = stripe_utils.complete_connect_oauth(code=code)
    guild = Guild.objects.get(pk=int(guild_id))

    StripeAccount.upsert_for_guild(guild, account_id)
    django_messages.success(request, f"Connected Stripe account for {guild.name}.")
    return redirect("billing_admin_dashboard")
