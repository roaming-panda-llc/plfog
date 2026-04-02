# Multi-Stripe Connect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route tab charges to guild Stripe accounts via Stripe Connect destination charges, with a product catalog that determines routing and optional per-guild platform fees.

**Architecture:** New `StripeAccount` and `Product` models in the billing app. `TabEntry` gains a `product` FK for routing. `TabCharge` gains a `stripe_account` FK for destination tracking. The billing engine groups entries by destination guild and creates separate destination charges per group. Guild Stripe accounts are linked via Connect Standard OAuth.

**Tech Stack:** Django 5.1+, Stripe Connect (Standard accounts, destination charges), stripe-python SDK v11+, Unfold admin

---

## File Structure

### New Files
| File | Responsibility |
|---|---|
| `tests/billing/models/stripe_account_spec.py` | StripeAccount model tests |
| `tests/billing/models/product_spec.py` | Product model tests |
| `tests/billing/connect_views_spec.py` | Connect OAuth view tests |
| `templates/billing/admin_connect_accounts.html` | Admin page listing connected accounts |

### Modified Files
| File | Changes |
|---|---|
| `billing/models.py` | Add StripeAccount, Product models; add `product` FK to TabEntry; add `stripe_account` + `application_fee` to TabCharge |
| `billing/admin.py` | Register StripeAccount, Product admins |
| `billing/stripe_utils.py` | Add `create_destination_payment_intent`, `get_connect_oauth_url`, `complete_connect_oauth` |
| `billing/views.py` | Add Connect OAuth views; update admin_add_tab_entry with product |
| `billing/urls.py` | Add Connect OAuth + account management routes |
| `billing/forms.py` | Add product field to AdminAddTabEntryForm |
| `billing/management/commands/bill_tabs.py` | Group entries by destination; use destination charges for guild entries |
| `hub/forms.py` | Add product field to AddTabEntryForm |
| `hub/views.py` | Pass products to tab_detail context; handle product-based entries |
| `templates/hub/tab_detail.html` | Product picker; guild labels on entries |
| `templates/hub/tab_history.html` | Show destination per charge |
| `tests/billing/factories.py` | Add StripeAccountFactory, ProductFactory |
| `plfog/settings.py` | Add STRIPE_CONNECT_CLIENT_ID; add sidebar entries |

---

### Task 1: StripeAccount + Product Models

**Files:**
- Modify: `billing/models.py` (add after BillingSettings, before Tab — line ~109)
- Modify: `tests/billing/factories.py` (add StripeAccountFactory, ProductFactory)
- Create: `tests/billing/models/stripe_account_spec.py`
- Create: `tests/billing/models/product_spec.py`

- [ ] **Step 1: Write StripeAccount model tests**

Create `tests/billing/models/stripe_account_spec.py`:

```python
"""BDD-style tests for StripeAccount model."""

from __future__ import annotations

from decimal import Decimal

import pytest

from billing.models import StripeAccount
from tests.billing.factories import StripeAccountFactory
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def describe_StripeAccount():
    def it_has_str_representation():
        acct = StripeAccountFactory(display_name="Ceramics Guild")
        assert str(acct) == "Ceramics Guild"

    def it_links_to_guild():
        guild = GuildFactory(name="Glass")
        acct = StripeAccountFactory(guild=guild, display_name="Glass Guild")
        assert acct.guild == guild

    def it_allows_null_guild():
        acct = StripeAccountFactory(guild=None, display_name="Platform Admin")
        assert acct.guild is None

    def it_defaults_to_active():
        acct = StripeAccountFactory()
        assert acct.is_active is True

    def it_defaults_platform_fee_to_zero():
        acct = StripeAccountFactory()
        assert acct.platform_fee_percent == Decimal("0.00")

    def describe_compute_fee():
        def it_returns_zero_when_fee_is_zero():
            acct = StripeAccountFactory(platform_fee_percent=Decimal("0.00"))
            assert acct.compute_fee(Decimal("100.00")) == Decimal("0.00")

        def it_computes_correct_fee():
            acct = StripeAccountFactory(platform_fee_percent=Decimal("15.00"))
            assert acct.compute_fee(Decimal("100.00")) == Decimal("15.00")

        def it_rounds_to_two_decimal_places():
            acct = StripeAccountFactory(platform_fee_percent=Decimal("15.00"))
            assert acct.compute_fee(Decimal("12.00")) == Decimal("1.80")
```

- [ ] **Step 2: Write Product model tests**

Create `tests/billing/models/product_spec.py`:

```python
"""BDD-style tests for Product model."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError

from billing.models import Product
from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def describe_Product():
    def it_has_str_representation():
        product = ProductFactory(name="Clay - 5lb bag")
        assert str(product) == "Clay - 5lb bag"

    def it_links_to_guild():
        guild = GuildFactory(name="Ceramics")
        product = ProductFactory(guild=guild)
        assert product.guild == guild

    def it_defaults_to_active():
        product = ProductFactory()
        assert product.is_active is True

    def it_enforces_positive_price():
        with pytest.raises(IntegrityError):
            ProductFactory(price=Decimal("0.00"))

    def it_cascades_on_guild_delete():
        guild = GuildFactory()
        ProductFactory(guild=guild)
        assert Product.objects.count() == 1
        guild.delete()
        assert Product.objects.count() == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/billing/models/stripe_account_spec.py tests/billing/models/product_spec.py --override-ini="addopts=" --tb=short -q`
Expected: FAIL — StripeAccount, Product, factories not defined yet

- [ ] **Step 4: Add factories**

Add to `tests/billing/factories.py` (after TabChargeFactory):

```python
from billing.models import Product, StripeAccount
from tests.membership.factories import GuildFactory


class StripeAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StripeAccount

    guild = factory.SubFactory(GuildFactory)
    stripe_account_id = factory.Sequence(lambda n: f"acct_test_{n:04d}")
    display_name = factory.LazyAttribute(lambda o: f"{o.guild.name} Account" if o.guild else "Platform Account")
    is_active = True
    platform_fee_percent = Decimal("0.00")


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Product {n}")
    price = Decimal("10.00")
    guild = factory.SubFactory(GuildFactory)
    is_active = True
```

Also update the import at the top of `tests/billing/factories.py`:

```python
from billing.models import BillingSettings, Product, StripeAccount, Tab, TabCharge, TabEntry
```

- [ ] **Step 5: Implement StripeAccount and Product models**

Add to `billing/models.py` after the `BillingSettings` class (after line 108), before the `Tab` class:

```python
# ---------------------------------------------------------------------------
# StripeAccount (Stripe Connect connected account)
# ---------------------------------------------------------------------------


class StripeAccount(models.Model):
    """A Stripe Connect connected account — typically one per guild."""

    guild = models.OneToOneField(
        "membership.Guild",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stripe_account",
        help_text="The guild this Stripe account belongs to. Null for the platform admin account.",
    )
    stripe_account_id = models.CharField(
        max_length=255,
        help_text="Stripe Connect account ID (acct_xxx).",
    )
    display_name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this account.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this account is active and can receive charges.",
    )
    platform_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percentage of each charge kept by the platform (0-100). 0 means no fee.",
    )
    connected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this account was connected via OAuth.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this record was created.")

    class Meta:
        verbose_name = "Stripe Account"
        verbose_name_plural = "Stripe Accounts"

    def __str__(self) -> str:
        return self.display_name

    def compute_fee(self, amount: Decimal) -> Decimal:
        """Calculate the platform fee for a given charge amount."""
        if self.platform_fee_percent == Decimal("0.00"):
            return Decimal("0.00")
        return (amount * self.platform_fee_percent / Decimal("100")).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Product (purchasable items tied to guilds)
# ---------------------------------------------------------------------------


class Product(models.Model):
    """A purchasable item tied to a guild. Determines charge routing."""

    name = models.CharField(
        max_length=255,
        help_text="Product name shown to members.",
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Default price in USD.",
    )
    guild = models.ForeignKey(
        "membership.Guild",
        on_delete=models.CASCADE,
        related_name="products",
        help_text="The guild that sells this product. Determines which Stripe account receives the funds.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this product is available for purchase.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who created this product.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this product was created.")

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["guild__name", "name"]
        constraints = [
            models.CheckConstraint(condition=Q(price__gt=0), name="product_price_positive"),
        ]

    def __str__(self) -> str:
        return self.name
```

- [ ] **Step 6: Add product FK to TabEntry and stripe_account + application_fee to TabCharge**

In `billing/models.py`, add to `TabEntry` (after `tab_charge` field, around line 296):

```python
    product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tab_entries",
        help_text="Product purchased. Determines charge routing to guild Stripe account.",
    )
```

In `billing/models.py`, add to `TabCharge` (after `tab` field, around line 417):

```python
    stripe_account = models.ForeignKey(
        "StripeAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
        help_text="Destination Stripe Connect account. Null = platform direct charge.",
    )
    application_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Platform fee collected on this charge.",
    )
```

- [ ] **Step 7: Generate and apply migration**

Run:
```bash
python3 manage.py makemigrations billing
python3 manage.py migrate billing
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/billing/models/stripe_account_spec.py tests/billing/models/product_spec.py --override-ini="addopts=" --tb=short -q`
Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add billing/models.py billing/migrations/ tests/billing/factories.py tests/billing/models/stripe_account_spec.py tests/billing/models/product_spec.py
git commit -m "feat: add StripeAccount and Product models for multi-Stripe Connect routing"
```

---

### Task 2: Admin Registration for New Models

**Files:**
- Modify: `billing/admin.py` (add StripeAccount, Product admins)
- Modify: `tests/billing/admin_spec.py` (add tests)
- Modify: `plfog/settings.py` (add sidebar entries)

- [ ] **Step 1: Write admin tests**

Add to end of `tests/billing/admin_spec.py`:

```python
from billing.admin import ProductAdmin, StripeAccountAdmin
from billing.models import Product, StripeAccount
from tests.billing.factories import ProductFactory, StripeAccountFactory


def describe_StripeAccountAdmin():
    @pytest.fixture()
    def admin_instance():
        return StripeAccountAdmin(StripeAccount, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_never_allows_delete(admin_instance, superuser_request):
        assert admin_instance.has_delete_permission(superuser_request) is False


def describe_ProductAdmin():
    @pytest.fixture()
    def admin_instance():
        return ProductAdmin(Product, AdminSite())

    @pytest.fixture()
    def superuser_request(rf):
        request = rf.get("/admin/")
        request.user = User(is_staff=True, is_superuser=True)
        return request

    def it_displays_guild_name(admin_instance):
        product = ProductFactory()
        assert admin_instance.guild_name(product) == product.guild.name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/billing/admin_spec.py -k "StripeAccountAdmin or ProductAdmin" --override-ini="addopts=" --tb=short -q`
Expected: FAIL — admin classes not defined

- [ ] **Step 3: Implement admin registrations**

Add to end of `billing/admin.py`:

```python
from .models import Product, StripeAccount


# ---------------------------------------------------------------------------
# StripeAccount
# ---------------------------------------------------------------------------


@admin.register(StripeAccount)
class StripeAccountAdmin(ModelAdmin):
    list_display = ["display_name", "guild", "stripe_account_id", "is_active", "platform_fee_percent", "connected_at"]
    list_filter = ["is_active"]
    search_fields = ["display_name", "guild__name"]
    readonly_fields = ["stripe_account_id", "connected_at", "created_at"]

    fieldsets = [
        (
            None,
            {
                "fields": ["guild", "display_name", "is_active", "platform_fee_percent"],
            },
        ),
        (
            "Stripe",
            {
                "fields": ["stripe_account_id", "connected_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["name", "guild_name", "price", "is_active"]
    list_filter = ["is_active", "guild"]
    search_fields = ["name", "guild__name"]

    @admin.display(description="Guild", ordering="guild__name")
    def guild_name(self, obj: Product) -> str:
        return obj.guild.name
```

Also update the import at top of `billing/admin.py` line 10:

```python
from .models import BillingSettings, Product, StripeAccount, Tab, TabCharge, TabEntry
```

- [ ] **Step 4: Add sidebar entries**

In `plfog/settings.py`, add after the "Billing Settings" sidebar item (around line 394):

```python
                    {
                        "title": "Stripe Accounts",
                        "icon": "account_balance",
                        "link": reverse_lazy("admin:billing_stripeaccount_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Products",
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:billing_product_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/billing/admin_spec.py --override-ini="addopts=" --tb=short -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add billing/admin.py plfog/settings.py tests/billing/admin_spec.py
git commit -m "feat: admin registration for StripeAccount and Product models"
```

---

### Task 3: Stripe Connect OAuth + Utils

**Files:**
- Modify: `billing/stripe_utils.py` (add Connect OAuth + destination charge functions)
- Modify: `billing/views.py` (add Connect views)
- Modify: `billing/urls.py` (add Connect routes)
- Modify: `plfog/settings.py` (add STRIPE_CONNECT_CLIENT_ID)
- Create: `tests/billing/connect_views_spec.py`
- Modify: `tests/billing/stripe_utils_spec.py` (add destination charge + OAuth tests)

- [ ] **Step 1: Add STRIPE_CONNECT_CLIENT_ID to settings**

In `plfog/settings.py` after `STRIPE_WEBHOOK_SECRET` (line 227):

```python
STRIPE_CONNECT_CLIENT_ID = os.environ.get("STRIPE_CONNECT_CLIENT_ID", "")
```

- [ ] **Step 2: Write stripe_utils tests for new functions**

Add to end of `tests/billing/stripe_utils_spec.py`:

```python
def describe_create_destination_payment_intent():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_creates_destination_charge_with_fee(mock_get_client):
        client = _mock_client()
        intent = MagicMock()
        intent.id = "pi_dest_123"
        intent.status = "succeeded"
        intent.latest_charge = "ch_dest_001"
        client.v1.payment_intents.create.return_value = intent

        charge = MagicMock()
        charge.id = "ch_dest_001"
        charge.receipt_url = "https://stripe.com/receipt/dest"
        client.v1.charges.retrieve.return_value = charge
        mock_get_client.return_value = client

        result = stripe_utils.create_destination_payment_intent(
            customer_id="cus_123",
            payment_method_id="pm_456",
            amount_cents=1200,
            description="Tab charge",
            metadata={"tab_id": "1"},
            idempotency_key="key-1",
            destination_account_id="acct_guild_001",
            application_fee_cents=180,
        )

        assert result["id"] == "pi_dest_123"
        call_kwargs = client.v1.payment_intents.create.call_args.kwargs
        assert call_kwargs["params"]["transfer_data"] == {"destination": "acct_guild_001"}
        assert call_kwargs["params"]["application_fee_amount"] == 180

    @patch("billing.stripe_utils._get_stripe_client")
    def it_omits_fee_when_none(mock_get_client):
        client = _mock_client()
        intent = MagicMock()
        intent.id = "pi_dest_no_fee"
        intent.status = "succeeded"
        intent.latest_charge = None
        client.v1.payment_intents.create.return_value = intent
        mock_get_client.return_value = client

        result = stripe_utils.create_destination_payment_intent(
            customer_id="cus_123",
            payment_method_id="pm_456",
            amount_cents=800,
            description="Tab charge",
            metadata={},
            idempotency_key="key-2",
            destination_account_id="acct_guild_002",
            application_fee_cents=None,
        )

        call_kwargs = client.v1.payment_intents.create.call_args.kwargs
        assert "application_fee_amount" not in call_kwargs["params"]


def describe_get_connect_oauth_url():
    def it_builds_url_with_client_id(settings):
        settings.STRIPE_CONNECT_CLIENT_ID = "ca_test_123"
        url = stripe_utils.get_connect_oauth_url(state="guild-42")
        assert "ca_test_123" in url
        assert "guild-42" in url
        assert "stripe_landing=login" in url


def describe_complete_connect_oauth():
    @patch("billing.stripe_utils._get_stripe_client")
    def it_exchanges_code_for_account_id(mock_get_client):
        client = _mock_client()
        client.v1.oauth.token.return_value = MagicMock(stripe_user_id="acct_connected_123")
        mock_get_client.return_value = client

        result = stripe_utils.complete_connect_oauth(code="ac_test_code")

        assert result == "acct_connected_123"
```

- [ ] **Step 3: Implement new stripe_utils functions**

Add to end of `billing/stripe_utils.py`:

```python
def create_destination_payment_intent(
    *,
    customer_id: str,
    payment_method_id: str,
    amount_cents: int,
    description: str,
    metadata: dict[str, str],
    idempotency_key: str,
    destination_account_id: str,
    application_fee_cents: int | None = None,
) -> dict[str, Any]:
    """Create a Stripe Connect destination charge.

    Routes the payment to a connected account with an optional platform fee.
    """
    client = _get_stripe_client()
    params: dict[str, Any] = {
        "customer": customer_id,
        "payment_method": payment_method_id,
        "amount": amount_cents,
        "currency": "usd",
        "description": description,
        "metadata": metadata,
        "off_session": True,
        "confirm": True,
        "transfer_data": {"destination": destination_account_id},
    }
    if application_fee_cents is not None:
        params["application_fee_amount"] = application_fee_cents

    intent = client.v1.payment_intents.create(
        params=params,
        options={"idempotency_key": idempotency_key},
    )

    charge_id = ""
    receipt_url = ""
    if intent.latest_charge:
        charge = client.v1.charges.retrieve(str(intent.latest_charge))
        charge_id = charge.id
        receipt_url = charge.receipt_url or ""

    return {
        "id": intent.id,
        "status": intent.status,
        "charge_id": charge_id,
        "receipt_url": receipt_url,
    }


def get_connect_oauth_url(*, state: str) -> str:
    """Build the Stripe Connect OAuth URL for linking a Standard account."""
    client_id = settings.STRIPE_CONNECT_CLIENT_ID
    return (
        f"https://connect.stripe.com/oauth/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&scope=read_write"
        f"&state={state}"
        f"&stripe_landing=login"
    )


def complete_connect_oauth(*, code: str) -> str:
    """Exchange a Connect OAuth authorization code for a connected account ID."""
    client = _get_stripe_client()
    response = client.v1.oauth.token(params={"grant_type": "authorization_code", "code": code})
    return response.stripe_user_id
```

- [ ] **Step 4: Write Connect OAuth view tests**

Create `tests/billing/connect_views_spec.py`:

```python
"""BDD-style tests for Stripe Connect OAuth views."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.models import StripeAccount
from tests.membership.factories import GuildFactory

pytestmark = pytest.mark.django_db


def _create_superuser(client: Client) -> User:
    user = User.objects.create_superuser(username="connect_admin", password="pass", email="admin@test.com")
    client.login(username="connect_admin", password="pass")
    return user


def describe_initiate_connect():
    def it_requires_staff(client: Client):
        response = client.get("/billing/connect/initiate/1/")
        assert response.status_code == 302

    def it_redirects_to_stripe(client: Client, settings):
        settings.STRIPE_CONNECT_CLIENT_ID = "ca_test_abc"
        _create_superuser(client)
        guild = GuildFactory()

        response = client.get(f"/billing/connect/initiate/{guild.pk}/")

        assert response.status_code == 302
        assert "connect.stripe.com" in response.url


def describe_connect_callback():
    @patch("billing.views.stripe_utils.complete_connect_oauth")
    def it_creates_stripe_account_on_success(mock_oauth, client: Client):
        mock_oauth.return_value = "acct_new_123"
        _create_superuser(client)
        guild = GuildFactory()

        response = client.get(
            "/billing/connect/callback/",
            {"code": "ac_test_code", "state": str(guild.pk)},
        )

        assert response.status_code == 302
        acct = StripeAccount.objects.get(guild=guild)
        assert acct.stripe_account_id == "acct_new_123"

    def it_handles_error_from_stripe(client: Client):
        _create_superuser(client)

        response = client.get(
            "/billing/connect/callback/",
            {"error": "access_denied", "error_description": "User denied"},
        )

        assert response.status_code == 302

    @patch("billing.views.stripe_utils.complete_connect_oauth")
    def it_updates_existing_stripe_account(mock_oauth, client: Client):
        mock_oauth.return_value = "acct_updated_456"
        _create_superuser(client)
        guild = GuildFactory()
        StripeAccount.objects.create(
            guild=guild, stripe_account_id="acct_old", display_name=guild.name,
        )

        response = client.get(
            "/billing/connect/callback/",
            {"code": "ac_test_code", "state": str(guild.pk)},
        )

        assert response.status_code == 302
        acct = StripeAccount.objects.get(guild=guild)
        assert acct.stripe_account_id == "acct_updated_456"
```

- [ ] **Step 5: Implement Connect views**

Add to `billing/views.py`:

```python
@staff_member_required
def initiate_connect(request: HttpRequest, guild_id: int) -> HttpResponse:
    """Redirect admin to Stripe Connect OAuth to link a guild's account."""
    from membership.models import Guild

    guild = Guild.objects.get(pk=guild_id)
    url = stripe_utils.get_connect_oauth_url(state=str(guild.pk))
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

    acct, _created = StripeAccount.objects.update_or_create(
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
```

Add `StripeAccount` to the imports at the top of `billing/views.py`:

```python
from billing.models import BillingSettings, StripeAccount, Tab, TabCharge, TabEntry
```

- [ ] **Step 6: Add Connect URLs**

Add to `billing/urls.py`:

```python
    path("connect/initiate/<int:guild_id>/", views.initiate_connect, name="billing_initiate_connect"),
    path("connect/callback/", views.connect_callback, name="billing_connect_callback"),
```

- [ ] **Step 7: Run all tests**

Run: `python3 -m pytest tests/billing/ --override-ini="addopts=" --tb=short -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add billing/stripe_utils.py billing/views.py billing/urls.py plfog/settings.py tests/billing/stripe_utils_spec.py tests/billing/connect_views_spec.py
git commit -m "feat: Stripe Connect OAuth flow and destination charge support"
```

---

### Task 4: Billing Engine — Group by Destination

**Files:**
- Modify: `billing/management/commands/bill_tabs.py`
- Modify: `tests/billing/management/bill_tabs_spec.py`

- [ ] **Step 1: Write tests for destination grouping**

Add to `tests/billing/management/bill_tabs_spec.py`:

```python
from tests.billing.factories import ProductFactory, StripeAccountFactory


    def describe_destination_routing():
        @patch("billing.management.commands.bill_tabs.stripe_utils.create_destination_payment_intent")
        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_creates_separate_charges_per_guild(mock_receipt, mock_platform, mock_dest):
            mock_dest.return_value = {
                "id": "pi_dest", "status": "succeeded", "charge_id": "ch_dest", "receipt_url": "",
            }
            mock_platform.return_value = {
                "id": "pi_plat", "status": "succeeded", "charge_id": "ch_plat", "receipt_url": "",
            }
            BillingSettingsFactory()
            guild_a = GuildFactory(name="Ceramics")
            guild_b = GuildFactory(name="Glass")
            acct_a = StripeAccountFactory(guild=guild_a)
            acct_b = StripeAccountFactory(guild=guild_b)
            prod_a = ProductFactory(guild=guild_a, price=Decimal("12.00"))
            prod_b = ProductFactory(guild=guild_b, price=Decimal("8.00"))

            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, product=prod_a, amount=Decimal("12.00"))
            TabEntryFactory(tab=tab, product=prod_b, amount=Decimal("8.00"))
            TabEntryFactory(tab=tab, product=None, amount=Decimal("5.00"))  # platform

            output = _call_bill_tabs(force=True)

            assert "3 charged" in output
            assert mock_dest.call_count == 2  # Two guild destination charges
            assert mock_platform.call_count == 1  # One platform direct charge

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_destination_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_includes_application_fee(mock_receipt, mock_dest):
            mock_dest.return_value = {
                "id": "pi_fee", "status": "succeeded", "charge_id": "ch_fee", "receipt_url": "",
            }
            BillingSettingsFactory()
            guild = GuildFactory()
            StripeAccountFactory(guild=guild, platform_fee_percent=Decimal("15.00"))
            prod = ProductFactory(guild=guild, price=Decimal("100.00"))

            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, product=prod, amount=Decimal("100.00"))

            _call_bill_tabs(force=True)

            call_kwargs = mock_dest.call_args.kwargs
            assert call_kwargs["application_fee_cents"] == 1500  # 15% of $100

        @patch("billing.management.commands.bill_tabs.stripe_utils.create_payment_intent")
        @patch("billing.management.commands.bill_tabs.send_receipt")
        def it_skips_entries_with_disconnected_guild(mock_receipt, mock_platform):
            mock_platform.return_value = {
                "id": "pi_plat", "status": "succeeded", "charge_id": "ch_plat", "receipt_url": "",
            }
            BillingSettingsFactory()
            guild = GuildFactory()
            StripeAccountFactory(guild=guild, is_active=False)
            prod = ProductFactory(guild=guild)

            member = MemberFactory(status="active")
            tab = TabFactory(member=member, stripe_customer_id="cus_test", stripe_payment_method_id="pm_test")
            TabEntryFactory(tab=tab, product=prod, amount=Decimal("20.00"))
            TabEntryFactory(tab=tab, product=None, amount=Decimal("5.00"))  # platform still charges

            output = _call_bill_tabs(force=True)

            assert "1 charged" in output  # Only the platform entry
            assert "1 skipped" in output  # Guild entry skipped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/billing/management/bill_tabs_spec.py -k "destination" --override-ini="addopts=" --tb=short -q`
Expected: FAIL

- [ ] **Step 3: Refactor bill_tabs to group by destination**

Replace `_process_tab` in `billing/management/commands/bill_tabs.py` with:

```python
    def _process_tab(self, tab: Tab, settings: BillingSettings) -> int:
        """Process a single tab. Returns count of charges created."""
        from billing.models import StripeAccount

        with transaction.atomic():
            locked_tab = Tab.objects.select_for_update().get(pk=tab.pk)

            if not locked_tab.has_payment_method:
                logger.warning("Tab %s: no payment method on file, skipping.", tab.pk)
                return 0

            if not locked_tab.stripe_customer_id:
                logger.warning("Tab %s: no Stripe customer ID, skipping.", tab.pk)
                return 0

            pending = locked_tab.entries.filter(
                tab_charge__isnull=True,
                voided_at__isnull=True,
            ).select_related("product__guild__stripe_account")

            # Group entries by destination (guild pk or None for platform)
            groups: dict[int | None, list] = {}
            for entry in pending:
                if entry.product and entry.product.guild_id:
                    key = entry.product.guild_id
                else:
                    key = None
                groups.setdefault(key, []).append(entry)

        # Process each group outside the lock
        charges_created = 0
        for guild_id, entries in groups.items():
            total = sum(e.amount for e in entries)
            if total < Decimal("0.50"):
                if total > Decimal("0.00"):
                    logger.info("Tab %s guild %s: $%s below Stripe minimum.", tab.pk, guild_id, total)
                continue

            # Resolve destination
            stripe_account = None
            if guild_id is not None:
                try:
                    stripe_account = StripeAccount.objects.get(guild_id=guild_id, is_active=True)
                except StripeAccount.DoesNotExist:
                    logger.warning("Tab %s: guild %s has no active Stripe account, skipping entries.", tab.pk, guild_id)
                    continue

            # Create charge record
            idempotency_key = str(uuid.uuid4())
            charge = TabCharge.objects.create(
                tab=tab,
                amount=total,
                status=TabCharge.Status.PROCESSING,
                stripe_account=stripe_account,
            )
            TabEntry.objects.filter(pk__in=[e.pk for e in entries]).update(tab_charge=charge)

            # Stripe call
            try:
                if stripe_account:
                    fee = stripe_account.compute_fee(total)
                    fee_cents = int(fee * 100) if fee > Decimal("0.00") else None
                    result = stripe_utils.create_destination_payment_intent(
                        customer_id=tab.stripe_customer_id,
                        payment_method_id=tab.stripe_payment_method_id,
                        amount_cents=int(total * 100),
                        description=f"Past Lives Makerspace tab — {stripe_account.display_name}",
                        metadata={"tab_id": str(tab.pk), "charge_id": str(charge.pk)},
                        idempotency_key=f"tabcharge-{charge.pk}-{idempotency_key}",
                        destination_account_id=stripe_account.stripe_account_id,
                        application_fee_cents=fee_cents,
                    )
                    charge.application_fee = fee if fee > Decimal("0.00") else None
                else:
                    result = stripe_utils.create_payment_intent(
                        customer_id=tab.stripe_customer_id,
                        payment_method_id=tab.stripe_payment_method_id,
                        amount_cents=int(total * 100),
                        description=f"Past Lives Makerspace tab — {charge.entry_count} items",
                        metadata={"tab_id": str(tab.pk), "charge_id": str(charge.pk)},
                        idempotency_key=f"tabcharge-{charge.pk}-{idempotency_key}",
                    )

                charge.stripe_payment_intent_id = result["id"]
                charge.stripe_charge_id = result["charge_id"]
                charge.stripe_receipt_url = result["receipt_url"]
                charge.status = TabCharge.Status.SUCCEEDED
                charge.charged_at = timezone.now()
                charge.save()
                send_receipt(charge)
                charges_created += 1

            except Exception:
                logger.exception("Tab %s: Stripe charge failed for guild %s.", tab.pk, guild_id)
                charge.status = TabCharge.Status.FAILED
                charge.failure_reason = "Stripe charge failed"
                charge.retry_count = 1
                charge.next_retry_at = timezone.now() + timedelta(hours=settings.retry_interval_hours)
                charge.save()
                notify_admin_charge_failed(charge)

        return charges_created
```

Also update `_run_billing` to use the new return value (count of charges instead of bool):

```python
        for tab in tabs_with_pending:
            result = self._process_tab(tab, settings)
            billed_count += result
            if result == 0:
                skipped_count += 1
```

Add `TabEntry` to the imports at top of `bill_tabs.py`:

```python
from billing.models import BillingSettings, Tab, TabCharge, TabEntry
```

- [ ] **Step 4: Run all billing tests**

Run: `python3 -m pytest tests/billing/ --override-ini="addopts=" --tb=short -q`
Expected: All pass (existing tests may need minor fixes for the new `_process_tab` return type)

- [ ] **Step 5: Commit**

```bash
git add billing/management/commands/bill_tabs.py tests/billing/management/bill_tabs_spec.py
git commit -m "feat: billing engine groups entries by destination for multi-Stripe routing"
```

---

### Task 5: Product Picker in Forms + Views

**Files:**
- Modify: `hub/forms.py` (add product field to AddTabEntryForm)
- Modify: `billing/forms.py` (add product field to AdminAddTabEntryForm)
- Modify: `hub/views.py` (pass products to context, handle product entries)
- Modify: `billing/views.py` (handle product in admin add-entry)
- Modify: `templates/hub/tab_detail.html` (product picker, guild labels)
- Modify: `templates/hub/tab_history.html` (destination per charge)

- [ ] **Step 1: Add product field to AddTabEntryForm**

In `hub/forms.py`, update `AddTabEntryForm`:

```python
from billing.models import Product


class AddTabEntryForm(forms.Form):
    """Self-service form for members to add items to their own tab."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).select_related("guild"),
        required=False,
        empty_label="— Manual entry (no product) —",
        label="Product",
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "What is this charge for?"}),
        label="Description",
    )
    amount = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01"}),
        label="Amount ($)",
    )

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        product = cleaned.get("product")
        if product:
            cleaned["description"] = product.name
            cleaned["amount"] = product.price
        elif not cleaned.get("description") or not cleaned.get("amount"):
            raise forms.ValidationError("Either select a product or enter a description and amount.")
        return cleaned
```

- [ ] **Step 2: Add product to AdminAddTabEntryForm**

In `billing/forms.py`, update `AdminAddTabEntryForm`:

```python
from billing.models import Product


class AdminAddTabEntryForm(forms.Form):
    """Admin form for adding a charge to any member's tab."""

    member = forms.ModelChoiceField(
        queryset=Member.objects.filter(status=Member.Status.ACTIVE),
        label="Member",
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).select_related("guild"),
        required=False,
        empty_label="— Manual entry —",
        label="Product",
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "What is this charge for?"}),
        label="Description",
    )
    amount = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01"}),
        label="Amount ($)",
    )

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        product = cleaned.get("product")
        if product:
            cleaned["description"] = product.name
            cleaned["amount"] = product.price
        elif not cleaned.get("description") or not cleaned.get("amount"):
            raise forms.ValidationError("Either select a product or enter a description and amount.")
        return cleaned
```

- [ ] **Step 3: Update hub tab_detail view to pass product and handle product entries**

In `hub/views.py`, update `tab_detail` to pass products and save product on entry:

```python
from billing.models import Product, Tab

# In tab_detail view, add products to context:
    products = Product.objects.filter(is_active=True).select_related("guild").order_by("guild__name", "name")

# In the POST handler, after form.is_valid():
    product = form.cleaned_data.get("product")
    tab.add_entry(
        description=form.cleaned_data["description"],
        amount=form.cleaned_data["amount"],
        added_by=request.user,
        is_self_service=True,
        product=product,
    )
```

This also requires updating `Tab.add_entry()` in `billing/models.py` to accept an optional `product` parameter and pass it to `TabEntry.objects.create()`.

- [ ] **Step 4: Update Tab.add_entry to accept product**

In `billing/models.py`, update `add_entry` signature and create call:

```python
    def add_entry(
        self,
        *,
        description: str,
        amount: Decimal,
        added_by: User | None = None,
        is_self_service: bool = False,
        product: Product | None = None,
    ) -> TabEntry:
        # ... existing logic ...
            return TabEntry.objects.create(
                tab=self,
                description=description,
                amount=amount,
                added_by=added_by,
                is_self_service=is_self_service,
                product=product,
            )
```

Add `Product` to the `TYPE_CHECKING` import block.

- [ ] **Step 5: Update admin add-entry view to save product**

In `billing/views.py`, update `admin_add_tab_entry`:

```python
            product = form.cleaned_data.get("product")
            TabEntry.objects.create(
                tab=tab,
                description=form.cleaned_data["description"],
                amount=form.cleaned_data["amount"],
                added_by=request.user,
                product=product,
            )
```

- [ ] **Step 6: Update tab_detail.html template**

Add product picker and guild labels to `templates/hub/tab_detail.html`. In the form section:

```html
<div class="tab-add-form__field">
    <label for="id_product">{{ form.product.label }}</label>
    {{ form.product }}
</div>
```

In the entries table, add a guild column:

```html
<td>{{ entry.description }}{% if entry.product %} <span class="tab-entry-guild">→ {{ entry.product.guild.name }}</span>{% endif %}</td>
```

- [ ] **Step 7: Update tab_history.html template**

In `templates/hub/tab_history.html`, show destination:

```html
{% if charge.stripe_account %}
<span class="tab-charge__destination">→ {{ charge.stripe_account.display_name }}</span>
{% endif %}
```

- [ ] **Step 8: Update form tests**

Update `tests/billing/forms_spec.py` to test product-based form submissions and the clean() validation logic.

- [ ] **Step 9: Run all tests**

Run: `python3 -m pytest --override-ini="addopts=" --tb=short -q`
Expected: All pass

- [ ] **Step 10: Commit**

```bash
git add billing/models.py billing/forms.py billing/views.py hub/forms.py hub/views.py templates/hub/tab_detail.html templates/hub/tab_history.html tests/
git commit -m "feat: product picker in tab forms with guild routing labels"
```

---

### Task 6: Polish — Lint, Types, Coverage, Version

**Files:**
- All billing/ and tests/billing/ files
- `plfog/version.py`

- [ ] **Step 1: Format and lint**

Run: `ruff format . && ruff check --fix .`

- [ ] **Step 2: Type check**

Run: `python3 -m mypy billing/`
Fix any errors.

- [ ] **Step 3: Coverage check**

Run: `python3 -m pytest tests/billing/ tests/hub/tab_views_spec.py --override-ini="addopts=" --cov=billing --cov-report=term-missing --tb=short -q`
Target: 100%

- [ ] **Step 4: Full test suite**

Run: `python3 -m pytest --override-ini="addopts=" --tb=short -q`
Expected: All pass

- [ ] **Step 5: Version bump**

Update `plfog/version.py`:

```python
VERSION = "1.4.0"
```

Add changelog entry:

```python
    {
        "version": "1.4.0",
        "date": "2026-04-02",
        "title": "Multi-Stripe Connect",
        "changes": [
            "Guild Stripe accounts can now be connected via Stripe Connect — each guild receives their share of charges directly",
            "New product catalog — admins create products tied to guilds, and charges route to the right Stripe account automatically",
            "Members can pick products when adding to their tab — price and routing are automatic",
            "Optional platform fee per guild — a percentage of each charge stays with the makerspace",
            "Billing engine now creates separate charges per destination guild",
            "New admin pages for managing Stripe accounts and products",
        ],
    },
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: multi-Stripe Connect support — v1.4.0"
```

---

## Verification

After all tasks:

1. `ruff format . && ruff check .` — clean
2. `python3 -m mypy billing/` — clean
3. `python3 -m pytest --override-ini="addopts=" --tb=short -q` — all pass
4. Billing module coverage — 100%
5. Manual: admin can create StripeAccount, Product, and see them in sidebar
6. Manual: member Add to Tab form shows product picker
