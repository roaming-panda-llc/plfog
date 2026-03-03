# Full Feature Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Port all missing features from makerspace-tea (Laravel) to plfog (Django) — ~26 new models across 4 new apps, Stripe billing, django-guardian permissions, full admin UI — in a single PR.

**Architecture:** 4 new Django apps (`billing`, `tools`, `education`, `outreach`) plus enhancements to existing `membership` and `core` apps. Admin-only UI via django-unfold. Object-level permissions via django-guardian. Stripe integration via dj-stripe. BDD tests with pytest-describe, 100% coverage, mutation testing.

**Tech Stack:** Django 5.1+, django-unfold, dj-stripe, django-guardian, pytest-describe, factory-boy

**Reference repos:**
- Laravel source: `/Users/joshplaza/Code/hexagonstorms/makerspace-tea/makerverse/`
- Google Drive docs: `/Users/joshplaza/Code/hexagonstorms/ FOG_dump/`

---

## Task 1: Dependencies and Project Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `pyproject.toml`
- Modify: `plfog/settings.py:34-55` (INSTALLED_APPS)
- Modify: `plfog/settings.py:128-131` (AUTHENTICATION_BACKENDS)
- Modify: `.github/workflows/ci.yml:42-43` (mutation test targets)
- Modify: `.github/workflows/ci.yml:69` (mypy targets)

**Step 1: Update requirements.txt**

Add after `Pillow>=10.0`:
```
dj-stripe>=2.9
django-guardian>=2.4
stripe>=8.0
```

**Step 2: Update requirements-dev.txt**

No changes needed — factory-boy and faker already present.

**Step 3: Update pyproject.toml**

Add new apps to pytest coverage (`addopts` line 11):
```
addopts = "-v --tb=short --cov=plfog --cov=core --cov=membership --cov=billing --cov=tools --cov=education --cov=outreach --cov-report=term-missing"
```

Add mypy overrides for new apps (after the existing `membership.*` override at line 29-30):
```toml
[[tool.mypy.overrides]]
module = "billing.*"
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "tools.*"
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "education.*"
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "outreach.*"
disallow_untyped_defs = true
```

**Step 4: Update settings.py INSTALLED_APPS**

Add after `"membership"` in INSTALLED_APPS (line 54):
```python
    "billing",
    "tools",
    "education",
    "outreach",
    # Third-party (after project apps)
    "guardian",
    "djstripe",
```

**Step 5: Update AUTHENTICATION_BACKENDS in settings.py**

Add guardian backend (after line 131):
```python
    "guardian.backends.ObjectPermissionBackend",
```

**Step 6: Add Stripe settings to settings.py**

Add at end of file:
```python
# Stripe (dj-stripe)
STRIPE_LIVE_SECRET_KEY = os.environ.get("STRIPE_LIVE_SECRET_KEY", "")
STRIPE_TEST_SECRET_KEY = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
STRIPE_LIVE_MODE = os.environ.get("STRIPE_LIVE_MODE", "False").lower() == "true"
DJSTRIPE_WEBHOOK_SECRET = os.environ.get("DJSTRIPE_WEBHOOK_SECRET", "")
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"
```

**Step 7: Update CI workflow**

In `ci.yml`, update mutation test line to include new apps:
```yaml
      - name: Run mutation tests
        run: pytest --leela --target plfog/ --target core/ --target membership/ --target billing/ --target tools/ --target education/ --target outreach/
```

Update mypy line:
```yaml
      - name: Mypy
        run: mypy plfog/ core/ membership/ billing/ tools/ education/ outreach/
```

**Step 8: Update sidebar navigation in settings.py**

Replace the SIDEBAR navigation (lines 269-314) with expanded version including all new apps:
```python
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Navigation",
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": "Members",
                "items": [
                    {
                        "title": "Members",
                        "icon": "group",
                        "link": reverse_lazy("admin:membership_member_changelist"),
                    },
                    {
                        "title": "Membership Plans",
                        "icon": "card_membership",
                        "link": reverse_lazy("admin:membership_membershipplan_changelist"),
                    },
                    {
                        "title": "Schedules",
                        "icon": "calendar_month",
                        "link": reverse_lazy("admin:membership_memberschedule_changelist"),
                    },
                ],
            },
            {
                "title": "Guilds",
                "items": [
                    {
                        "title": "Guilds",
                        "icon": "groups",
                        "link": reverse_lazy("admin:membership_guild_changelist"),
                    },
                    {
                        "title": "Guild Votes",
                        "icon": "how_to_vote",
                        "link": reverse_lazy("admin:membership_guildvote_changelist"),
                    },
                ],
            },
            {
                "title": "Spaces & Leases",
                "items": [
                    {
                        "title": "Spaces",
                        "icon": "meeting_room",
                        "link": reverse_lazy("admin:membership_space_changelist"),
                    },
                    {
                        "title": "Leases",
                        "icon": "description",
                        "link": reverse_lazy("admin:membership_lease_changelist"),
                    },
                ],
            },
            {
                "title": "Tools & Equipment",
                "items": [
                    {
                        "title": "Tools",
                        "icon": "build",
                        "link": reverse_lazy("admin:tools_tool_changelist"),
                    },
                    {
                        "title": "Reservations",
                        "icon": "event_available",
                        "link": reverse_lazy("admin:tools_toolreservation_changelist"),
                    },
                    {
                        "title": "Rentables",
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:tools_rentable_changelist"),
                    },
                    {
                        "title": "Rentals",
                        "icon": "receipt",
                        "link": reverse_lazy("admin:tools_rental_changelist"),
                    },
                ],
            },
            {
                "title": "Education",
                "items": [
                    {
                        "title": "Classes",
                        "icon": "school",
                        "link": reverse_lazy("admin:education_makerclass_changelist"),
                    },
                    {
                        "title": "Students",
                        "icon": "person",
                        "link": reverse_lazy("admin:education_student_changelist"),
                    },
                    {
                        "title": "Discount Codes",
                        "icon": "sell",
                        "link": reverse_lazy("admin:education_classdiscountcode_changelist"),
                    },
                    {
                        "title": "Orientations",
                        "icon": "explore",
                        "link": reverse_lazy("admin:education_orientation_changelist"),
                    },
                ],
            },
            {
                "title": "Billing",
                "items": [
                    {
                        "title": "Orders",
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:billing_order_changelist"),
                    },
                    {
                        "title": "Invoices",
                        "icon": "request_quote",
                        "link": reverse_lazy("admin:billing_invoice_changelist"),
                    },
                    {
                        "title": "Revenue Splits",
                        "icon": "pie_chart",
                        "link": reverse_lazy("admin:billing_revenuesplit_changelist"),
                    },
                    {
                        "title": "Subscription Plans",
                        "icon": "loyalty",
                        "link": reverse_lazy("admin:billing_subscriptionplan_changelist"),
                    },
                    {
                        "title": "Subscriptions",
                        "icon": "autorenew",
                        "link": reverse_lazy("admin:billing_membersubscription_changelist"),
                    },
                    {
                        "title": "Payouts",
                        "icon": "payments",
                        "link": reverse_lazy("admin:billing_payout_changelist"),
                    },
                ],
            },
            {
                "title": "Outreach",
                "items": [
                    {
                        "title": "Leads",
                        "icon": "contact_mail",
                        "link": reverse_lazy("admin:outreach_lead_changelist"),
                    },
                    {
                        "title": "Tours",
                        "icon": "tour",
                        "link": reverse_lazy("admin:outreach_tour_changelist"),
                    },
                    {
                        "title": "Events",
                        "icon": "event",
                        "link": reverse_lazy("admin:outreach_event_changelist"),
                    },
                    {
                        "title": "Buyables",
                        "icon": "storefront",
                        "link": reverse_lazy("admin:outreach_buyable_changelist"),
                    },
                ],
            },
            {
                "title": "Settings",
                "items": [
                    {
                        "title": "Settings",
                        "icon": "settings",
                        "link": reverse_lazy("admin:core_setting_changelist"),
                    },
                ],
            },
        ],
    },
```

**Step 9: Create new app directories**

```bash
cd /Users/joshplaza/Code/hexagonstorms/plfog
python manage.py startapp billing
python manage.py startapp tools
python manage.py startapp education
python manage.py startapp outreach
```

**Step 10: Create test directories for new apps**

```bash
mkdir -p tests/billing tests/tools tests/education tests/outreach
touch tests/billing/__init__.py tests/tools/__init__.py tests/education/__init__.py tests/outreach/__init__.py
```

**Step 11: Install dependencies and verify Django checks pass**

```bash
pip install -r requirements-dev.txt
python manage.py check
```

**Step 12: Commit**

```bash
git add -A
git commit -m "feat: add billing, tools, education, outreach apps with deps"
```

---

## Task 2: Core Setting Model

**Files:**
- Create: `core/models.py`
- Modify: `core/admin.py` (or create if not exists)
- Create: `tests/core/setting_spec.py`
- Create: `tests/core/factories.py`

**Step 1: Write failing tests**

Create `tests/core/factories.py`:
```python
from __future__ import annotations

import factory
from django.contrib.auth.models import User

from core.models import Setting


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")


class SettingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Setting

    key = factory.Sequence(lambda n: f"setting_{n}")
    value = {"default": True}
    type = "json"
```

Create `tests/core/setting_spec.py`:
```python
import pytest

from core.models import Setting
from tests.core.factories import SettingFactory, UserFactory


@pytest.mark.django_db
def describe_setting():
    def it_has_str_representation():
        setting = SettingFactory(key="door_code")
        assert str(setting) == "door_code"

    def it_stores_json_value():
        setting = SettingFactory(key="config", value={"theme": "dark"})
        setting.refresh_from_db()
        assert setting.value == {"theme": "dark"}

    def it_tracks_updated_by():
        user = UserFactory()
        setting = SettingFactory(updated_by=user)
        assert setting.updated_by == user

    def it_get_returns_value():
        SettingFactory(key="door_code", value="1234")
        assert Setting.get("door_code") == "1234"

    def it_get_returns_default_when_missing():
        assert Setting.get("nonexistent", "fallback") == "fallback"

    def it_set_creates_setting():
        Setting.set("new_key", "new_value")
        assert Setting.get("new_key") == "new_value"

    def it_set_updates_existing():
        SettingFactory(key="existing", value="old")
        Setting.set("existing", "new")
        assert Setting.get("existing") == "new"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/setting_spec.py -v
```

Expected: FAIL (Setting model doesn't exist yet)

**Step 3: Implement Setting model**

Write `core/models.py`:
```python
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import models


class Setting(models.Model):
    key = models.CharField(max_length=255, unique=True)
    value = models.JSONField(default=dict)
    type = models.CharField(max_length=20, default="text")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    @classmethod
    def get(cls, key: str, default: object = None) -> object:
        cache_key = f"setting.{key}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            setting = cls.objects.get(key=key)
            cache.set(cache_key, setting.value, 3600)
            return setting.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(
        cls,
        key: str,
        value: object,
        type: str = "text",
        updated_by_id: int | None = None,
    ) -> None:
        cls.objects.update_or_create(
            key=key,
            defaults={"value": value, "type": type, "updated_by_id": updated_by_id},
        )
        cache.delete(f"setting.{key}")
```

**Step 4: Create migration and register admin**

```bash
python manage.py makemigrations core
```

Register in admin (create `core/admin.py` or update):
```python
from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Setting


@admin.register(Setting)
class SettingAdmin(ModelAdmin):
    list_display = ["key", "type", "updated_by", "updated_at"]
    search_fields = ["key"]
    list_filter = ["type"]
    readonly_fields = ["created_at", "updated_at"]
```

**Step 5: Run tests**

```bash
pytest tests/core/setting_spec.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add core/ tests/core/
git commit -m "feat: add Setting model with get/set class methods and caching"
```

---

## Task 3: Membership App Enhancements (Guild fields, GuildDocument, GuildWishlistItem, GuildMembership, MemberSchedule, ScheduleBlock)

**Files:**
- Modify: `membership/models.py`
- Modify: `membership/admin.py`
- Create: `membership/migrations/0005_*.py` (auto-generated)
- Modify: `tests/membership/factories.py`
- Create: `tests/membership/guild_enhancements_spec.py`
- Create: `tests/membership/schedule_spec.py`

**Step 1: Write failing tests for new guild models**

Add to `tests/membership/factories.py`:
```python
from membership.models import (
    Guild, GuildDocument, GuildMembership, GuildVote, GuildWishlistItem,
    Lease, Member, MemberSchedule, MembershipPlan, ScheduleBlock, Space,
)

# ... existing factories ...

class GuildMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildMembership

    guild = factory.SubFactory(GuildFactory)
    user = factory.SubFactory("tests.core.factories.UserFactory")
    is_lead = False


class GuildDocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildDocument

    guild = factory.SubFactory(GuildFactory)
    name = factory.Sequence(lambda n: f"Document {n}")
    file_path = "guild_docs/test.pdf"
    uploaded_by = factory.SubFactory("tests.core.factories.UserFactory")


class GuildWishlistItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildWishlistItem

    guild = factory.SubFactory(GuildFactory)
    name = factory.Sequence(lambda n: f"Wishlist Item {n}")
    estimated_cost = Decimal("100.00")
    created_by = factory.SubFactory("tests.core.factories.UserFactory")


class MemberScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MemberSchedule

    user = factory.SubFactory("tests.core.factories.UserFactory")


class ScheduleBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduleBlock

    member_schedule = factory.SubFactory(MemberScheduleFactory)
    day_of_week = 1  # Monday
    start_time = "09:00"
    end_time = "17:00"
    is_recurring = True
```

Create `tests/membership/guild_enhancements_spec.py`:
```python
import pytest
from django.utils.text import slugify

from membership.models import Guild, GuildDocument, GuildMembership, GuildWishlistItem
from tests.core.factories import UserFactory
from tests.membership.factories import (
    GuildDocumentFactory,
    GuildFactory,
    GuildMembershipFactory,
    GuildWishlistItemFactory,
)


@pytest.mark.django_db
def describe_guild_enhancements():
    def it_has_slug():
        guild = GuildFactory(name="Woodworking Guild", slug="")
        guild.refresh_from_db()
        assert guild.slug == "woodworking-guild"

    def it_has_intro_and_description():
        guild = GuildFactory(intro="Short intro", description="Long description")
        assert guild.intro == "Short intro"

    def it_has_is_active_default():
        guild = GuildFactory()
        assert guild.is_active is True


@pytest.mark.django_db
def describe_guild_membership():
    def it_links_user_to_guild():
        gm = GuildMembershipFactory()
        assert gm.guild is not None
        assert gm.user is not None

    def it_tracks_is_lead():
        gm = GuildMembershipFactory(is_lead=True)
        assert gm.is_lead is True

    def it_has_str():
        gm = GuildMembershipFactory()
        assert str(gm.guild.name) in str(gm)


@pytest.mark.django_db
def describe_guild_document():
    def it_has_str():
        doc = GuildDocumentFactory(name="Safety Rules")
        assert str(doc) == "Safety Rules"

    def it_belongs_to_guild():
        doc = GuildDocumentFactory()
        assert doc.guild is not None


@pytest.mark.django_db
def describe_guild_wishlist_item():
    def it_has_str():
        item = GuildWishlistItemFactory(name="New Bandsaw")
        assert str(item) == "New Bandsaw"

    def it_defaults_is_fulfilled_false():
        item = GuildWishlistItemFactory()
        assert item.is_fulfilled is False
```

Create `tests/membership/schedule_spec.py`:
```python
import pytest

from membership.models import MemberSchedule, ScheduleBlock
from tests.membership.factories import MemberScheduleFactory, ScheduleBlockFactory


@pytest.mark.django_db
def describe_member_schedule():
    def it_links_to_user():
        ms = MemberScheduleFactory()
        assert ms.user is not None

    def it_has_str():
        ms = MemberScheduleFactory()
        assert str(ms.user) in str(ms)


@pytest.mark.django_db
def describe_schedule_block():
    def it_has_day_name():
        block = ScheduleBlockFactory(day_of_week=1)
        assert block.day_name == "Monday"

    def it_has_str():
        block = ScheduleBlockFactory()
        assert "Monday" in str(block) or str(block)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/membership/guild_enhancements_spec.py tests/membership/schedule_spec.py -v
```

**Step 3: Implement models**

Add to `membership/models.py` after the Guild class:

New fields on Guild (add to existing Guild model):
- `slug = models.SlugField(max_length=255, unique=True, blank=True)`
- `intro = models.CharField(max_length=500, blank=True)`
- `description = models.TextField(blank=True)`
- `cover_image = models.ImageField(upload_to="guilds/", blank=True)`
- `icon = models.CharField(max_length=100, blank=True)`
- `is_active = models.BooleanField(default=True)`

Add `save()` override to auto-generate slug:
```python
def save(self, *args, **kwargs):
    if not self.slug:
        self.slug = slugify(self.name)
    super().save(*args, **kwargs)
```

New models:
```python
class GuildMembership(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="guild_memberships")
    is_lead = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["guild", "user"]
        ordering = ["guild", "user"]

    def __str__(self):
        role = "Lead" if self.is_lead else "Member"
        return f"{self.user} - {self.guild} ({role})"


class GuildDocument(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE, related_name="documents")
    name = models.CharField(max_length=255)
    file_path = models.FileField(upload_to="guild_docs/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["guild", "name"]

    def __str__(self):
        return self.name


class GuildWishlistItem(models.Model):
    guild = models.ForeignKey(Guild, on_delete=models.CASCADE, related_name="wishlist_items")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="wishlist/", blank=True)
    link = models.URLField(blank=True)
    estimated_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_fulfilled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["guild", "-created_at"]

    def __str__(self):
        return self.name


class MemberSchedule(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member_schedule")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user"]

    def __str__(self):
        return f"Schedule for {self.user}"


class ScheduleBlock(models.Model):
    DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    member_schedule = models.ForeignKey(MemberSchedule, on_delete=models.CASCADE, related_name="blocks")
    day_of_week = models.IntegerField(choices=[(i, name) for i, name in enumerate(DAY_NAMES)])
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_recurring = models.BooleanField(default=True)

    class Meta:
        ordering = ["member_schedule", "day_of_week", "start_time"]

    def __str__(self):
        return f"{self.day_name} {self.start_time}-{self.end_time}"

    @property
    def day_name(self):
        return self.DAY_NAMES[self.day_of_week]
```

**Step 4: Create migration**

```bash
python manage.py makemigrations membership
```

**Step 5: Update admin**

Add inlines and admin classes for new models to `membership/admin.py`.

**Step 6: Run tests**

```bash
pytest tests/membership/guild_enhancements_spec.py tests/membership/schedule_spec.py -v
```

**Step 7: Run full test suite**

```bash
pytest
```

**Step 8: Commit**

```bash
git add membership/ tests/membership/
git commit -m "feat: add GuildMembership, GuildDocument, GuildWishlistItem, MemberSchedule, ScheduleBlock models"
```

---

## Task 4: Billing App — RevenueSplit, Order, Invoice, Payout

**Files:**
- Create: `billing/models.py`
- Create: `billing/admin.py`
- Create: `tests/billing/factories.py`
- Create: `tests/billing/models_spec.py`
- Create: `tests/billing/admin_spec.py`

**Step 1: Write failing tests**

Create `tests/billing/factories.py`:
```python
from __future__ import annotations

from decimal import Decimal

import factory
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from billing.models import Invoice, Order, Payout, RevenueSplit
from tests.core.factories import UserFactory


class RevenueSplitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RevenueSplit

    name = factory.Sequence(lambda n: f"Split {n}")
    splits = [{"entity_type": "org", "entity_id": 1, "percentage": 100}]


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    description = "Test order"
    amount = 5000  # $50.00 in cents
    revenue_split = factory.SubFactory(RevenueSplitFactory)
    status = "on_tab"
    issued_at = factory.LazyFunction(timezone.now)


class InvoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invoice

    user = factory.SubFactory(UserFactory)
    stripe_invoice_id = factory.Sequence(lambda n: f"inv_{n}")
    amount_due = 5000
    amount_paid = 0
    status = "open"
    issued_at = factory.LazyFunction(timezone.now)


class PayoutFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payout

    payee_type = "user"
    payee_id = 1
    amount = 5000
    status = "pending"
    period_start = factory.LazyFunction(lambda: timezone.now().date())
    period_end = factory.LazyFunction(lambda: timezone.now().date())
```

Create `tests/billing/models_spec.py` — test all model behaviors:
- RevenueSplit str, splits validation
- Order str, status methods (is_on_tab, is_paid), formatted_amount
- Invoice str, is_paid, formatted amounts
- Payout str, formatted_amount

**Step 2: Implement billing models**

Implement all 4 models in `billing/models.py` matching the design doc spec. Key points:
- Order uses GenericFK for orderable (content_type + object_id)
- Invoice.line_items is JSONField
- Payout.invoice_ids is JSONField
- All amounts in cents (IntegerField)
- formatted_amount properties return "$X.XX"

**Step 3: Create migration, register admin, run tests, commit**

```bash
python manage.py makemigrations billing
pytest tests/billing/ -v
git add billing/ tests/billing/
git commit -m "feat: add RevenueSplit, Order, Invoice, Payout models"
```

---

## Task 5: Billing App — SubscriptionPlan and MemberSubscription

**Files:**
- Modify: `billing/models.py`
- Create: `tests/billing/subscription_spec.py`
- Modify: `tests/billing/factories.py`

**Step 1: Write failing tests for subscription models**

Test SubscriptionPlan str, is_active default, price formatting.
Test MemberSubscription str, is_active method, relationship to plan.

**Step 2: Implement models**

```python
class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    interval = models.CharField(max_length=20, choices=[("monthly", "Monthly"), ("yearly", "Yearly")])
    stripe_price_id = models.CharField(max_length=255, blank=True)
    plan_type = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class MemberSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member_subscriptions")
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=[...], default="active")
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    next_billing_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
```

**Step 3: Migration, admin, tests, commit**

```bash
python manage.py makemigrations billing
pytest tests/billing/ -v
git add billing/ tests/billing/
git commit -m "feat: add SubscriptionPlan and MemberSubscription models"
```

---

## Task 6: Tools App — Tool, ToolReservation, Rentable, Rental, Document

**Files:**
- Create: `tools/models.py`
- Create: `tools/admin.py`
- Create: `tests/tools/factories.py`
- Create: `tests/tools/models_spec.py`
- Create: `tests/tools/admin_spec.py`

**Step 1: Write failing tests**

Test Tool str, guild relationship, is_reservable/is_rentable defaults.
Test ToolReservation str, is_active method.
Test Rentable str, is_available method, formatted_cost, rental_period_label.
Test Rental str, is_overdue, is_active, is_returned, mark_as_returned, calculate_rental_cost.
Test Document str, GenericFK resolution.

**Step 2: Implement all 5 models in tools/models.py**

Key business logic:
- `Rentable.is_available()` — checks is_active and no active rentals
- `Rental.calculate_rental_cost()` — computes cost based on rental_period (hours/days/weeks)
- `Rental.mark_as_returned()` — updates status and returned_at
- `Rental.is_overdue` — active and due_at in past
- `Document` uses GenericFK (content_type + object_id)

**Step 3: Admin with inlines**

- ToolAdmin with ToolReservation inline
- RentableAdmin
- RentalAdmin with computed fields (overdue status, cost)
- DocumentAdmin

**Step 4: Migration, tests, commit**

```bash
python manage.py makemigrations tools
pytest tests/tools/ -v
git add tools/ tests/tools/
git commit -m "feat: add Tool, ToolReservation, Rentable, Rental, Document models"
```

---

## Task 7: Education App — MakerClass, ClassSession, ClassImage, ClassDiscountCode, Student

**Files:**
- Create: `education/models.py` (class-related models first)
- Create: `education/admin.py`
- Create: `tests/education/factories.py`
- Create: `tests/education/class_spec.py`

**Step 1: Write failing tests**

Test MakerClass str, is_published, has_available_spots.
Test ClassSession belongs to class.
Test ClassDiscountCode calculate_discount for percentage and fixed types.
Test Student is_member (user_id not null).

**Step 2: Implement models**

Key business logic:
- `MakerClass.is_published()` — status == "published"
- `MakerClass.has_available_spots()` — None max_students means unlimited; else count < max
- `ClassDiscountCode.calculate_discount(price)` — percentage or fixed amount
- `Student.is_member` — user_id is not None
- M2M: MakerClass ↔ User (instructors), MakerClass ↔ ClassDiscountCode

**Step 3: Admin with inlines**

- MakerClassAdmin with SessionsInline, StudentsInline, ImagesInline
- ClassDiscountCodeAdmin
- StudentAdmin

**Step 4: Migration, tests, commit**

```bash
python manage.py makemigrations education
pytest tests/education/ -v
git add education/ tests/education/
git commit -m "feat: add MakerClass, ClassSession, ClassImage, ClassDiscountCode, Student models"
```

---

## Task 8: Education App — Orientation and ScheduledOrientation

**Files:**
- Modify: `education/models.py`
- Create: `tests/education/orientation_spec.py`
- Modify: `tests/education/factories.py`

**Step 1: Write failing tests**

Test Orientation str, guild relationship, M2M tools and orienters.
Test ScheduledOrientation str, status transitions, claimed_by tracking.

**Step 2: Implement models**

```python
class Orientation(models.Model):
    guild = models.ForeignKey("membership.Guild", on_delete=models.CASCADE, related_name="orientations")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_minutes = models.IntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    revenue_split = models.ForeignKey("billing.RevenueSplit", null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    tools = models.ManyToManyField("tools.Tool", blank=True, related_name="orientations")
    orienters = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="authorized_orientations")

class ScheduledOrientation(models.Model):
    orientation = models.ForeignKey(Orientation, on_delete=models.CASCADE, related_name="scheduled")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scheduled_orientations")
    scheduled_at = models.DateTimeField()
    claimed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="claimed_orientations")
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[...], default="pending")
    order = models.ForeignKey("billing.Order", null=True, blank=True, on_delete=models.SET_NULL)
```

**Step 3: Migration, admin, tests, commit**

```bash
python manage.py makemigrations education
pytest tests/education/ -v
git add education/ tests/education/
git commit -m "feat: add Orientation and ScheduledOrientation models"
```

---

## Task 9: Outreach App — Lead, Tour, Event, Buyable, BuyablePurchase

**Files:**
- Create: `outreach/models.py`
- Create: `outreach/admin.py`
- Create: `tests/outreach/factories.py`
- Create: `tests/outreach/models_spec.py`
- Create: `tests/outreach/admin_spec.py`

**Step 1: Write failing tests**

Test Lead str, status choices, greenlighted default.
Test Tour str, status choices, guide relationship.
Test Event str, is_published default, guild relationship.
Test Buyable str, guild relationship, is_active default.
Test BuyablePurchase str, relationships.

**Step 2: Implement all 5 models**

Match the Laravel models exactly. Key points:
- Lead.status choices: new, contacted, toured, converted, lost
- Tour.status choices: scheduled, claimed, completed, cancelled, no_show
- Event supports recurring (is_recurring + recurrence_rule)
- Buyable links to RevenueSplit
- BuyablePurchase links to Order

**Step 3: Admin**

- LeadAdmin with ToursInline
- TourAdmin
- EventAdmin with list_filter by guild, is_published
- BuyableAdmin with PurchasesInline
- BuyablePurchaseAdmin

**Step 4: Migration, tests, commit**

```bash
python manage.py makemigrations outreach
pytest tests/outreach/ -v
git add outreach/ tests/outreach/
git commit -m "feat: add Lead, Tour, Event, Buyable, BuyablePurchase models"
```

---

## Task 10: Permissions — django-guardian Groups and Roles

**Files:**
- Create: `membership/management/commands/setup_roles.py`
- Create: `tests/membership/roles_spec.py`

**Step 1: Write failing test**

Test that running `setup_roles` management command creates all 10 groups with correct permissions.

**Step 2: Implement management command**

Create `membership/management/commands/setup_roles.py` that creates groups:
- super-admin (all permissions)
- guild-manager
- class-manager
- orientation-manager
- accountant
- tour-guide
- membership-manager
- guild-lead
- orienter
- teacher

Each group gets the appropriate Django permissions (add/change/view/delete on relevant models) matching the Laravel role permissions documented in the PLOS Technical Manual.

**Step 3: Run tests, commit**

```bash
pytest tests/membership/roles_spec.py -v
git add membership/ tests/membership/
git commit -m "feat: add setup_roles management command with 10 permission groups"
```

---

## Task 11: Stripe Integration — Tab Billing Management Command

**Files:**
- Create: `billing/management/commands/bill_tabs.py`
- Create: `billing/stripe_utils.py`
- Create: `tests/billing/stripe_spec.py`
- Modify: `plfog/urls.py` (add djstripe webhook URL)

**Step 1: Write failing tests**

Test bill_tabs command:
- Collects all "on_tab" orders for each user
- Creates Stripe invoice with line items
- Creates Invoice model record
- Updates order statuses to "billed"
- Handles Stripe API errors gracefully

Test stripe_utils:
- create_invoice_for_user(user, orders) — creates Stripe invoice
- process_payout_report(period_start, period_end) — generates payout records

**Step 2: Implement**

`billing/stripe_utils.py` — wrapper functions around Stripe API:
```python
import stripe
from django.conf import settings

def create_invoice_for_user(user, orders):
    """Create a Stripe invoice for a user's tab orders."""
    # Get or create Stripe customer
    # Add invoice items for each order
    # Finalize and send invoice
    # Return Invoice model instance

def process_payout_report(period_start, period_end):
    """Generate payout records from invoices in the period."""
    # Query paid invoices in period
    # Calculate per-entity amounts from revenue splits
    # Create Payout records
```

`billing/management/commands/bill_tabs.py`:
```python
class Command(BaseCommand):
    help = "Bill all members with outstanding tab balances"

    def handle(self, *args, **options):
        # Get users with on_tab orders
        # For each user, create Stripe invoice
        # Update order statuses
```

**Step 3: Add djstripe webhook URL to urls.py**

```python
path("stripe/", include("djstripe.urls", namespace="djstripe")),
```

**Step 4: Tests, commit**

```bash
pytest tests/billing/stripe_spec.py -v
git add billing/ plfog/urls.py tests/billing/
git commit -m "feat: add Stripe tab billing command and utilities"
```

---

## Task 12: Full Admin Polish and Inlines

**Files:**
- Modify: `billing/admin.py` — finalize all computed fields, inlines
- Modify: `tools/admin.py` — add reservation/rental inlines on Tool
- Modify: `education/admin.py` — add session/student inlines on MakerClass
- Modify: `outreach/admin.py` — add tour inline on Lead, purchase inline on Buyable
- Modify: `membership/admin.py` — add GuildMembership, GuildDocument, GuildWishlistItem inlines on Guild

Ensure all admin classes use `unfold.admin.ModelAdmin`, have appropriate:
- `list_display` with computed fields
- `list_filter` for status/type fields
- `search_fields` for name/email fields
- `fieldsets` for organized editing
- `inlines` for related objects
- `readonly_fields` for computed values

**Step 1: Write admin integration tests**

For each app, test:
- Admin changelist loads (HTTP 200)
- Admin add form loads (HTTP 200)
- All list_display fields render without error

**Step 2: Implement, run tests, commit**

```bash
pytest tests/ -v
git add .
git commit -m "feat: polish admin interfaces with inlines and computed fields"
```

---

## Task 13: Update Existing Tests and Coverage

**Files:**
- Modify: all existing test files as needed
- Modify: `conftest.py` if needed
- Modify: `plfog/auto_admin.py` — add new apps to exclusion or inclusion

**Step 1: Run full test suite with coverage**

```bash
pytest --cov-report=term-missing
```

**Step 2: Fix any coverage gaps**

Add tests for any uncovered lines. Ensure:
- All model `__str__` methods tested
- All model properties tested
- All admin `list_display` computed methods tested
- All management commands tested
- All querysets tested

**Step 3: Run mutation testing**

```bash
pytest --leela --target billing/ --target tools/ --target education/ --target outreach/
```

Fix any surviving mutants.

**Step 4: Run linter and type checker**

```bash
ruff check .
ruff format .
mypy plfog/ core/ membership/ billing/ tools/ education/ outreach/
```

**Step 5: Commit**

```bash
git add .
git commit -m "test: achieve 100% coverage across all apps with mutation testing"
```

---

## Task 14: Create PR

**Step 1: Push branch and create PR**

```bash
git push -u origin feature/full-rebuild
gh pr create --title "feat: Full feature rebuild — billing, tools, education, outreach" --body "$(cat <<'EOF'
## Summary
- Add 4 new Django apps: billing, tools, education, outreach
- Add ~26 new models porting all features from makerspace-tea (Laravel)
- Add django-guardian for object-level permissions with 10 role groups
- Add dj-stripe integration for tab billing system
- Enhance existing Guild model with slug, intro, description, cover_image, M2M members
- Add MemberSchedule/ScheduleBlock for member availability
- Add Setting model for app-wide configuration
- Full admin UI with django-unfold (sidebar nav, inlines, computed fields)
- 100% test coverage with mutation testing

## New Models
**billing:** RevenueSplit, Order, Invoice, Payout, SubscriptionPlan, MemberSubscription
**tools:** Tool, ToolReservation, Rentable, Rental, Document
**education:** MakerClass, ClassSession, ClassImage, ClassDiscountCode, Student, Orientation, ScheduledOrientation
**outreach:** Lead, Tour, Event, Buyable, BuyablePurchase
**membership:** GuildMembership, GuildDocument, GuildWishlistItem, MemberSchedule, ScheduleBlock
**core:** Setting

## Test plan
- [ ] pytest passes with 100% coverage
- [ ] Mutation tests pass
- [ ] ruff check and ruff format clean
- [ ] mypy passes
- [ ] Django checks pass
- [ ] Migrations apply cleanly
- [ ] Admin UI loads all new model pages
EOF
)"
```

---

## Testing Requirements Per Task

Every task follows TDD (test first, then implement). Here are the **minimum required test cases** for each task. These are not optional — the implementing agent must write ALL of these tests.

### Task 2 (Setting) — Minimum 7 tests:
- `it_has_str_representation` — str(setting) returns key
- `it_stores_json_value` — round-trip JSON through DB
- `it_tracks_updated_by` — FK to User
- `it_get_returns_value` — Setting.get("key") returns stored value
- `it_get_returns_default_when_missing` — Setting.get("nope", "fb") == "fb"
- `it_set_creates_setting` — Setting.set creates new record
- `it_set_updates_existing` — Setting.set overwrites existing value
- Admin test: `it_loads_changelist` — GET /admin/core/setting/ returns 200

### Task 3 (Guild enhancements) — Minimum 15 tests:
- Guild: `it_auto_generates_slug`, `it_preserves_existing_slug`, `it_has_intro_description`, `it_defaults_is_active_true`
- GuildMembership: `it_links_user_to_guild`, `it_tracks_is_lead`, `it_has_str`, `it_enforces_unique_together`
- GuildDocument: `it_has_str`, `it_belongs_to_guild`, `it_tracks_uploader`
- GuildWishlistItem: `it_has_str`, `it_defaults_is_fulfilled_false`, `it_belongs_to_guild`
- MemberSchedule: `it_links_to_user`, `it_has_str`
- ScheduleBlock: `it_has_day_name`, `it_has_str`, `it_belongs_to_schedule`
- Admin tests: changelist loads for each new model (5 tests)

### Task 4 (RevenueSplit, Order, Invoice, Payout) — Minimum 20 tests:
- RevenueSplit: `it_has_str`, `it_stores_splits_json`, `it_unique_name`
- Order: `it_has_str`, `it_is_on_tab`, `it_is_paid`, `it_is_failed`, `it_formatted_amount`, `it_belongs_to_user`, `it_belongs_to_revenue_split`, `it_supports_generic_fk_orderable`
- Invoice: `it_has_str`, `it_is_paid`, `it_formatted_amount_due`, `it_formatted_amount_paid`, `it_belongs_to_user`
- Payout: `it_has_str`, `it_formatted_amount`, `it_status_default_pending`, `it_tracks_distributor`
- Admin tests: changelist loads for all 4 models (4 tests)
- **Boundary tests**: Order with 0 amount, negative amount (credit), max amount

### Task 5 (Subscriptions) — Minimum 10 tests:
- SubscriptionPlan: `it_has_str`, `it_defaults_is_active`, `it_has_interval_choices`, `it_has_stripe_price_id`
- MemberSubscription: `it_has_str`, `it_is_active`, `it_is_cancelled`, `it_belongs_to_plan`, `it_belongs_to_user`, `it_tracks_discount_percentage`
- Admin tests: changelist loads (2 tests)

### Task 6 (Tools) — Minimum 25 tests:
- Tool: `it_has_str`, `it_belongs_to_guild`, `it_has_reservable_rentable_flags`, `it_has_estimated_value`, `it_has_owner_type`
- ToolReservation: `it_has_str`, `it_is_active`, `it_is_completed`, `it_is_cancelled`, `it_belongs_to_tool`, `it_belongs_to_user`
- Rentable: `it_has_str`, `it_is_available_when_active_no_rentals`, `it_is_unavailable_when_rented`, `it_is_unavailable_when_inactive`, `it_formatted_cost`, `it_rental_period_label`
- Rental: `it_has_str`, `it_is_overdue`, `it_is_active`, `it_is_returned`, `it_mark_as_returned`, `it_calculate_rental_cost_hours`, `it_calculate_rental_cost_days`, `it_calculate_rental_cost_weeks`, `it_status_badge_color`
- Document: `it_has_str`, `it_resolves_generic_fk`
- Admin tests: changelist loads (5 tests)

### Task 7 (Classes) — Minimum 18 tests:
- MakerClass: `it_has_str`, `it_is_published`, `it_is_not_published_when_draft`, `it_has_available_spots_unlimited`, `it_has_available_spots_with_room`, `it_has_no_available_spots_when_full`, `it_belongs_to_guild`, `it_has_instructors_m2m`, `it_has_discount_codes_m2m`
- ClassSession: `it_has_str`, `it_belongs_to_class`, `it_has_datetime_fields`
- ClassImage: `it_has_str`, `it_has_sort_order`
- ClassDiscountCode: `it_has_str`, `it_calculate_discount_percentage`, `it_calculate_discount_fixed`, `it_calculate_discount_fixed_capped_at_price`
- Student: `it_has_str`, `it_is_member_when_user_set`, `it_is_not_member_when_user_null`
- Admin tests: changelist loads (4 tests)

### Task 8 (Orientations) — Minimum 12 tests:
- Orientation: `it_has_str`, `it_belongs_to_guild`, `it_has_tools_m2m`, `it_has_orienters_m2m`, `it_has_price`, `it_defaults_is_active`
- ScheduledOrientation: `it_has_str`, `it_status_default_pending`, `it_tracks_claimed_by`, `it_tracks_completed_at`, `it_belongs_to_orientation`, `it_links_to_order`
- Admin tests: changelist loads (2 tests)

### Task 9 (Outreach) — Minimum 18 tests:
- Lead: `it_has_str`, `it_status_choices`, `it_defaults_greenlighted_false`, `it_has_latest_tour`
- Tour: `it_has_str`, `it_status_choices`, `it_belongs_to_lead`, `it_tracks_guide`, `it_tracks_completion`
- Event: `it_has_str`, `it_defaults_is_published_false`, `it_belongs_to_guild`, `it_has_recurrence`
- Buyable: `it_has_str`, `it_belongs_to_guild`, `it_defaults_is_active`, `it_has_revenue_split`
- BuyablePurchase: `it_has_str`, `it_belongs_to_buyable`, `it_belongs_to_user`, `it_links_to_order`
- Admin tests: changelist loads (5 tests)

### Task 10 (Permissions) — Minimum 12 tests:
- `it_creates_all_10_groups` — management command creates groups
- One test per group verifying correct permissions (10 tests)
- `it_is_idempotent` — running twice doesn't create duplicates

### Task 11 (Stripe) — Minimum 10 tests:
- bill_tabs: `it_collects_on_tab_orders`, `it_skips_users_with_no_tab`, `it_creates_invoice_records`, `it_updates_order_status_to_billed`, `it_handles_stripe_error_gracefully`
- stripe_utils: `it_creates_stripe_invoice`, `it_generates_payout_report`, `it_handles_empty_period`, `it_calculates_splits_correctly`, `it_handles_negative_orders`

### Task 12 (Admin polish) — Minimum 30 tests:
- For EVERY admin class: changelist loads (200), add form loads (200)
- For every computed `list_display` method: renders without error
- For every inline: renders on parent detail page

### Task 13 (Coverage) — Requirements:
- `pytest --cov-report=term-missing` shows 100% coverage
- `pytest --leela` — zero surviving mutants on all app targets
- `ruff check .` — zero errors
- `ruff format --check .` — zero errors
- `mypy` — zero errors

**Total minimum test count: ~177 tests across all tasks**

---

## Execution Notes

- **Each task is independent enough to commit separately** but they must be done in order (later tasks depend on models from earlier tasks)
- **Task dependency chain:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14
- **Reference the Laravel source** at `/Users/joshplaza/Code/hexagonstorms/makerspace-tea/makerverse/app/Models/` for exact field types and relationships when implementing
- **Follow existing patterns** in `membership/models.py` and `membership/admin.py` for Django idioms (TextChoices, unfold.admin.ModelAdmin, GenericForeignKey patterns)
- **Test style:** pytest-describe with `describe_*` blocks and `it_*` functions, using factories from factory-boy
- **Coverage target:** 100% with branch coverage; mutation testing via pytest-leela
- **Every task MUST have tests written BEFORE implementation** (TDD red-green-refactor)
- **Every task MUST run the full test suite before committing** to catch regressions
- **Stripe tests MUST mock the Stripe API** — never call real Stripe in tests
