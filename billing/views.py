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

    # Ensure Stripe customer exists
    if not tab.stripe_customer_id:
        customer_id = stripe_utils.create_customer(
            email=member.email,
            name=member.display_name,
            member_pk=member.pk,
        )
        tab.stripe_customer_id = customer_id
        tab.save(update_fields=["stripe_customer_id"])

    result = stripe_utils.create_setup_intent(customer_id=tab.stripe_customer_id)
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

    # Attach to customer and retrieve details
    if tab.stripe_customer_id:
        stripe_utils.attach_payment_method(
            customer_id=tab.stripe_customer_id,
            payment_method_id=payment_method_id,
        )

    pm_details = stripe_utils.retrieve_payment_method(payment_method_id=payment_method_id)
    tab.stripe_payment_method_id = pm_details["id"]
    tab.payment_method_last4 = pm_details["last4"]
    tab.payment_method_brand = pm_details["brand"]
    tab.save(
        update_fields=[
            "stripe_payment_method_id",
            "payment_method_last4",
            "payment_method_brand",
            "updated_at",
        ]
    )

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

    if tab.stripe_payment_method_id:
        stripe_utils.detach_payment_method(payment_method_id=tab.stripe_payment_method_id)
        tab.stripe_payment_method_id = ""
        tab.payment_method_last4 = ""
        tab.payment_method_brand = ""
        tab.save(
            update_fields=[
                "stripe_payment_method_id",
                "payment_method_last4",
                "payment_method_brand",
                "updated_at",
            ]
        )

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


@staff_member_required
def admin_tab_dashboard(request: HttpRequest) -> HttpResponse:
    """Admin payments dashboard — aggregate stats, outstanding tabs, failed charges."""
    from django.contrib import admin

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

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

    context = {
        **admin.site.each_context(request),
        "total_outstanding": total_outstanding,
        "collected_this_month": collected_this_month,
        "failed_count": failed_count,
        "locked_count": locked_count,
        "outstanding_tabs": outstanding_tabs,
        "failed_charges": failed_charges,
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
            TabEntry.objects.create(
                tab=tab,
                description=form.cleaned_data["description"],
                amount=form.cleaned_data["amount"],
                added_by=request.user,  # type: ignore[misc]  # @staff_member_required guarantees User
                product=product,
            )
            django_messages.success(request, f"Added ${form.cleaned_data['amount']} to {member.display_name}'s tab.")
            return redirect("billing_admin_dashboard")
    else:
        form = AdminAddTabEntryForm()

    context = {**admin.site.each_context(request), "form": form}
    return render(request, "billing/admin_add_entry.html", context)


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
def initiate_connect(request: HttpRequest, guild_id: int) -> HttpResponse:
    """Redirect admin to Stripe Connect OAuth to link a guild's account."""
    url = stripe_utils.get_connect_oauth_url(state=str(guild_id))
    return redirect(url)


@staff_member_required
def connect_callback(request: HttpRequest) -> HttpResponse:
    """Handle Stripe Connect OAuth callback."""
    from membership.models import Guild

    error = request.GET.get("error")
    if error:
        django_messages.error(request, f"Stripe Connect failed: {request.GET.get('error_description', error)}")
        return redirect("billing_admin_dashboard")

    code = request.GET.get("code", "")
    guild_id = request.GET.get("state", "")
    account_id = stripe_utils.complete_connect_oauth(code=code)
    guild = Guild.objects.get(pk=int(guild_id))

    StripeAccount.objects.update_or_create(
        guild=guild,
        defaults={
            "stripe_account_id": account_id,
            "display_name": guild.name,
            "is_active": True,
            "connected_at": timezone.now(),
        },
    )
    django_messages.success(request, f"Connected Stripe account for {guild.name}.")
    return redirect("billing_admin_dashboard")
