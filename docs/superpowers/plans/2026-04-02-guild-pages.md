# Guild Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each guild a member-facing page where the guild lead can post an about/announcement blurb and manage a list of products members can add to their tab.

**Architecture:** Expand the existing stub `guild_detail` view, add three new views (`guild_edit`, `guild_product_edit`, `guild_product_remove`) in `hub/views.py`, add two forms to `hub/forms.py`, add three URL patterns to `hub/urls.py`, add `Guild.about` field via migration, and write three templates. No new apps or admin pages needed.

**Tech Stack:** Django, pytest-describe BDD tests, factory-boy, existing hub CSS classes (`hub-card`, `hub-form-group`, `hub-btn--primary`, `hub-detail-section`, `hub-detail-label`, `hub-text-muted`)

---

## File Map

| File | Change |
|---|---|
| `membership/models.py` | Add `Guild.about` TextField |
| `membership/migrations/0019_guild_about.py` | New migration |
| `hub/forms.py` | Add `GuildPageForm`, `GuildProductForm` |
| `hub/views.py` | Expand `guild_detail`; add `guild_edit`, `guild_product_edit`, `guild_product_remove` |
| `hub/urls.py` | Add 3 URL patterns |
| `templates/hub/guild_detail.html` | Rewrite stub |
| `templates/hub/guild_edit.html` | New |
| `templates/hub/guild_product_edit.html` | New |
| `tests/hub/guild_pages_spec.py` | New test file |

---

### Task 1: Add `Guild.about` field and migration

**Files:**
- Modify: `membership/models.py` (Guild class, after the `notes` field)
- Create: `membership/migrations/0019_guild_about.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hub/guild_pages_spec.py`:

```python
"""BDD specs for guild pages views."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from membership.models import Guild
from tests.membership.factories import GuildFactory, MemberFactory


@pytest.mark.django_db
def describe_guild_about_field():
    def it_defaults_to_empty_string():
        guild = GuildFactory()
        assert guild.about == ""

    def it_stores_about_text():
        guild = GuildFactory(about="Welcome to our guild!")
        guild.refresh_from_db()
        assert guild.about == "Welcome to our guild!"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_about_field -v
```

Expected: `FAILED` — `TypeError: GuildFactory got unexpected keyword argument 'about'`

- [ ] **Step 3: Add `Guild.about` field**

In `membership/models.py`, add after the `notes` field (line 359):

```python
    notes = models.TextField(blank=True)
    about = models.TextField(
        blank=True,
        default="",
        help_text="Member-facing description or announcement shown on the guild page.",
    )
```

- [ ] **Step 4: Generate migration**

```bash
python manage.py makemigrations membership --name guild_about
```

Expected output: `Migrations for 'membership': membership/migrations/0019_guild_about.py`

- [ ] **Step 5: Run migration**

```bash
python manage.py migrate
```

Expected: `Applying membership.0019_guild_about... OK`

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_about_field -v
```

Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add membership/models.py membership/migrations/0019_guild_about.py tests/hub/guild_pages_spec.py
git commit -m "feat: add Guild.about field for member-facing guild page content"
```

---

### Task 2: Add `GuildPageForm` and `GuildProductForm`

**Files:**
- Modify: `hub/forms.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/hub/guild_pages_spec.py`:

```python
from decimal import Decimal

from billing.models import Product
from hub.forms import GuildPageForm, GuildProductForm
from tests.billing.factories import ProductFactory


@pytest.mark.django_db
def describe_GuildPageForm():
    def it_is_valid_with_about_text():
        guild = GuildFactory(about="Old text")
        form = GuildPageForm(data={"about": "New text"}, instance=guild)
        assert form.is_valid()

    def it_is_valid_with_blank_about():
        guild = GuildFactory()
        form = GuildPageForm(data={"about": ""}, instance=guild)
        assert form.is_valid()

    def it_saves_about_text():
        guild = GuildFactory(about="Old")
        form = GuildPageForm(data={"about": "Updated"}, instance=guild)
        assert form.is_valid()
        form.save()
        guild.refresh_from_db()
        assert guild.about == "Updated"


@pytest.mark.django_db
def describe_GuildProductForm():
    def it_is_valid_with_name_and_positive_price():
        form = GuildProductForm(data={"name": "Wood Laser", "price": "25.00"})
        assert form.is_valid()

    def it_rejects_zero_price():
        form = GuildProductForm(data={"name": "Freebie", "price": "0.00"})
        assert not form.is_valid()
        assert "price" in form.errors

    def it_rejects_negative_price():
        form = GuildProductForm(data={"name": "Bad", "price": "-5.00"})
        assert not form.is_valid()
        assert "price" in form.errors
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/guild_pages_spec.py::describe_GuildPageForm tests/hub/guild_pages_spec.py::describe_GuildProductForm -v
```

Expected: `ImportError: cannot import name 'GuildPageForm' from 'hub.forms'`

- [ ] **Step 3: Add both forms to `hub/forms.py`**

Add at the end of `hub/forms.py` (after `AddTabEntryForm`):

```python
class GuildPageForm(forms.ModelForm):
    """Form for guild leads to edit their guild's member-facing about/announcement text."""

    class Meta:
        model = Guild
        fields = ["about"]
        widgets = {
            "about": forms.Textarea(attrs={"rows": 6, "placeholder": "Tell members what your guild is about..."}),
        }
        labels = {"about": "About / Announcements"}


class GuildProductForm(forms.ModelForm):
    """Form for guild leads to add or edit a product offered by their guild."""

    class Meta:
        model = Product
        fields = ["name", "price"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Laser Cutter — 30 min"}),
            "price": forms.NumberInput(attrs={"placeholder": "0.00", "step": "0.01", "min": "0.01"}),
        }
        labels = {"name": "Product name", "price": "Price ($)"}

    def clean_price(self) -> Decimal:
        price: Decimal = self.cleaned_data["price"]
        if price <= Decimal("0"):
            raise forms.ValidationError("Price must be greater than zero.")
        return price
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/hub/guild_pages_spec.py::describe_GuildPageForm tests/hub/guild_pages_spec.py::describe_GuildProductForm -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add hub/forms.py tests/hub/guild_pages_spec.py
git commit -m "feat: add GuildPageForm and GuildProductForm"
```

---

### Task 3: Expand `guild_detail` view and write the detail template

**Files:**
- Modify: `hub/views.py` (expand `guild_detail`)
- Modify: `templates/hub/guild_detail.html` (full rewrite)

- [ ] **Step 1: Write the failing tests**

Append to `tests/hub/guild_pages_spec.py`:

```python
@pytest.mark.django_db
def describe_guild_detail():
    def _make_lead_client() -> tuple[Client, Guild]:
        """Create a guild lead user and return their logged-in client and guild."""
        lead_member = MemberFactory()
        lead_user = User.objects.create_user(username="lead", password="pass")
        lead_member.user = lead_user
        lead_member.save()
        guild = GuildFactory(guild_lead=lead_member, about="Hello world")
        return Client(), guild, lead_user

    def it_requires_login(client: Client):
        guild = GuildFactory()
        response = client.get(f"/guilds/{guild.pk}/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def it_shows_guild_name(client: Client):
        user = User.objects.create_user(username="viewer", password="pass")
        guild = GuildFactory(name="Woodworking Guild")
        client.login(username="viewer", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert response.status_code == 200
        assert b"Woodworking Guild" in response.content

    def it_shows_about_text(client: Client):
        user = User.objects.create_user(username="v2", password="pass")
        guild = GuildFactory(about="We love wood.")
        client.login(username="v2", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"We love wood." in response.content

    def it_shows_placeholder_when_about_is_blank(client: Client):
        user = User.objects.create_user(username="v3", password="pass")
        guild = GuildFactory(about="")
        client.login(username="v3", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Nothing here yet" in response.content

    def it_shows_active_products_only(client: Client):
        user = User.objects.create_user(username="v4", password="pass")
        guild = GuildFactory()
        active = ProductFactory(guild=guild, name="Laser Cutter", is_active=True)
        ProductFactory(guild=guild, name="Hidden", is_active=False)
        client.login(username="v4", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Laser Cutter" in response.content
        assert b"Hidden" not in response.content

    def it_shows_no_products_placeholder_when_empty(client: Client):
        user = User.objects.create_user(username="v5", password="pass")
        guild = GuildFactory()
        client.login(username="v5", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"No products listed yet" in response.content

    def it_shows_edit_button_for_guild_lead(client: Client):
        lead_member = MemberFactory()
        lead_user = User.objects.create_user(username="gl", password="pass")
        lead_member.user = lead_user
        lead_member.save()
        guild = GuildFactory(guild_lead=lead_member)
        client.login(username="gl", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Edit Guild Page" in response.content

    def it_hides_edit_button_for_non_lead(client: Client):
        User.objects.create_user(username="other", password="pass")
        guild = GuildFactory()
        client.login(username="other", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Edit Guild Page" not in response.content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_detail -v
```

Expected: Several `FAILED` — missing context variables and template content.

- [ ] **Step 3: Expand `guild_detail` in `hub/views.py`**

Replace the existing `guild_detail` function (lines 182–187):

```python
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
```

- [ ] **Step 4: Rewrite `templates/hub/guild_detail.html`**

```html
{% extends "hub/base.html" %}
{% block title %}{{ guild.name }}{% endblock %}

{% block content %}
<div class="hub-card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem;">
        <h1 class="hub-page-title" style="margin-bottom:0;">{{ guild.name }}</h1>
        {% if is_lead %}
        <a href="{% url 'hub_guild_edit' guild.pk %}" class="hub-btn hub-btn--primary">Edit Guild Page</a>
        {% endif %}
    </div>

    <div class="hub-detail-section">
        <h3 class="hub-detail-label">About</h3>
        {% if guild.about %}
        <p>{{ guild.about|linebreaksbr }}</p>
        {% else %}
        <p class="hub-text-muted">Nothing here yet.</p>
        {% endif %}
    </div>

    {% if guild.guild_lead %}
    <div class="hub-detail-section">
        <h3 class="hub-detail-label">Guild Lead</h3>
        <div class="hub-member-row">
            <div class="hub-member-avatar">
                {{ guild.guild_lead.display_name|make_list|first|upper }}
            </div>
            <div class="hub-member-info">
                <span class="hub-member-name">{{ guild.guild_lead.display_name }}</span>
                <span class="hub-badge">Lead</span>
            </div>
        </div>
    </div>
    {% endif %}
</div>

<div class="hub-card" style="margin-top:1.5rem;">
    <h3 class="hub-detail-label" style="margin-bottom:1rem;">Products</h3>
    {% if products %}
    <table style="width:100%;border-collapse:collapse;">
        <thead>
            <tr>
                <th style="text-align:left;padding:0.5rem 0.75rem;color:var(--color-muted,#96ACBB);font-size:0.8125rem;font-weight:500;border-bottom:1px solid rgba(255,255,255,0.08);">Product</th>
                <th style="text-align:right;padding:0.5rem 0.75rem;color:var(--color-muted,#96ACBB);font-size:0.8125rem;font-weight:500;border-bottom:1px solid rgba(255,255,255,0.08);">Price</th>
            </tr>
        </thead>
        <tbody>
            {% for product in products %}
            <tr>
                <td style="padding:0.625rem 0.75rem;border-bottom:1px solid rgba(255,255,255,0.05);">{{ product.name }}</td>
                <td style="padding:0.625rem 0.75rem;text-align:right;border-bottom:1px solid rgba(255,255,255,0.05);">${{ product.price }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p class="hub-text-muted">No products listed yet.</p>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Add URL for `guild_edit` to `hub/urls.py`** (needed so the template `{% url 'hub_guild_edit' %}` resolves during tests — the view itself comes in Task 4)

Add to `hub/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("guilds/voting/", views.guild_voting, name="hub_guild_voting"),
    path("guilds/voting/history/", views.snapshot_history, name="hub_snapshot_history"),
    path("guilds/voting/history/<int:pk>/", views.snapshot_detail, name="hub_snapshot_detail"),
    path("members/", views.member_directory, name="hub_member_directory"),
    path("guilds/<int:pk>/", views.guild_detail, name="hub_guild_detail"),
    path("guilds/<int:pk>/edit/", views.guild_edit, name="hub_guild_edit"),
    path("guilds/<int:pk>/products/<int:product_pk>/edit/", views.guild_product_edit, name="hub_guild_product_edit"),
    path("guilds/<int:pk>/products/<int:product_pk>/remove/", views.guild_product_remove, name="hub_guild_product_remove"),
    path("settings/profile/", views.profile_settings, name="hub_profile_settings"),
    path("settings/emails/", views.email_preferences, name="hub_email_preferences"),
    path("feedback/", views.beta_feedback, name="hub_beta_feedback"),
    path("tab/", views.tab_detail, name="hub_tab_detail"),
    path("tab/history/", views.tab_history, name="hub_tab_history"),
]
```

Add stub views to `hub/views.py` so the URL conf loads (replace with real implementations in Tasks 4–5):

```python
@login_required
def guild_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Guild edit page — guild lead edits about text and manages products."""
    raise NotImplementedError


@login_required
def guild_product_edit(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """Edit a single product belonging to this guild."""
    raise NotImplementedError


@login_required
def guild_product_remove(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """Soft-delete a product (sets is_active=False)."""
    raise NotImplementedError
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_detail -v
```

Expected: `9 passed`

- [ ] **Step 7: Commit**

```bash
git add hub/views.py hub/urls.py templates/hub/guild_detail.html tests/hub/guild_pages_spec.py
git commit -m "feat: expand guild_detail view and template with about + products"
```

---

### Task 4: Implement `guild_edit` view and template

**Files:**
- Modify: `hub/views.py` (replace `guild_edit` stub)
- Create: `templates/hub/guild_edit.html`

- [ ] **Step 1: Write the failing tests**

Append to `tests/hub/guild_pages_spec.py`:

```python
from billing.models import Product as BillingProduct


@pytest.mark.django_db
def describe_guild_edit():
    def _lead_client_and_guild() -> tuple[Client, Guild, User]:
        lead_member = MemberFactory()
        lead_user = User.objects.create_user(username="lead2", password="pass")
        lead_member.user = lead_user
        lead_member.save()
        guild = GuildFactory(guild_lead=lead_member, about="Old text")
        client = Client()
        client.login(username="lead2", password="pass")
        return client, guild, lead_user

    def it_requires_login(client: Client):
        guild = GuildFactory()
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def it_returns_403_for_non_lead(client: Client):
        User.objects.create_user(username="rando", password="pass")
        guild = GuildFactory()
        client.login(username="rando", password="pass")
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert response.status_code == 403

    def it_renders_form_with_current_about_text():
        client, guild, _ = _lead_client_and_guild()
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert response.status_code == 200
        assert b"Old text" in response.content

    def it_saves_about_and_redirects():
        client, guild, _ = _lead_client_and_guild()
        response = client.post(f"/guilds/{guild.pk}/edit/", {"about": "New announcement"})
        assert response.status_code == 302
        assert response["Location"] == f"/guilds/{guild.pk}/edit/"
        guild.refresh_from_db()
        assert guild.about == "New announcement"

    def it_shows_active_products_in_table():
        client, guild, _ = _lead_client_and_guild()
        ProductFactory(guild=guild, name="Laser Session", is_active=True)
        ProductFactory(guild=guild, name="Old Product", is_active=False)
        response = client.get(f"/guilds/{guild.pk}/edit/")
        assert b"Laser Session" in response.content
        assert b"Old Product" not in response.content

    def it_adds_product_on_post():
        client, guild, _ = _lead_client_and_guild()
        response = client.post(
            f"/guilds/{guild.pk}/edit/",
            {"about": guild.about, "add_product": "1", "name": "CNC Hour", "price": "30.00"},
        )
        assert response.status_code == 302
        assert BillingProduct.objects.filter(guild=guild, name="CNC Hour", price="30.00").exists()

    def it_rejects_product_with_zero_price():
        client, guild, _ = _lead_client_and_guild()
        response = client.post(
            f"/guilds/{guild.pk}/edit/",
            {"about": guild.about, "add_product": "1", "name": "Free", "price": "0.00"},
        )
        assert response.status_code == 200
        assert b"greater than zero" in response.content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_edit -v
```

Expected: `FAILED` — `NotImplementedError` from the stub.

- [ ] **Step 3: Replace `guild_edit` stub in `hub/views.py`**

Replace the `guild_edit` stub with:

```python
@login_required
def guild_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Guild edit page — guild lead edits about text and manages products."""
    from django.http import HttpResponseForbidden

    from hub.forms import GuildPageForm, GuildProductForm

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
        {
            **ctx,
            "guild": guild,
            "products": products,
            "page_form": page_form,
            "product_form": product_form,
        },
    )
```

Also add `HttpResponseForbidden` to the top-level imports in `hub/views.py`:

```python
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
```

And add the two new form imports to the existing import line:

```python
from hub.forms import AddTabEntryForm, BetaFeedbackForm, EmailPreferencesForm, GuildPageForm, GuildProductForm, ProfileSettingsForm, VotePreferenceForm
```

Remove the local `from hub.forms import GuildPageForm, GuildProductForm` inside `guild_edit` now that it's at the top.

- [ ] **Step 4: Create `templates/hub/guild_edit.html`**

```html
{% extends "hub/base.html" %}
{% block title %}Edit — {{ guild.name }}{% endblock %}

{% block content %}
<div class="hub-card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem;">
        <h1 class="hub-page-title" style="margin-bottom:0;">Edit Guild Page</h1>
        <a href="{% url 'hub_guild_detail' guild.pk %}" class="hub-btn">View Page</a>
    </div>

    <h3 class="hub-detail-label" style="margin-bottom:0.75rem;">About / Announcements</h3>
    <form method="post" class="hub-form">
        {% csrf_token %}
        {% for field in page_form %}
        <div class="hub-form-group">
            <label for="{{ field.id_for_label }}">{{ field.label }}</label>
            {{ field }}
            {% if field.errors %}
            <ul class="hub-field-errors">
                {% for error in field.errors %}
                <li>{{ error }}</li>
                {% endfor %}
            </ul>
            {% endif %}
        </div>
        {% endfor %}
        <div style="margin-top:1rem;">
            <button type="submit" class="hub-btn hub-btn--primary">Save</button>
        </div>
    </form>
</div>

<div class="hub-card" style="margin-top:1.5rem;">
    <h3 class="hub-detail-label" style="margin-bottom:1rem;">Products</h3>

    {% if products %}
    <table style="width:100%;border-collapse:collapse;margin-bottom:1.5rem;">
        <thead>
            <tr>
                <th style="text-align:left;padding:0.5rem 0.75rem;color:var(--color-muted,#96ACBB);font-size:0.8125rem;font-weight:500;border-bottom:1px solid rgba(255,255,255,0.08);">Product</th>
                <th style="text-align:right;padding:0.5rem 0.75rem;color:var(--color-muted,#96ACBB);font-size:0.8125rem;font-weight:500;border-bottom:1px solid rgba(255,255,255,0.08);">Price</th>
                <th style="padding:0.5rem 0.75rem;border-bottom:1px solid rgba(255,255,255,0.08);"></th>
            </tr>
        </thead>
        <tbody>
            {% for product in products %}
            <tr>
                <td style="padding:0.625rem 0.75rem;border-bottom:1px solid rgba(255,255,255,0.05);">{{ product.name }}</td>
                <td style="padding:0.625rem 0.75rem;text-align:right;border-bottom:1px solid rgba(255,255,255,0.05);">${{ product.price }}</td>
                <td style="padding:0.625rem 0.75rem;text-align:right;border-bottom:1px solid rgba(255,255,255,0.05);white-space:nowrap;">
                    <a href="{% url 'hub_guild_product_edit' guild.pk product.pk %}" style="color:#EEB44B;font-size:0.875rem;margin-right:0.75rem;">Edit</a>
                    <form method="post" action="{% url 'hub_guild_product_remove' guild.pk product.pk %}" style="display:inline;">
                        {% csrf_token %}
                        <button type="submit" style="background:none;border:none;color:#96ACBB;font-size:0.875rem;cursor:pointer;padding:0;" onclick="return confirm('Remove {{ product.name }}?')">Remove</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p class="hub-text-muted" style="margin-bottom:1.5rem;">No products yet. Add one below.</p>
    {% endif %}

    <h3 class="hub-detail-label" style="margin-bottom:0.75rem;">Add Product</h3>
    <form method="post" class="hub-form">
        {% csrf_token %}
        <input type="hidden" name="add_product" value="1">
        {% for field in product_form %}
        <div class="hub-form-group">
            <label for="{{ field.id_for_label }}">{{ field.label }}</label>
            {{ field }}
            {% if field.errors %}
            <ul class="hub-field-errors">
                {% for error in field.errors %}
                <li>{{ error }}</li>
                {% endfor %}
            </ul>
            {% endif %}
        </div>
        {% endfor %}
        {% if product_form.non_field_errors %}
        <ul class="hub-field-errors">
            {% for error in product_form.non_field_errors %}
            <li>{{ error }}</li>
            {% endfor %}
        </ul>
        {% endif %}
        <div style="margin-top:1rem;">
            <button type="submit" class="hub-btn hub-btn--primary">Add Product</button>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_edit -v
```

Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add hub/views.py hub/forms.py templates/hub/guild_edit.html tests/hub/guild_pages_spec.py
git commit -m "feat: add guild_edit view and template"
```

---

### Task 5: Implement `guild_product_edit` and `guild_product_remove` views and template

**Files:**
- Modify: `hub/views.py` (replace stubs)
- Create: `templates/hub/guild_product_edit.html`

- [ ] **Step 1: Write the failing tests**

Append to `tests/hub/guild_pages_spec.py`:

```python
@pytest.mark.django_db
def describe_guild_product_edit():
    def _setup() -> tuple[Client, Guild, BillingProduct]:
        lead_member = MemberFactory()
        lead_user = User.objects.create_user(username="lead3", password="pass")
        lead_member.user = lead_user
        lead_member.save()
        guild = GuildFactory(guild_lead=lead_member)
        product = ProductFactory(guild=guild, name="Old Name", price="15.00")
        client = Client()
        client.login(username="lead3", password="pass")
        return client, guild, product

    def it_requires_login(client: Client):
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/edit/")
        assert response.status_code == 302

    def it_returns_403_for_non_lead(client: Client):
        User.objects.create_user(username="rando2", password="pass")
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        client.login(username="rando2", password="pass")
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/edit/")
        assert response.status_code == 403

    def it_returns_404_for_product_not_in_guild():
        client, guild, _ = _setup()
        other_product = ProductFactory()
        response = client.get(f"/guilds/{guild.pk}/products/{other_product.pk}/edit/")
        assert response.status_code == 404

    def it_renders_form_prefilled():
        client, guild, product = _setup()
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/edit/")
        assert response.status_code == 200
        assert b"Old Name" in response.content

    def it_saves_and_redirects():
        client, guild, product = _setup()
        response = client.post(
            f"/guilds/{guild.pk}/products/{product.pk}/edit/",
            {"name": "New Name", "price": "20.00"},
        )
        assert response.status_code == 302
        assert response["Location"] == f"/guilds/{guild.pk}/edit/"
        product.refresh_from_db()
        assert product.name == "New Name"
        assert product.price == Decimal("20.00")


@pytest.mark.django_db
def describe_guild_product_remove():
    def _setup() -> tuple[Client, Guild, BillingProduct]:
        lead_member = MemberFactory()
        lead_user = User.objects.create_user(username="lead4", password="pass")
        lead_member.user = lead_user
        lead_member.save()
        guild = GuildFactory(guild_lead=lead_member)
        product = ProductFactory(guild=guild, is_active=True)
        client = Client()
        client.login(username="lead4", password="pass")
        return client, guild, product

    def it_returns_405_on_get():
        client, guild, product = _setup()
        response = client.get(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        assert response.status_code == 405

    def it_returns_403_for_non_lead(client: Client):
        User.objects.create_user(username="rando3", password="pass")
        guild = GuildFactory()
        product = ProductFactory(guild=guild)
        client.login(username="rando3", password="pass")
        response = client.post(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        assert response.status_code == 403

    def it_returns_404_for_product_not_in_guild():
        client, guild, _ = _setup()
        other_product = ProductFactory()
        response = client.post(f"/guilds/{guild.pk}/products/{other_product.pk}/remove/")
        assert response.status_code == 404

    def it_sets_is_active_false():
        client, guild, product = _setup()
        client.post(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        product.refresh_from_db()
        assert product.is_active is False

    def it_redirects_to_edit_page():
        client, guild, product = _setup()
        response = client.post(f"/guilds/{guild.pk}/products/{product.pk}/remove/")
        assert response.status_code == 302
        assert response["Location"] == f"/guilds/{guild.pk}/edit/"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_product_edit tests/hub/guild_pages_spec.py::describe_guild_product_remove -v
```

Expected: `FAILED` — `NotImplementedError` from stubs.

- [ ] **Step 3: Replace stubs in `hub/views.py`**

Replace `guild_product_edit` stub:

```python
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
```

Replace `guild_product_remove` stub:

```python
@login_required
def guild_product_remove(request: HttpRequest, pk: int, product_pk: int) -> HttpResponse:
    """Soft-delete a product (sets is_active=False)."""
    from django.http import HttpResponseNotAllowed

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
```

Add `HttpResponseNotAllowed` to the top-level import in `hub/views.py`:

```python
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
```

- [ ] **Step 4: Create `templates/hub/guild_product_edit.html`**

```html
{% extends "hub/base.html" %}
{% block title %}Edit Product — {{ guild.name }}{% endblock %}

{% block content %}
<div class="hub-card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem;">
        <h1 class="hub-page-title" style="margin-bottom:0;">Edit Product</h1>
        <a href="{% url 'hub_guild_edit' guild.pk %}" class="hub-btn">Back to Edit Page</a>
    </div>

    <form method="post" class="hub-form">
        {% csrf_token %}
        {% for field in form %}
        <div class="hub-form-group">
            <label for="{{ field.id_for_label }}">{{ field.label }}</label>
            {{ field }}
            {% if field.errors %}
            <ul class="hub-field-errors">
                {% for error in field.errors %}
                <li>{{ error }}</li>
                {% endfor %}
            </ul>
            {% endif %}
        </div>
        {% endfor %}
        {% if form.non_field_errors %}
        <ul class="hub-field-errors">
            {% for error in form.non_field_errors %}
            <li>{{ error }}</li>
            {% endfor %}
        </ul>
        {% endif %}
        <div style="margin-top:1.5rem;">
            <button type="submit" class="hub-btn hub-btn--primary">Save Changes</button>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/hub/guild_pages_spec.py::describe_guild_product_edit tests/hub/guild_pages_spec.py::describe_guild_product_remove -v
```

Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add hub/views.py templates/hub/guild_product_edit.html tests/hub/guild_pages_spec.py
git commit -m "feat: add guild_product_edit and guild_product_remove views"
```

---

### Task 6: Full test suite pass, version bump, and final commit

**Files:**
- Modify: `plfog/version.py`

- [ ] **Step 1: Run the full test suite**

```bash
pytest --tb=short -q
```

Expected: All tests pass, 0 failures. Fix any failures before proceeding.

- [ ] **Step 2: Run type checking**

```bash
mypy .
```

Expected: No new errors. Fix any type errors before proceeding.

- [ ] **Step 3: Run linting**

```bash
ruff check . && ruff format --check .
```

Expected: No errors. If there are format issues, run `ruff format .` then re-check.

- [ ] **Step 4: Bump version in `plfog/version.py`**

The current version is `1.3.0`. This feature ships as part of the same PR, so update the existing `1.3.0` changelog entry to add guild pages entries:

```python
VERSION = "1.3.0"

CHANGELOG: list[dict[str, str | list[str]]] = [
    {
        "version": "1.3.0",
        "date": "2026-04-02",
        "title": "Tab Billing System",
        "changes": [
            # ... existing entries stay, add:
            "Guild pages — each guild now has its own page with an about section and a list of products",
            "Guild leads can edit their guild's about text and manage their product listings directly from the guild page",
        ],
    },
    # ... rest of changelog unchanged
]
```

- [ ] **Step 5: Final commit**

```bash
git add plfog/version.py
git commit -m "feat: guild pages — about section and products for guild leads (v1.3.0)"
```
