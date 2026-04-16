"""Core app views for PWA push notification infrastructure."""

import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from allauth.account.internal.stagekit import clear_login

from plfog.capabilities import SESSION_HIDDEN_KEY, Capability, admin_capability_required

from .forms import FindAccountForm
from .models import PushSubscription, SiteConfiguration

logger = logging.getLogger(__name__)


def health_check(request):
    """Health check endpoint."""
    return JsonResponse({"status": "ok"})


def restart_login(request: HttpRequest) -> HttpResponse:
    """Clear any pending login stage and redirect to the login page."""
    clear_login(request)
    return redirect("account_login")


def find_account(request: HttpRequest) -> HttpResponse:
    """Look up a member by name and send a login link to the email on file."""
    if request.method == "POST":
        form = FindAccountForm(request.POST)
        if form.is_valid():
            form.send_login_email()
            return render(request, "account/find_account_done.html")
    else:
        form = FindAccountForm()
    return render(request, "account/find_account.html", {"form": form})


def home(request):
    """Home page view."""
    if request.user.is_authenticated:
        return redirect("hub_guild_voting")
    return render(request, "home.html")


@require_GET
def service_worker(request):
    """Serve the service worker JavaScript file.

    The Service-Worker-Allowed header is set by ServiceWorkerAllowedMiddleware,
    not by this view, to avoid redundancy and ensure mutation test coverage.
    """
    sw_path = Path(settings.BASE_DIR) / "static" / "js" / "sw.js"
    if not sw_path.exists():
        return HttpResponse("Service worker not found", status=404)

    with open(sw_path) as f:
        content = f.read()

    return HttpResponse(content, content_type="application/javascript")


@require_GET
@login_required
def vapid_key(request):
    """Return the VAPID public key for push subscription.

    iOS graceful degradation: Returns the key if configured.
    Client-side code handles unavailability gracefully.
    """
    vapid_public_key = settings.WEBPUSH_SETTINGS.get("VAPID_PUBLIC_KEY", "")
    return JsonResponse({"vapid_public_key": vapid_public_key})


@require_POST
@login_required
def subscribe(request):
    """Create a push subscription for the authenticated user.

    Expects JSON body with: endpoint, p256dh, auth
    Returns success/error JSON response.
    iOS graceful degradation: No errors if push features unavailable on client.
    """
    try:
        data = json.loads(request.body)
        endpoint = data.get("endpoint")
        p256dh = data.get("p256dh")
        auth = data.get("auth")

        if not all([endpoint, p256dh, auth]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "p256dh": p256dh,
                "auth": auth,
            },
        )

        return JsonResponse({"success": True})

    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception:
        logger.exception("Push subscription failed")
        return JsonResponse({"error": "Subscription failed. Please try again."}, status=500)


@require_POST
@login_required
def unsubscribe(request):
    """Delete a push subscription for the authenticated user.

    Expects JSON body with: endpoint
    Returns success/error JSON response.
    iOS graceful degradation: Silently succeeds even if subscription doesn't exist.
    """
    try:
        data = json.loads(request.body)
        endpoint = data.get("endpoint")

        if not endpoint:
            return JsonResponse({"error": "Missing endpoint"}, status=400)

        # Delete silently - no error if doesn't exist (iOS graceful degradation)
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()

        return JsonResponse({"success": True})

    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception:
        logger.exception("Push unsubscription failed")
        return JsonResponse({"error": "Unsubscription failed. Please try again."}, status=500)


@admin_capability_required
def site_settings(request: HttpRequest) -> HttpResponse:
    """Hub-native Site Settings page. Admin capability required."""
    from django import forms

    class SiteConfigurationForm(forms.ModelForm):
        class Meta:
            model = SiteConfiguration
            fields = ["registration_mode"]

    config = SiteConfiguration.load()
    if request.method == "POST":
        form = SiteConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            from django.contrib import messages
            messages.success(request, "Site settings saved.")
            return redirect("site_settings")
    else:
        form = SiteConfigurationForm(instance=config)
    return render(request, "core/site_settings.html", {"form": form, "config": config})


@require_POST
@login_required
def capabilities_toggle(request: HttpRequest) -> JsonResponse:
    """Add or remove a capability from the session-hidden set.

    Request body: ``{"capability": "admin", "hidden": true}``. When
    ``hidden`` is true the capability is added to the hidden set (the
    user unchecked its "Viewing as" checkbox); when false it's removed.
    Unknown capabilities are rejected so junk never lands in the session.
    Capabilities the user does not actually hold are also rejected — you
    can only hide what you have.
    """
    try:
        payload = json.loads(request.body or b"{}")
        name = payload["capability"]
        hidden = bool(payload["hidden"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"error": "Invalid request"}, status=400)

    if name not in Capability.ALL:
        return JsonResponse({"error": f"Unknown capability '{name}'"}, status=400)

    if not request.capabilities.has_actual(name):
        return JsonResponse({"error": "Cannot toggle a capability you don't have"}, status=403)

    current = set(request.session.get(SESSION_HIDDEN_KEY, []))
    if hidden:
        current.add(name)
    else:
        current.discard(name)
    request.session[SESSION_HIDDEN_KEY] = sorted(current)

    return JsonResponse({"hidden": sorted(current)})
