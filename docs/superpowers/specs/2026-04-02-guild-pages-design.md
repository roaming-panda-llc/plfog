# Guild Pages Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each guild a member-facing page where the guild lead can post an about/announcement blurb and manage a list of products members can add to their tab.

**Architecture:** Expand the existing stub `guild_detail` view and add an edit page (guild lead only) in the `hub` app. The `billing.Product` model already exists and is reused as-is. One new field is added to `Guild`.

**Tech Stack:** Django, hub app, existing hub CSS classes, billing.Product model

---

## Data Model

### `Guild.about` (new field)
- `TextField`, `blank=True`, `default=""`
- `help_text`: "Member-facing description or announcement shown on the guild page."
- Separate from `Guild.notes`, which is admin-facing staff notes.

### `billing.Product` (no changes)
Existing fields used: `name`, `price`, `guild` (FK), `is_active`. Guild leads manage products through the guild edit page; soft-delete sets `is_active=False`.

---

## Pages & Access

| URL | View | Who can access |
|---|---|---|
| `GET /guilds/<pk>/` | `guild_detail` | All logged-in members |
| `GET /POST /guilds/<pk>/edit/` | `guild_edit` | Guild lead only (403 otherwise) |
| `GET /POST /guilds/<pk>/products/<product_pk>/edit/` | `guild_product_edit` | Guild lead only (403 otherwise) |
| `POST /guilds/<pk>/products/<product_pk>/remove/` | `guild_product_remove` | Guild lead only (403 otherwise) |

### Guild Detail Page (`/guilds/<pk>/`)
- Guild name as page heading
- **About section**: shows `guild.about` text, or a muted "Nothing here yet" placeholder if blank
- **Products section**: lists all `guild.products.filter(is_active=True)`, showing name and price. If no active products, shows a muted placeholder.
- Guild lead sees an "Edit Guild Page" button linking to the edit page. Other members do not see this button.

### Guild Edit Page (`/guilds/<pk>/edit/`)
- Access: `request.user == guild.guild_lead.user`, else `HttpResponseForbidden`
- **About form**: textarea pre-filled with `guild.about`, saves on POST, redirects back to edit page
- **Products section**: table of current active products with Edit and Remove buttons per row
- **Add product form**: name + price fields at the bottom of the products section. Saves on POST, redirects back to edit page.
- Form errors re-render the edit page with error messages.

### Guild Product Edit Page (`/guilds/<pk>/products/<product_pk>/edit/`)
- Access: guild lead only (403 otherwise)
- Form pre-filled with product name and price
- POST saves, redirects back to `/guilds/<pk>/edit/`
- Product must belong to the guild (404 if not)

### Guild Product Remove (`/guilds/<pk>/products/<product_pk>/remove/`)
- POST only (GET returns 405)
- Access: guild lead only (403 otherwise)
- Sets `product.is_active = False`, saves
- Product must belong to the guild (404 if not)
- Redirects to `/guilds/<pk>/edit/`

---

## Forms

### `GuildPageForm` (in `hub/forms.py`)
```python
class GuildPageForm(forms.ModelForm):
    class Meta:
        model = Guild
        fields = ["about"]
        widgets = {"about": forms.Textarea(attrs={"rows": 6})}
```

### `GuildProductForm` (in `hub/forms.py`)
```python
class GuildProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "price"]
```
Validation: price must be > 0 (already enforced by `Product`'s model constraint; form validation re-enforces it with a user-friendly message).

---

## Files Changed

| File | Change |
|---|---|
| `membership/models.py` | Add `Guild.about` field |
| `membership/migrations/NNNN_guild_about.py` | New migration |
| `hub/forms.py` | Add `GuildPageForm`, `GuildProductForm` |
| `hub/views.py` | Expand `guild_detail`; add `guild_edit`, `guild_product_edit`, `guild_product_remove` |
| `hub/urls.py` | Add 3 URL patterns |
| `templates/hub/guild_detail.html` | Full rewrite of stub |
| `templates/hub/guild_edit.html` | New template |
| `templates/hub/guild_product_edit.html` | New template |

No new apps. No new admin registrations (billing admin already shows products).

---

## Access Control

All edit/remove views check `request.user == guild.guild_lead.user`. If the guild has no `guild_lead` set, the edit page is inaccessible (403). Superusers are not special-cased — this is a guild lead feature, not an admin feature.

---

## Testing

BDD spec style, files in `hub/spec/`:

### `describe_guild_detail`
- `it_shows_about_text` — about text visible to any member
- `it_shows_placeholder_when_about_is_blank`
- `it_shows_active_products_only` — inactive products hidden
- `it_shows_no_products_placeholder_when_empty`
- `it_shows_edit_button_for_guild_lead`
- `it_hides_edit_button_for_non_lead`

### `describe_guild_edit`
- `it_requires_login`
- `it_returns_403_for_non_lead`
- `it_renders_form_with_current_about_text`
- `it_saves_about_and_redirects`
- `it_shows_active_products_in_table`
- `it_adds_product_on_post`
- `it_rejects_product_with_zero_price`

### `describe_guild_product_edit`
- `it_requires_login`
- `it_returns_403_for_non_lead`
- `it_returns_404_for_product_not_in_guild`
- `it_renders_form_prefilled`
- `it_saves_and_redirects`

### `describe_guild_product_remove`
- `it_returns_405_on_get`
- `it_returns_403_for_non_lead`
- `it_returns_404_for_product_not_in_guild`
- `it_sets_is_active_false`
- `it_redirects_to_edit_page`
