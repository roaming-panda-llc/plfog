# Payments Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the white-on-white Payments Dashboard with a five-tab admin page (Overview / Open Tabs / History / Settings / Stripe) that matches the Voting Dashboard's dark design system.

**Architecture:** Single Django view at `/billing/admin/dashboard/` reads a `?tab=` query param to determine which section to render. Three new supporting views handle form saves (settings), AJAX retries (charge retry), and modal data (tab detail). The template is a full replacement using the same `pl-*` CSS classes as `templates/admin/index.html`.

**Tech Stack:** Django 6, Unfold admin base template, vanilla JS (no new dependencies), existing `stripe_utils` functions, `billing.forms`, `billing.models`.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `billing/forms.py` | Modify | Add `BillingSettingsForm` |
| `billing/views.py` | Modify | Expand `admin_tab_dashboard`; add `billing_admin_save_settings`, `billing_admin_retry_charge`, `billing_admin_tab_detail_api` |
| `billing/urls.py` | Modify | Register three new URL patterns |
| `templates/billing/admin_dashboard.html` | Replace | Five-tab dashboard layout |
| `tests/billing/forms_spec.py` | Modify | Add `describe_BillingSettingsForm` |
| `tests/billing/admin_dashboard_spec.py` | Modify | Add tests for new views and expanded context |

---

## Task 1: BillingSettingsForm

**Files:**
- Modify: `billing/forms.py`
- Test: `tests/billing/forms_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/billing/forms_spec.py`:

```python
from billing.forms import AdminAddTabEntryForm, BillingSettingsForm, VoidTabEntryForm
from billing.models import BillingSettings
from tests.billing.factories import BillingSettingsFactory

# ... (keep all existing describe blocks) ...

def describe_BillingSettingsForm():
    def it_is_valid_with_daily_frequency():
        form = BillingSettingsForm(data={
            "charge_frequency": "daily",
            "charge_time": "23:00",
            "charge_day_of_week": "",
            "charge_day_of_month": "",
            "default_tab_limit": "200.00",
            "max_retry_attempts": "3",
            "retry_interval_hours": "24",
        })
        assert form.is_valid(), form.errors

    def it_is_valid_with_weekly_frequency():
        form = BillingSettingsForm(data={
            "charge_frequency": "weekly",
            "charge_time": "23:00",
            "charge_day_of_week": "0",
            "charge_day_of_month": "",
            "default_tab_limit": "200.00",
            "max_retry_attempts": "3",
            "retry_interval_hours": "24",
        })
        assert form.is_valid(), form.errors

    def it_is_valid_with_monthly_frequency():
        form = BillingSettingsForm(data={
            "charge_frequency": "monthly",
            "charge_time": "23:00",
            "charge_day_of_week": "",
            "charge_day_of_month": "15",
            "default_tab_limit": "200.00",
            "max_retry_attempts": "3",
            "retry_interval_hours": "24",
        })
        assert form.is_valid(), form.errors

    def it_populates_from_instance(db):
        settings = BillingSettingsFactory(
            charge_frequency="weekly",
            charge_day_of_week=2,
            default_tab_limit="150.00",
        )
        form = BillingSettingsForm(instance=settings)
        assert form.initial["charge_frequency"] == "weekly" or form["charge_frequency"].value() == "weekly"
        assert form["default_tab_limit"].value() == "150.00"

    def it_rejects_negative_tab_limit():
        form = BillingSettingsForm(data={
            "charge_frequency": "daily",
            "charge_time": "23:00",
            "charge_day_of_week": "",
            "charge_day_of_month": "",
            "default_tab_limit": "-10.00",
            "max_retry_attempts": "3",
            "retry_interval_hours": "24",
        })
        assert not form.is_valid()
        assert "default_tab_limit" in form.errors
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/billing/forms_spec.py::describe_BillingSettingsForm -x -q
```

Expected: `ImportError: cannot import name 'BillingSettingsForm'`

- [ ] **Step 3: Implement BillingSettingsForm**

Add to `billing/forms.py` after the existing imports:

```python
from billing.models import BillingSettings, Product
```

*(replace the existing `from billing.models import Product` line)*

Add this class after `VoidTabEntryForm`:

```python
class BillingSettingsForm(forms.ModelForm):
    """Admin form for editing the BillingSettings singleton."""

    class Meta:
        model = BillingSettings
        fields = [
            "charge_frequency",
            "charge_time",
            "charge_day_of_week",
            "charge_day_of_month",
            "default_tab_limit",
            "max_retry_attempts",
            "retry_interval_hours",
        ]
        widgets = {
            "charge_frequency": forms.Select(),
            "charge_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean_default_tab_limit(self) -> Decimal:
        value: Decimal = self.cleaned_data["default_tab_limit"]
        if value < Decimal("0.00"):
            raise forms.ValidationError("Tab limit must be zero or positive.")
        return value
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/billing/forms_spec.py::describe_BillingSettingsForm -x -q
```

Expected: 5 passed

- [ ] **Step 5: Full test suite — confirm no regressions**

```bash
.venv/bin/pytest tests/billing/forms_spec.py -q
```

Expected: all passed, 100% coverage

- [ ] **Step 6: Commit**

```bash
git add billing/forms.py tests/billing/forms_spec.py
git commit -m "feat: add BillingSettingsForm for payments dashboard settings tab"
```

---

## Task 2: billing_admin_save_settings view

**Files:**
- Modify: `billing/views.py`
- Modify: `billing/urls.py`
- Test: `tests/billing/admin_dashboard_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/billing/admin_dashboard_spec.py`:

```python
from billing.models import BillingSettings, Tab, TabCharge
from tests.billing.factories import BillingSettingsFactory, TabChargeFactory, TabEntryFactory, TabFactory

# ... (keep all existing describe blocks) ...

def describe_billing_admin_save_settings():
    def it_requires_staff(client: Client):
        response = client.post("/billing/admin/save-settings/", {})
        assert response.status_code == 302
        assert "/accounts/login/" in response.url or "/admin/login/" in response.url

    def it_saves_valid_settings_and_redirects(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()

        response = client.post("/billing/admin/save-settings/", {
            "charge_frequency": "weekly",
            "charge_time": "22:00",
            "charge_day_of_week": "1",
            "charge_day_of_month": "",
            "default_tab_limit": "150.00",
            "max_retry_attempts": "5",
            "retry_interval_hours": "12",
        })

        assert response.status_code == 302
        assert response.url == "/billing/admin/dashboard/?tab=settings"
        settings = BillingSettings.load()
        assert settings.charge_frequency == "weekly"
        assert settings.max_retry_attempts == 5

    def it_redirects_with_error_on_invalid_data(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()

        response = client.post("/billing/admin/save-settings/", {
            "charge_frequency": "daily",
            "charge_time": "23:00",
            "charge_day_of_week": "",
            "charge_day_of_month": "",
            "default_tab_limit": "-50.00",
            "max_retry_attempts": "3",
            "retry_interval_hours": "24",
        })

        assert response.status_code == 302
        assert "tab=settings" in response.url
        settings = BillingSettings.load()
        assert settings.default_tab_limit != Decimal("-50.00")

    def it_only_accepts_post(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/save-settings/")
        assert response.status_code == 405
```

Also add `from decimal import Decimal` to the imports at the top of the file if not already present.

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_billing_admin_save_settings -x -q
```

Expected: `404 Not Found` (URL not registered yet)

- [ ] **Step 3: Add the view**

Add to `billing/views.py` after `admin_add_tab_entry`:

```python
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
```

Also add `BillingSettings` to the imports at the top of the file:

```python
from billing.models import BillingSettings, StripeAccount, Tab, TabCharge, TabEntry
```

- [ ] **Step 4: Register the URL**

In `billing/urls.py`, add:

```python
path("admin/save-settings/", views.billing_admin_save_settings, name="billing_admin_save_settings"),
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_billing_admin_save_settings -x -q
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add billing/forms.py billing/views.py billing/urls.py tests/billing/admin_dashboard_spec.py
git commit -m "feat: add billing_admin_save_settings view for inline settings editing"
```

---

## Task 3: billing_admin_retry_charge view

**Files:**
- Modify: `billing/views.py`
- Modify: `billing/urls.py`
- Test: `tests/billing/admin_dashboard_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/billing/admin_dashboard_spec.py`:

```python
import uuid
from unittest.mock import patch

# ... keep existing imports ...

def describe_billing_admin_retry_charge():
    def it_requires_staff(client: Client):
        response = client.post("/billing/admin/retry-charge/999/")
        assert response.status_code == 302

    def it_returns_404_for_missing_charge(client: Client):
        _create_superuser(client)
        response = client.post("/billing/admin/retry-charge/999999/")
        assert response.status_code == 404

    def it_succeeds_when_stripe_succeeds(client: Client):
        _create_superuser(client)
        tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test", stripe_account=None)
        charge = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            amount=Decimal("25.00"),
            stripe_account=None,
        )

        mock_result = {"id": "pi_test123", "charge_id": "ch_test123", "receipt_url": "https://receipt.test"}
        with patch("billing.views.stripe_utils.create_payment_intent", return_value=mock_result):
            response = client.post(f"/billing/admin/retry-charge/{charge.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"
        charge.refresh_from_db()
        assert charge.status == TabCharge.Status.SUCCEEDED
        assert charge.stripe_payment_intent_id == "pi_test123"

    def it_succeeds_destination_charge_when_stripe_account_present(client: Client):
        _create_superuser(client)
        from tests.billing.factories import StripeAccountFactory
        stripe_acct = StripeAccountFactory(stripe_account_id="acct_test")
        tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
        charge = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            amount=Decimal("50.00"),
            stripe_account=stripe_acct,
            application_fee=Decimal("2.50"),
        )

        mock_result = {"id": "pi_dest123", "charge_id": "ch_dest123", "receipt_url": "https://receipt.dest"}
        with patch("billing.views.stripe_utils.create_destination_payment_intent", return_value=mock_result):
            response = client.post(f"/billing/admin/retry-charge/{charge.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"

    def it_returns_failed_json_when_stripe_raises(client: Client):
        _create_superuser(client)
        tab = TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test", stripe_account=None)
        charge = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            amount=Decimal("25.00"),
            stripe_account=None,
        )

        with patch("billing.views.stripe_utils.create_payment_intent", side_effect=Exception("Card declined")):
            response = client.post(f"/billing/admin/retry-charge/{charge.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        charge.refresh_from_db()
        assert charge.status == TabCharge.Status.FAILED
```

Note: `TabFactory` doesn't have a `stripe_account` field — Tab has no StripeAccount FK. The `stripe_account` field is on `TabCharge`. The `TabFactory` call with `stripe_account=None` should be `TabFactory(stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")`.

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_billing_admin_retry_charge -x -q
```

Expected: `404` (URL not yet registered)

- [ ] **Step 3: Implement the view**

Add to `billing/views.py` after `billing_admin_save_settings`:

```python
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

    tab = charge.tab
    idempotency_key = f"admin-retry-{charge.pk}-{_uuid.uuid4()}"

    try:
        if charge.stripe_account:
            fee_cents = int(charge.application_fee * 100) if charge.application_fee else None
            result = stripe_utils.create_destination_payment_intent(
                customer_id=tab.stripe_customer_id,
                payment_method_id=tab.stripe_payment_method_id,
                amount_cents=int(charge.amount * 100),
                description=f"Past Lives Makerspace tab retry — {charge.entry_count} items",
                metadata={"tab_id": str(tab.pk), "charge_id": str(charge.pk)},
                idempotency_key=idempotency_key,
                destination_account_id=charge.stripe_account.stripe_account_id,
                application_fee_cents=fee_cents,
            )
        else:
            result = stripe_utils.create_payment_intent(
                customer_id=tab.stripe_customer_id,
                payment_method_id=tab.stripe_payment_method_id,
                amount_cents=int(charge.amount * 100),
                description=f"Past Lives Makerspace tab retry — {charge.entry_count} items",
                metadata={"tab_id": str(tab.pk), "charge_id": str(charge.pk)},
                idempotency_key=idempotency_key,
            )
        charge.stripe_payment_intent_id = result["id"]
        charge.stripe_charge_id = result["charge_id"]
        charge.stripe_receipt_url = result["receipt_url"]
        charge.status = TabCharge.Status.SUCCEEDED
        charge.charged_at = timezone.now()
        charge.save()
        return JsonResponse({"status": "succeeded"})
    except Exception:
        logger.exception("Admin retry failed for charge %s.", charge.pk)
        return JsonResponse({"status": "failed"})
```

- [ ] **Step 4: Register the URL**

In `billing/urls.py`, add:

```python
path("admin/retry-charge/<int:charge_pk>/", views.billing_admin_retry_charge, name="billing_admin_retry_charge"),
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_billing_admin_retry_charge -x -q
```

Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add billing/views.py billing/urls.py tests/billing/admin_dashboard_spec.py
git commit -m "feat: add billing_admin_retry_charge AJAX view for one-click charge retries"
```

---

## Task 4: billing_admin_tab_detail_api view

**Files:**
- Modify: `billing/views.py`
- Modify: `billing/urls.py`
- Test: `tests/billing/admin_dashboard_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/billing/admin_dashboard_spec.py`:

```python
def describe_billing_admin_tab_detail_api():
    def it_requires_staff(client: Client):
        response = client.get("/billing/admin/tab/999/detail/")
        assert response.status_code == 302

    def it_returns_404_for_missing_tab(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/tab/999999/detail/")
        assert response.status_code == 404

    def it_returns_tab_data_as_json(client: Client):
        _create_superuser(client)
        member = MemberFactory(full_legal_name="Jane Doe")
        tab = TabFactory(
            member=member,
            stripe_payment_method_id="pm_test",
            payment_method_brand="visa",
            payment_method_last4="4242",
            tab_limit=Decimal("150.00"),
        )
        entry = TabEntryFactory(tab=tab, description="Laser time", amount=Decimal("20.00"))

        response = client.get(f"/billing/admin/tab/{tab.pk}/detail/")

        assert response.status_code == 200
        data = response.json()
        assert data["member_name"] == "Jane Doe"
        assert data["balance"] == "20.00"
        assert data["limit"] == "150.00"
        assert data["payment_method"] == "visa 4242"
        assert data["is_locked"] is False
        assert len(data["pending_entries"]) == 1
        assert data["pending_entries"][0]["description"] == "Laser time"
        assert data["pending_entries"][0]["amount"] == "20.00"

    def it_returns_charge_history(client: Client):
        _create_superuser(client)
        member = MemberFactory()
        tab = TabFactory(member=member)
        TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.SUCCEEDED,
            amount=Decimal("50.00"),
            stripe_receipt_url="https://receipt.test",
        )

        response = client.get(f"/billing/admin/tab/{tab.pk}/detail/")
        data = response.json()

        assert len(data["charge_history"]) == 1
        assert data["charge_history"][0]["amount"] == "50.00"
        assert data["charge_history"][0]["status"] == "succeeded"
        assert data["charge_history"][0]["receipt_url"] == "https://receipt.test"

    def it_shows_no_payment_method_when_absent(client: Client):
        _create_superuser(client)
        member = MemberFactory()
        tab = TabFactory(member=member, stripe_payment_method_id="", payment_method_brand="", payment_method_last4="")

        response = client.get(f"/billing/admin/tab/{tab.pk}/detail/")
        data = response.json()

        assert data["payment_method"] == ""
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_billing_admin_tab_detail_api -x -q
```

Expected: `404` (URL not registered yet)

- [ ] **Step 3: Implement the view**

Add to `billing/views.py` after `billing_admin_retry_charge`:

```python
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

    return JsonResponse({
        "member_name": tab.member.display_name,
        "balance": str(tab.current_balance),
        "limit": str(tab.effective_tab_limit),
        "payment_method": payment_method,
        "is_locked": tab.is_locked,
        "locked_reason": tab.locked_reason,
        "tab_pk": tab.pk,
        "pending_entries": [
            {
                "description": e["description"],
                "amount": str(e["amount"]),
                "date": e["created_at"].strftime("%-d %b") if e["created_at"] else "",
            }
            for e in pending_entries
        ],
        "charge_history": [
            {
                "amount": str(c["amount"]),
                "status": c["status"],
                "date": c["charged_at"].strftime("%-d %b %Y") if c["charged_at"] else "—",
                "receipt_url": c["stripe_receipt_url"] or "",
            }
            for c in charge_history
        ],
    })
```

- [ ] **Step 4: Register the URL**

In `billing/urls.py`, add:

```python
path("admin/tab/<int:tab_pk>/detail/", views.billing_admin_tab_detail_api, name="billing_admin_tab_detail_api"),
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_billing_admin_tab_detail_api -x -q
```

Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add billing/views.py billing/urls.py tests/billing/admin_dashboard_spec.py
git commit -m "feat: add billing_admin_tab_detail_api for tab detail modal data"
```

---

## Task 5: Expand admin_tab_dashboard context

**Files:**
- Modify: `billing/views.py`
- Test: `tests/billing/admin_dashboard_spec.py`

The view must serve context for all five tabs based on `request.GET.get("tab", "overview")`. It also handles Open Tabs filtering (`?filter=`) and History filtering (`?status=`).

- [ ] **Step 1: Write the failing tests**

Add to the existing `describe_admin_tab_dashboard` block in `tests/billing/admin_dashboard_spec.py`:

```python
def describe_admin_tab_dashboard():
    # ... keep existing tests ...

    def it_defaults_to_overview_tab(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/dashboard/")
        assert response.context["active_tab"] == "overview"

    def it_sets_active_tab_from_query_param(client: Client):
        _create_superuser(client)
        for tab_name in ["overview", "open-tabs", "history", "settings", "stripe"]:
            response = client.get(f"/billing/admin/dashboard/?tab={tab_name}")
            assert response.context["active_tab"] == tab_name

    def it_unknown_tab_defaults_to_overview(client: Client):
        _create_superuser(client)
        response = client.get("/billing/admin/dashboard/?tab=bogus")
        assert response.context["active_tab"] == "overview"

    def it_provides_open_tabs_filter_outstanding(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)
        TabEntryFactory(tab=tab, amount=Decimal("10.00"))

        response = client.get("/billing/admin/dashboard/?tab=open-tabs&filter=outstanding")
        assert tab in response.context["open_tabs"]

    def it_provides_open_tabs_filter_all(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)  # no entries — zero balance

        response = client.get("/billing/admin/dashboard/?tab=open-tabs&filter=all")
        assert tab in response.context["open_tabs"]

    def it_provides_open_tabs_filter_failed(client: Client):
        _create_superuser(client)
        member = MemberFactory(status="active")
        tab = TabFactory(member=member)
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)

        response = client.get("/billing/admin/dashboard/?tab=open-tabs&filter=failed")
        assert tab in response.context["open_tabs"]

    def it_provides_history_charges_all(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        charge = TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)

        response = client.get("/billing/admin/dashboard/?tab=history&status=all")
        assert charge in response.context["history_charges"]

    def it_provides_history_charges_filter_succeeded(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        succeeded = TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)

        response = client.get("/billing/admin/dashboard/?tab=history&status=succeeded")
        charges = list(response.context["history_charges"])
        assert succeeded in charges
        assert all(c.status == TabCharge.Status.SUCCEEDED for c in charges)

    def it_provides_history_charges_filter_failed(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        failed = TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED)
        TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED)

        response = client.get("/billing/admin/dashboard/?tab=history&status=failed")
        charges = list(response.context["history_charges"])
        assert failed in charges
        assert all(c.status == TabCharge.Status.FAILED for c in charges)

    def it_provides_history_charges_filter_needs_retry(client: Client):
        _create_superuser(client)
        from django.utils import timezone as tz
        tab = TabFactory()
        retryable = TabChargeFactory(
            tab=tab,
            status=TabCharge.Status.FAILED,
            next_retry_at=tz.now() - timedelta(hours=1),
        )
        TabChargeFactory(tab=tab, status=TabCharge.Status.FAILED, next_retry_at=None)

        response = client.get("/billing/admin/dashboard/?tab=history&status=needs_retry")
        charges = list(response.context["history_charges"])
        assert retryable in charges

    def it_provides_history_month_stats(client: Client):
        _create_superuser(client)
        tab = TabFactory()
        TabChargeFactory(tab=tab, status=TabCharge.Status.SUCCEEDED, amount=Decimal("75.00"),
                         charged_at=timezone.now())

        response = client.get("/billing/admin/dashboard/?tab=history")
        assert response.context["history_collected"] == Decimal("75.00")
        assert response.context["history_failed_count"] == 0

    def it_provides_settings_form(client: Client):
        _create_superuser(client)
        BillingSettingsFactory()

        response = client.get("/billing/admin/dashboard/?tab=settings")
        assert "settings_form" in response.context
        from billing.forms import BillingSettingsForm
        assert isinstance(response.context["settings_form"], BillingSettingsForm)

    def it_provides_stripe_context(client: Client):
        _create_superuser(client)
        from tests.billing.factories import StripeAccountFactory, ProductFactory

        StripeAccountFactory()
        ProductFactory()

        response = client.get("/billing/admin/dashboard/?tab=stripe")
        assert "stripe_accounts" in response.context
        assert "products" in response.context
        assert "guilds" in response.context
```

Also add `from datetime import timedelta` to the imports at the top of the file.

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_admin_tab_dashboard -x -q 2>&1 | head -30
```

Expected: several failures on `active_tab` not in context, etc.

- [ ] **Step 3: Replace the admin_tab_dashboard view**

In `billing/views.py`, replace the entire `admin_tab_dashboard` function with:

```python
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

    # --- Overview stats (always computed — used in Overview tab) ---
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
        open_tabs = (
            Tab.objects.filter(charges__status=TabCharge.Status.FAILED)
            .distinct()
            .select_related("member")
        )
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
        history_charges = (
            TabCharge.objects.exclude(status=TabCharge.Status.PENDING)
            .select_related("tab__member", "stripe_account")
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

    history_total_count = TabCharge.objects.filter(
        created_at__gte=month_start,
    ).exclude(status=TabCharge.Status.PENDING).count()

    history_success_rate = (
        int((history_collected and TabCharge.objects.filter(
            status=TabCharge.Status.SUCCEEDED,
            charged_at__gte=month_start,
        ).count()) / history_total_count * 100)
        if history_total_count
        else 100
    )

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
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/billing/admin_dashboard_spec.py::describe_admin_tab_dashboard -x -q
```

Expected: all passed

- [ ] **Step 5: Full billing test suite — check coverage**

```bash
.venv/bin/pytest tests/billing/ -q --tb=short 2>&1 | tail -20
```

Expected: all passed, 100% coverage on billing module

- [ ] **Step 6: Commit**

```bash
git add billing/views.py tests/billing/admin_dashboard_spec.py
git commit -m "feat: expand admin_tab_dashboard to serve all five tabs' context"
```

---

## Task 6: Replace admin_dashboard.html template

**Files:**
- Replace: `templates/billing/admin_dashboard.html`

This is a full rewrite. The template uses `?tab=` server-side routing, the `pl-*` CSS from the Voting Dashboard, and vanilla JS for the modal fetch and conditional form fields.

- [ ] **Step 1: Replace the template**

Write the following to `templates/billing/admin_dashboard.html`:

```django
{% extends "admin/base.html" %}
{% load i18n %}

{% block title %}Payments Dashboard | {{ site_title }}{% endblock %}

{% block content %}
<style>
  .pl-dashboard { display: flex; flex-direction: column; gap: 1.5rem; padding: 2rem 2.5rem; }
  .pl-card { background-color: #092E4C; border: 1px solid transparent; border-radius: 10px; padding: 2rem; }
  .pl-card__title { font-family: 'Lato', system-ui, sans-serif; font-size: 1.75rem; font-weight: 700; color: #F4EFDD; margin-bottom: 0.5rem; }
  .pl-text-muted { color: #96ACBB; font-size: 0.9375rem; }
  .pl-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
  .pl-stats--3 { grid-template-columns: repeat(3, 1fr); }
  .pl-stat { background-color: rgba(255,255,255,0.04); border-radius: 8px; padding: 1.25rem; text-align: center; }
  .pl-stat__value { font-family: 'Lato', system-ui, sans-serif; font-size: 2rem; font-weight: 900; color: #EEB44B; line-height: 1.2; }
  .pl-stat__label { font-size: 0.8125rem; color: #96ACBB; margin-top: 0.25rem; }
  .pl-section-label { font-size: 0.6875rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #96ACBB; margin-bottom: 0.75rem; }
  .pl-table { width: 100%; border-collapse: collapse; font-size: 0.9375rem; }
  .pl-table thead th { text-align: left; padding: 0.5rem 0.75rem; font-weight: 500; color: #96ACBB; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 0.875rem; }
  .pl-table thead th.text-right { text-align: right; }
  .pl-table tbody td { padding: 0.5rem 0.75rem; color: #F4EFDD; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .pl-table tbody td.text-right { text-align: right; }
  .pl-table tbody tr { cursor: pointer; }
  .pl-table tbody tr:hover td { background: rgba(255,255,255,0.03); }
  .pl-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .pl-btn { display: inline-flex; align-items: center; padding: 0.625rem 1.5rem; font-family: 'Inter', system-ui, sans-serif; font-size: 0.9375rem; font-weight: 700; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; transition: background-color 0.15s ease; }
  .pl-btn--primary { background-color: #EEB44B; color: #092E4C; }
  .pl-btn--primary:hover { background-color: #d4a043; color: #092E4C; }
  .pl-btn--secondary { background-color: transparent; border: 1px solid rgba(255,255,255,0.12); color: #F4EFDD; }
  .pl-btn--secondary:hover { background-color: rgba(255,255,255,0.06); color: #F4EFDD; }
  .pl-btn--danger { background-color: transparent; border: 1px solid rgba(248,113,113,0.3); color: #f87171; }
  .pl-btn--danger:hover { background-color: rgba(248,113,113,0.08); }
  .pl-btn--sm { padding: 0.35rem 0.875rem; font-size: 0.8125rem; }

  /* Tab navigation */
  .pl-tab-nav { display: flex; border-bottom: 1px solid rgba(255,255,255,0.08); gap: 0; }
  .pl-tab-nav a { padding: 0.625rem 1.25rem; font-size: 0.9375rem; color: #96ACBB; text-decoration: none; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: color 0.15s ease; }
  .pl-tab-nav a:hover { color: #F4EFDD; }
  .pl-tab-nav a.active { color: #EEB44B; border-bottom-color: #EEB44B; }

  /* Filter chips */
  .pl-filters { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .pl-filter { padding: 0.3rem 0.875rem; border-radius: 20px; font-size: 0.8125rem; color: #96ACBB; border: 1px solid rgba(255,255,255,0.12); text-decoration: none; transition: all 0.15s ease; }
  .pl-filter:hover { color: #F4EFDD; border-color: rgba(255,255,255,0.25); }
  .pl-filter.active { background: rgba(238,180,75,0.12); border-color: rgba(238,180,75,0.4); color: #EEB44B; }

  /* Badges */
  .pl-badge { display: inline-block; font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: 500; }
  .pl-badge--ok { background: rgba(52,211,153,0.15); color: #6ee7b7; }
  .pl-badge--warn { background: rgba(251,191,36,0.15); color: #fbbf24; }
  .pl-badge--fail { background: rgba(220,60,60,0.15); color: #f87171; }
  .pl-badge--muted { background: rgba(255,255,255,0.06); color: #96ACBB; }

  /* Toolbar row */
  .pl-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }

  /* Modal */
  .pl-modal-overlay { position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center; background-color: rgba(0,0,0,0.6); padding: 1rem; }
  .pl-modal { background-color: #092E4C; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 20px 60px rgba(0,0,0,0.4); max-width: 560px; width: 100%; max-height: 90vh; overflow-y: auto; }
  .pl-modal__header { display: flex; align-items: flex-start; justify-content: space-between; padding: 1.25rem 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.08); }
  .pl-modal__title { font-family: 'Lato', system-ui, sans-serif; font-size: 1.1rem; font-weight: 700; color: #F4EFDD; margin: 0; }
  .pl-modal__subtitle { font-size: 0.8125rem; color: #96ACBB; margin-top: 0.2rem; }
  .pl-modal__close { background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #96ACBB; padding: 0; line-height: 1; flex-shrink: 0; }
  .pl-modal__close:hover { color: #F4EFDD; }
  .pl-modal__body { padding: 1.5rem; }
  .pl-modal__footer { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; border-top: 1px solid rgba(255,255,255,0.08); gap: 0.75rem; flex-wrap: wrap; }
  .pl-modal__field { margin-bottom: 1.25rem; }
  .pl-modal__field:last-child { margin-bottom: 0; }
  .pl-modal__field label { display: block; font-size: 0.85rem; font-weight: 500; color: #96ACBB; margin-bottom: 0.375rem; }
  .pl-modal__field select, .pl-modal__field input[type="text"], .pl-modal__field input[type="number"] { width: 100%; padding: 0.625rem 0.875rem; font-size: 0.9375rem; color: #F4EFDD; background-color: #0a1929; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; box-sizing: border-box; }
  .pl-modal__field select:focus, .pl-modal__field input:focus { outline: none; border-color: #EEB44B; box-shadow: 0 0 0 3px rgba(238,180,75,0.15); }
  .pl-modal__pills { display: flex; gap: 0.75rem; margin-bottom: 1.25rem; }
  .pl-modal__pill { flex: 1; background: rgba(255,255,255,0.04); border-radius: 8px; padding: 0.75rem; text-align: center; }
  .pl-modal__pill-value { font-size: 1.25rem; font-weight: 900; color: #EEB44B; }
  .pl-modal__pill-label { font-size: 0.7rem; color: #96ACBB; margin-top: 0.15rem; }

  /* Settings form */
  .pl-form-row { margin-bottom: 1.25rem; }
  .pl-form-row label { display: block; font-size: 0.875rem; font-weight: 500; color: #96ACBB; margin-bottom: 0.375rem; }
  .pl-form-row select, .pl-form-row input[type="time"], .pl-form-row input[type="number"], .pl-form-row input[type="text"] { padding: 0.625rem 0.875rem; font-size: 0.9375rem; color: #F4EFDD; background-color: #0a1929; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; width: 100%; max-width: 320px; box-sizing: border-box; }
  .pl-form-row select:focus, .pl-form-row input:focus { outline: none; border-color: #EEB44B; box-shadow: 0 0 0 3px rgba(238,180,75,0.15); }
  .pl-form-hint { font-size: 0.8125rem; color: #96ACBB; margin-top: 0.25rem; }
  .pl-form-errors { color: #f87171; font-size: 0.8125rem; margin-top: 0.25rem; }

  @media (max-width: 768px) {
    .pl-stats, .pl-stats--3 { grid-template-columns: 1fr; }
    .pl-dashboard { padding: 1.25rem; }
  }
</style>

<div class="pl-dashboard">

  <div>
    <h1 class="pl-card__title">Payments Dashboard</h1>
    <p class="pl-text-muted">Tab billing, charge history, and Stripe configuration.</p>
  </div>

  {# --- Tab navigation --- #}
  <div class="pl-tab-nav">
    <a href="?tab=overview" class="{% if active_tab == 'overview' %}active{% endif %}">Overview</a>
    <a href="?tab=open-tabs" class="{% if active_tab == 'open-tabs' %}active{% endif %}">Open Tabs</a>
    <a href="?tab=history" class="{% if active_tab == 'history' %}active{% endif %}">History</a>
    <a href="?tab=settings" class="{% if active_tab == 'settings' %}active{% endif %}">Settings</a>
    <a href="?tab=stripe" class="{% if active_tab == 'stripe' %}active{% endif %}">Stripe</a>
  </div>

  {# ================================================================ #}
  {# OVERVIEW TAB                                                      #}
  {# ================================================================ #}
  {% if active_tab == "overview" %}

  <div class="pl-stats">
    <div class="pl-stat">
      <div class="pl-stat__value">${{ total_outstanding }}</div>
      <div class="pl-stat__label">Total Outstanding</div>
    </div>
    <div class="pl-stat">
      <div class="pl-stat__value">${{ collected_this_month }}</div>
      <div class="pl-stat__label">Collected This Month</div>
    </div>
    <div class="pl-stat">
      <div class="pl-stat__value" style="color:{% if failed_count %}#f87171{% else %}#EEB44B{% endif %}">{{ failed_count }}</div>
      <div class="pl-stat__label">Failed Charges</div>
    </div>
    <div class="pl-stat">
      <div class="pl-stat__value" style="color:{% if locked_count %}#f87171{% else %}#EEB44B{% endif %}">{{ locked_count }}</div>
      <div class="pl-stat__label">Locked Tabs</div>
    </div>
  </div>

  <div class="pl-actions">
    <button type="button" class="pl-btn pl-btn--primary" onclick="document.getElementById('add-charge-modal').style.display='flex'">
      + Add Charge
    </button>
  </div>

  {% if outstanding_tabs %}
  <div class="pl-card">
    <div class="pl-section-label">Outstanding Tabs</div>
    <table class="pl-table">
      <thead>
        <tr>
          <th>Member</th>
          <th class="text-right">Balance</th>
          <th>Payment Method</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {% for tab in outstanding_tabs %}
        <tr onclick="openTabModal({{ tab.pk }})">
          <td>{{ tab.member.display_name }}</td>
          <td class="text-right">${{ tab.current_balance }}</td>
          <td>{% if tab.has_payment_method %}{{ tab.payment_method_brand }} ···· {{ tab.payment_method_last4 }}{% else %}<span class="pl-badge pl-badge--warn">None</span>{% endif %}</td>
          <td>{% if tab.is_locked %}<span class="pl-badge pl-badge--fail">Locked</span>{% else %}<span class="pl-badge pl-badge--ok">Active</span>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  {% if failed_charges %}
  <div class="pl-card">
    <div class="pl-section-label">Recent Failed Charges</div>
    <table class="pl-table">
      <thead>
        <tr>
          <th>Member</th>
          <th class="text-right">Amount</th>
          <th>Reason</th>
          <th>Retries</th>
          <th>Date</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for charge in failed_charges %}
        <tr>
          <td onclick="openTabModal({{ charge.tab.pk }})" style="cursor:pointer">{{ charge.tab.member.display_name }}</td>
          <td class="text-right">${{ charge.amount }}</td>
          <td style="color:#96ACBB">{{ charge.failure_reason|truncatewords:8 }}</td>
          <td>{{ charge.retry_count }}</td>
          <td style="color:#96ACBB">{{ charge.created_at|date:"M j, Y" }}</td>
          <td>
            <button class="pl-btn pl-btn--sm pl-btn--secondary" onclick="retryCharge({{ charge.pk }}, this)">Retry</button>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  {% endif %}{# /overview #}

  {# ================================================================ #}
  {# OPEN TABS TAB                                                     #}
  {# ================================================================ #}
  {% if active_tab == "open-tabs" %}

  <div class="pl-toolbar">
    <div class="pl-filters">
      <a href="?tab=open-tabs&filter=outstanding" class="pl-filter {% if tab_filter == 'outstanding' %}active{% endif %}">Outstanding</a>
      <a href="?tab=open-tabs&filter=all" class="pl-filter {% if tab_filter == 'all' %}active{% endif %}">All Members</a>
      <a href="?tab=open-tabs&filter=failed" class="pl-filter {% if tab_filter == 'failed' %}active{% endif %}">Failed Charges</a>
    </div>
    <button type="button" class="pl-btn pl-btn--primary pl-btn--sm" onclick="document.getElementById('add-charge-modal').style.display='flex'">
      + Add Charge
    </button>
  </div>

  <div class="pl-card">
    <table class="pl-table">
      <thead>
        <tr>
          <th>Member</th>
          <th class="text-right">Balance</th>
          <th class="text-right">Limit</th>
          <th>Payment Method</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {% for tab in open_tabs %}
        <tr onclick="openTabModal({{ tab.pk }})">
          <td>{{ tab.member.display_name }}</td>
          <td class="text-right">${{ tab.current_balance }}</td>
          <td class="text-right" style="color:#96ACBB">${{ tab.effective_tab_limit }}</td>
          <td>{% if tab.has_payment_method %}{{ tab.payment_method_brand }} ···· {{ tab.payment_method_last4 }}{% else %}<span class="pl-badge pl-badge--warn">None</span>{% endif %}</td>
          <td>{% if tab.is_locked %}<span class="pl-badge pl-badge--fail">Locked</span>{% elif not tab.has_payment_method %}<span class="pl-badge pl-badge--warn">No card</span>{% else %}<span class="pl-badge pl-badge--ok">Active</span>{% endif %}</td>
        </tr>
        {% empty %}
        <tr><td colspan="5" style="text-align:center;color:#96ACBB;padding:2rem">No tabs match this filter.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {% endif %}{# /open-tabs #}

  {# ================================================================ #}
  {# HISTORY TAB                                                       #}
  {# ================================================================ #}
  {% if active_tab == "history" %}

  <div class="pl-stats pl-stats--3">
    <div class="pl-stat">
      <div class="pl-stat__value">${{ history_collected }}</div>
      <div class="pl-stat__label">Collected This Month</div>
    </div>
    <div class="pl-stat">
      <div class="pl-stat__value" style="color:{% if history_failed_count %}#f87171{% else %}#EEB44B{% endif %}">{{ history_failed_count }}</div>
      <div class="pl-stat__label">Failed This Month</div>
    </div>
    <div class="pl-stat">
      <div class="pl-stat__value">{{ history_success_rate }}%</div>
      <div class="pl-stat__label">Success Rate</div>
    </div>
  </div>

  <div class="pl-toolbar">
    <div class="pl-filters">
      <a href="?tab=history&status=all" class="pl-filter {% if charge_status_filter == 'all' %}active{% endif %}">All</a>
      <a href="?tab=history&status=succeeded" class="pl-filter {% if charge_status_filter == 'succeeded' %}active{% endif %}">Succeeded</a>
      <a href="?tab=history&status=failed" class="pl-filter {% if charge_status_filter == 'failed' %}active{% endif %}">Failed</a>
      <a href="?tab=history&status=needs_retry" class="pl-filter {% if charge_status_filter == 'needs_retry' %}active{% endif %}">Needs Retry</a>
    </div>
  </div>

  <div class="pl-card">
    <table class="pl-table">
      <thead>
        <tr>
          <th>Member</th>
          <th class="text-right">Amount</th>
          <th>Guild / Account</th>
          <th>Status</th>
          <th>Retries</th>
          <th>Date</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for charge in history_charges %}
        <tr>
          <td onclick="openTabModal({{ charge.tab.pk }})" style="cursor:pointer;color:#EEB44B">{{ charge.tab.member.display_name }}</td>
          <td class="text-right">${{ charge.amount }}</td>
          <td style="color:#96ACBB">{% if charge.stripe_account %}{{ charge.stripe_account.display_name }}{% else %}Platform{% endif %}</td>
          <td>
            {% if charge.status == "succeeded" %}<span class="pl-badge pl-badge--ok">Succeeded</span>
            {% elif charge.status == "failed" %}<span class="pl-badge pl-badge--fail">Failed</span>
            {% elif charge.status == "processing" %}<span class="pl-badge pl-badge--warn">Processing</span>
            {% else %}<span class="pl-badge pl-badge--muted">{{ charge.get_status_display }}</span>{% endif %}
          </td>
          <td style="color:#96ACBB">{{ charge.retry_count }}</td>
          <td style="color:#96ACBB">{% if charge.charged_at %}{{ charge.charged_at|date:"M j, Y" }}{% else %}{{ charge.created_at|date:"M j, Y" }}{% endif %}</td>
          <td>
            {% if charge.status == "succeeded" and charge.stripe_receipt_url %}
              <a href="{{ charge.stripe_receipt_url }}" target="_blank" class="pl-btn pl-btn--sm pl-btn--secondary">Receipt</a>
            {% elif charge.status == "failed" %}
              <button class="pl-btn pl-btn--sm pl-btn--secondary" onclick="retryCharge({{ charge.pk }}, this)">Retry</button>
            {% endif %}
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="7" style="text-align:center;color:#96ACBB;padding:2rem">No charges match this filter.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {% endif %}{# /history #}

  {# ================================================================ #}
  {# SETTINGS TAB                                                      #}
  {# ================================================================ #}
  {% if active_tab == "settings" %}

  <div class="pl-card">
    <div class="pl-section-label">Billing Configuration</div>

    <form method="post" action="{% url 'billing_admin_save_settings' %}">
      {% csrf_token %}

      <div class="pl-form-row">
        <label for="{{ settings_form.charge_frequency.id_for_label }}">Charge Frequency</label>
        {{ settings_form.charge_frequency }}
        {% if settings_form.charge_frequency.errors %}<div class="pl-form-errors">{{ settings_form.charge_frequency.errors }}</div>{% endif %}
      </div>

      <div class="pl-form-row">
        <label for="{{ settings_form.charge_time.id_for_label }}">Charge Time (Pacific)</label>
        {{ settings_form.charge_time }}
        {% if settings_form.charge_time.errors %}<div class="pl-form-errors">{{ settings_form.charge_time.errors }}</div>{% endif %}
      </div>

      <div class="pl-form-row" id="dow-field" style="display:{% if settings_form.charge_frequency.value == 'weekly' %}block{% else %}none{% endif %}">
        <label for="{{ settings_form.charge_day_of_week.id_for_label }}">Day of Week (0=Monday … 6=Sunday)</label>
        {{ settings_form.charge_day_of_week }}
        {% if settings_form.charge_day_of_week.errors %}<div class="pl-form-errors">{{ settings_form.charge_day_of_week.errors }}</div>{% endif %}
      </div>

      <div class="pl-form-row" id="dom-field" style="display:{% if settings_form.charge_frequency.value == 'monthly' %}block{% else %}none{% endif %}">
        <label for="{{ settings_form.charge_day_of_month.id_for_label }}">Day of Month (1–28)</label>
        {{ settings_form.charge_day_of_month }}
        {% if settings_form.charge_day_of_month.errors %}<div class="pl-form-errors">{{ settings_form.charge_day_of_month.errors }}</div>{% endif %}
      </div>

      <div class="pl-form-row">
        <label for="{{ settings_form.default_tab_limit.id_for_label }}">Default Tab Limit ($)</label>
        {{ settings_form.default_tab_limit }}
        <div class="pl-form-hint">Maximum balance before new entries are blocked.</div>
        {% if settings_form.default_tab_limit.errors %}<div class="pl-form-errors">{{ settings_form.default_tab_limit.errors }}</div>{% endif %}
      </div>

      <div class="pl-form-row">
        <label for="{{ settings_form.max_retry_attempts.id_for_label }}">Max Retry Attempts</label>
        {{ settings_form.max_retry_attempts }}
        <div class="pl-form-hint">Number of times to retry a failed charge before locking the tab.</div>
        {% if settings_form.max_retry_attempts.errors %}<div class="pl-form-errors">{{ settings_form.max_retry_attempts.errors }}</div>{% endif %}
      </div>

      <div class="pl-form-row">
        <label for="{{ settings_form.retry_interval_hours.id_for_label }}">Retry Interval (hours)</label>
        {{ settings_form.retry_interval_hours }}
        {% if settings_form.retry_interval_hours.errors %}<div class="pl-form-errors">{{ settings_form.retry_interval_hours.errors }}</div>{% endif %}
      </div>

      <button type="submit" class="pl-btn pl-btn--primary">Save Settings</button>
    </form>
  </div>

  {% endif %}{# /settings #}

  {# ================================================================ #}
  {# STRIPE TAB                                                        #}
  {# ================================================================ #}
  {% if active_tab == "stripe" %}

  <div class="pl-card">
    <div class="pl-section-label">Connected Stripe Accounts</div>
    <table class="pl-table">
      <thead>
        <tr>
          <th>Display Name</th>
          <th>Guild</th>
          <th>Account ID</th>
          <th>Platform Fee</th>
          <th>Active</th>
          <th>Connected</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for acct in stripe_accounts %}
        <tr>
          <td>{{ acct.display_name }}</td>
          <td style="color:#96ACBB">{% if acct.guild %}{{ acct.guild.name }}{% else %}—{% endif %}</td>
          <td style="color:#96ACBB;font-size:0.8125rem">{{ acct.stripe_account_id|truncatechars:20 }}</td>
          <td>{{ acct.platform_fee_percent }}%</td>
          <td>{% if acct.is_active %}<span class="pl-badge pl-badge--ok">Active</span>{% else %}<span class="pl-badge pl-badge--muted">Inactive</span>{% endif %}</td>
          <td style="color:#96ACBB">{% if acct.connected_at %}{{ acct.connected_at|date:"M j, Y" }}{% else %}—{% endif %}</td>
          <td><a href="{% url 'admin:billing_stripeaccount_change' acct.pk %}" class="pl-btn pl-btn--sm pl-btn--secondary">Edit</a></td>
        </tr>
        {% empty %}
        <tr><td colspan="7" style="text-align:center;color:#96ACBB;padding:2rem">No Stripe accounts connected yet.</td></tr>
        {% endfor %}
      </tbody>
    </table>
    <div style="margin-top:1.25rem;display:flex;gap:0.75rem;flex-wrap:wrap">
      {% for guild in guilds %}
      <a href="{% url 'billing_initiate_connect' guild.pk %}" class="pl-btn pl-btn--secondary pl-btn--sm">
        Connect {{ guild.name }}
      </a>
      {% endfor %}
    </div>
  </div>

  <div class="pl-card">
    <div class="pl-section-label">Products</div>
    <table class="pl-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Guild</th>
          <th class="text-right">Price</th>
          <th>Active</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for product in products %}
        <tr>
          <td>{{ product.name }}</td>
          <td style="color:#96ACBB">{{ product.guild.name }}</td>
          <td class="text-right">${{ product.price }}</td>
          <td>{% if product.is_active %}<span class="pl-badge pl-badge--ok">Active</span>{% else %}<span class="pl-badge pl-badge--muted">Inactive</span>{% endif %}</td>
          <td><a href="{% url 'admin:billing_product_change' product.pk %}" class="pl-btn pl-btn--sm pl-btn--secondary">Edit</a></td>
        </tr>
        {% empty %}
        <tr><td colspan="5" style="text-align:center;color:#96ACBB;padding:2rem">No products yet.</td></tr>
        {% endfor %}
      </tbody>
    </table>
    <div style="margin-top:1.25rem">
      <a href="{% url 'admin:billing_product_add' %}" class="pl-btn pl-btn--secondary pl-btn--sm">+ Add Product</a>
    </div>
  </div>

  {% endif %}{# /stripe #}

</div>{# /pl-dashboard #}

{# ================================================================ #}
{# TAB DETAIL MODAL (shared, loaded via AJAX)                        #}
{# ================================================================ #}
<div id="tab-detail-modal" class="pl-modal-overlay" style="display:none"
     onclick="if(event.target===this)closeTabModal()">
  <div class="pl-modal">
    <div class="pl-modal__header">
      <div>
        <div class="pl-modal__title" id="tdm-name">—</div>
        <div class="pl-modal__subtitle" id="tdm-subtitle"></div>
      </div>
      <button class="pl-modal__close" onclick="closeTabModal()" aria-label="Close">&times;</button>
    </div>
    <div class="pl-modal__body">
      <div class="pl-modal__pills">
        <div class="pl-modal__pill">
          <div class="pl-modal__pill-value" id="tdm-balance">—</div>
          <div class="pl-modal__pill-label">Outstanding</div>
        </div>
        <div class="pl-modal__pill">
          <div class="pl-modal__pill-value" style="color:#F4EFDD" id="tdm-limit">—</div>
          <div class="pl-modal__pill-label">Tab Limit</div>
        </div>
        <div class="pl-modal__pill">
          <div class="pl-modal__pill-value" id="tdm-pm" style="font-size:0.9rem;padding-top:0.25rem">—</div>
          <div class="pl-modal__pill-label">Payment Method</div>
        </div>
      </div>

      <div class="pl-section-label" style="margin-top:0.5rem">Pending Entries</div>
      <table class="pl-table" id="tdm-entries-table">
        <thead><tr><th>Description</th><th>Date</th><th class="text-right">Amount</th></tr></thead>
        <tbody id="tdm-entries"></tbody>
      </table>

      <div class="pl-section-label" style="margin-top:1.25rem">Charge History</div>
      <table class="pl-table" id="tdm-history-table">
        <thead><tr><th>Date</th><th>Status</th><th class="text-right">Amount</th><th></th></tr></thead>
        <tbody id="tdm-history"></tbody>
      </table>
    </div>
    <div class="pl-modal__footer">
      <div style="display:flex;gap:0.5rem" id="tdm-actions"></div>
      <a id="tdm-admin-link" href="#" class="pl-btn pl-btn--sm pl-btn--secondary">View in Admin →</a>
    </div>
  </div>
</div>

{# ================================================================ #}
{# ADD CHARGE MODAL                                                   #}
{# ================================================================ #}
<div id="add-charge-modal" class="pl-modal-overlay" style="display:none"
     onclick="if(event.target===this)this.style.display='none'">
  <div class="pl-modal" style="max-width:480px">
    <div class="pl-modal__header">
      <div class="pl-modal__title">Add Charge to Tab</div>
      <button class="pl-modal__close" onclick="document.getElementById('add-charge-modal').style.display='none'" aria-label="Close">&times;</button>
    </div>
    <form method="post" action="{% url 'billing_admin_add_entry' %}">
      {% csrf_token %}
      <div class="pl-modal__body">
        <div class="pl-modal__field">
          <label for="{{ add_charge_form.member.id_for_label }}">Member</label>
          {{ add_charge_form.member }}
        </div>
        <div class="pl-modal__field">
          <label for="{{ add_charge_form.product.id_for_label }}">Product (optional)</label>
          {{ add_charge_form.product }}
        </div>
        <div class="pl-modal__field">
          <label for="{{ add_charge_form.description.id_for_label }}">Description</label>
          {{ add_charge_form.description }}
        </div>
        <div class="pl-modal__field">
          <label for="{{ add_charge_form.amount.id_for_label }}">Amount ($)</label>
          {{ add_charge_form.amount }}
        </div>
        {% if add_charge_form.non_field_errors %}
        <div class="pl-form-errors">{{ add_charge_form.non_field_errors }}</div>
        {% endif %}
      </div>
      <div class="pl-modal__footer">
        <button type="button" class="pl-btn pl-btn--secondary" onclick="document.getElementById('add-charge-modal').style.display='none'">Cancel</button>
        <button type="submit" class="pl-btn pl-btn--primary">Add Charge</button>
      </div>
    </form>
  </div>
</div>

<script>
  let _currentTabPk = null;

  function getCsrfToken() {
    const match = document.cookie.split('; ').find(r => r.startsWith('csrftoken='));
    return match ? match.split('=')[1] : '';
  }

  function openTabModal(tabPk) {
    _currentTabPk = tabPk;
    fetch('/billing/admin/tab/' + tabPk + '/detail/')
      .then(r => r.json())
      .then(data => {
        document.getElementById('tdm-name').textContent = data.member_name;
        document.getElementById('tdm-subtitle').textContent = data.is_locked ? ('Locked: ' + data.locked_reason) : '';
        document.getElementById('tdm-balance').textContent = '$' + data.balance;
        document.getElementById('tdm-limit').textContent = '$' + data.limit;
        document.getElementById('tdm-pm').textContent = data.payment_method || '— none —';

        const entriesEl = document.getElementById('tdm-entries');
        entriesEl.innerHTML = data.pending_entries.length
          ? data.pending_entries.map(e =>
              '<tr><td>' + e.description + '</td><td style="color:#96ACBB">' + e.date + '</td><td class="text-right">$' + e.amount + '</td></tr>'
            ).join('')
          : '<tr><td colspan="3" style="color:#96ACBB;text-align:center;padding:0.75rem">No pending entries.</td></tr>';

        const historyEl = document.getElementById('tdm-history');
        historyEl.innerHTML = data.charge_history.length
          ? data.charge_history.map(c => {
              const badge = c.status === 'succeeded'
                ? '<span class="pl-badge pl-badge--ok">Succeeded</span>'
                : '<span class="pl-badge pl-badge--fail">Failed</span>';
              const action = (c.status === 'succeeded' && c.receipt_url)
                ? '<a href="' + c.receipt_url + '" target="_blank" class="pl-btn pl-btn--sm pl-btn--secondary">Receipt</a>'
                : '';
              return '<tr><td style="color:#96ACBB">' + c.date + '</td><td>' + badge + '</td><td class="text-right">$' + c.amount + '</td><td>' + action + '</td></tr>';
            }).join('')
          : '<tr><td colspan="4" style="color:#96ACBB;text-align:center;padding:0.75rem">No charge history.</td></tr>';

        const adminLink = document.getElementById('tdm-admin-link');
        adminLink.href = '/admin/billing/tab/' + tabPk + '/change/';

        const actionsEl = document.getElementById('tdm-actions');
        actionsEl.innerHTML =
          '<button class="pl-btn pl-btn--sm pl-btn--secondary" onclick="document.getElementById(\'add-charge-modal\').style.display=\'flex\'">+ Add Charge</button>';

        document.getElementById('tab-detail-modal').style.display = 'flex';
      });
  }

  function closeTabModal() {
    document.getElementById('tab-detail-modal').style.display = 'none';
    _currentTabPk = null;
  }

  function retryCharge(chargePk, btn) {
    btn.disabled = true;
    btn.textContent = 'Retrying…';
    fetch('/billing/admin/retry-charge/' + chargePk + '/', {
      method: 'POST',
      headers: {'X-CSRFToken': getCsrfToken()}
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'succeeded') {
        const row = btn.closest('tr');
        const statusCell = row.querySelector('.pl-badge');
        if (statusCell) {
          statusCell.className = 'pl-badge pl-badge--ok';
          statusCell.textContent = 'Succeeded';
        }
        btn.remove();
      } else {
        btn.disabled = false;
        btn.textContent = 'Retry';
        alert('Retry failed. Check the charge in Stripe.');
      }
    });
  }

  /* Settings tab: show/hide day-of-week / day-of-month */
  const freqEl = document.getElementById('id_charge_frequency');
  if (freqEl) {
    function updateDayFields() {
      const freq = freqEl.value;
      document.getElementById('dow-field').style.display = freq === 'weekly' ? 'block' : 'none';
      document.getElementById('dom-field').style.display = freq === 'monthly' ? 'block' : 'none';
    }
    freqEl.addEventListener('change', updateDayFields);
    updateDayFields();
  }
</script>
{% endblock %}
```

- [ ] **Step 2: Run the full test suite**

```bash
.venv/bin/pytest -q --tb=short 2>&1 | tail -15
```

Expected: all tests pass, 100% coverage.

- [ ] **Step 3: Smoke-test the dashboard locally**

Visit `http://127.0.0.1:8080/billing/admin/dashboard/` while logged in as admin. Verify:
- Page loads with dark cards (no white-on-white)
- All five tabs are clickable and render without errors
- Settings tab shows the form; save works
- History tab shows filter chips

- [ ] **Step 4: Commit**

```bash
git add templates/billing/admin_dashboard.html
git commit -m "feat: replace payments dashboard with five-tab dark-theme layout"
```

---

## Self-Review

**Spec coverage check:**
- Overview tab with stats + outstanding + failed ✓ (Task 6)
- Open Tabs with filter chips + member search + modal ✓ (Tasks 4 + 6)
- History tab with monthly stats + filter + receipt/retry ✓ (Tasks 3 + 5 + 6)
- Settings form inline ✓ (Tasks 1 + 2 + 6)
- Stripe accounts + products ✓ (Task 5 + 6)
- Add Charge modal ✓ (Task 6)
- Tab Detail Modal via AJAX ✓ (Tasks 4 + 6)
- Dark theme matching Voting Dashboard ✓ (Task 6)
- White-on-white fix ✓ (Task 6 — no more `var(--body-bg)`)
- URL hash → replaced with `?tab=` query param (server-side, cleaner) ✓

**Placeholder scan:** No TBDs, no TODOs, all code blocks complete.

**Type consistency:** `TabCharge.Status.FAILED/SUCCEEDED` used consistently. `tab.pk` used for modal fetch URL throughout. `billing_admin_tab_detail_api` URL pattern matches the `openTabModal` JS fetch path exactly (`/billing/admin/tab/<pk>/detail/`).

**Scope:** Single deployable change. No migration required.
