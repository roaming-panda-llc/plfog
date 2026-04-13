# plfog Frontend Standardization

**Date:** 2026-04-12
**Status:** Draft
**Repo:** Past-Lives-Makerspace/plfog

## Problem

New pages and admin tools in plfog suffer from inconsistent UI because there's no reusable component library or documented frontend standards. Specific issues:

1. **Broken admin toggles** — The "Is Active" toggle in the Add Product inline on the Edit Guild admin page renders incorrectly, while the same field in the Edit Guild form above it works fine. Root cause: `.pl-admin-fieldset input[type="checkbox"]` resets `appearance: none` but the inline form doesn't have `.pl-admin-fieldset` as a parent, so unfold's default toggle CSS conflicts with our overrides.
2. **Horizontal scroll bug** — The Edit Guild admin page has a width overflow causing unnecessary horizontal scrolling, likely from the product inline table or the `.pl-add-product__fields` flex container.
3. **Inline forms always visible** — The Add Product form on the Edit Guild page is always shown. It should be hidden behind an "Add Product" button.
4. **No modal pattern** — Quick actions like "Add to Tab" and "Enter Your Own Price" are rendered as inline forms or trigger page navigations. These should be lightweight modals.
5. **No toast notifications** — After actions like adding an item to a tab, the user is redirected to a new page with a Django message. Should show an inline toast without navigation.
6. **No shared components** — Each template renders forms manually with copy-pasted HTML. No reusable includes for form fields, toggles, modals, or buttons.
7. **No frontend documentation** — Claude and agents have no reference for how to build pages in plfog, leading to inconsistent output.

## Solution: Template Component Library + FRONTEND.md

Approach 1 from brainstorming: reusable Django template includes in `templates/components/`, powered by Alpine.js for interactivity and HTMX for server communication. No new dependencies. A `FRONTEND.md` guide documents every component for Claude/agent consistency.

## Architecture

### Component Library (`templates/components/`)

Five template partials, each self-contained and usable in both hub and admin contexts:

```
templates/
  components/
    modal.html          # Reusable modal container
    toast.html          # Toast notification container (lives in base templates)
    toggle.html         # Standardized toggle switch
    form_field.html     # Standard form field wrapper
    confirm_modal.html  # "Are you sure?" destructive action modal
```

### Toast Utility (`hub/toast.py` or `core/toast.py`)

A small server-side helper for triggering toasts from HTMX responses:

```python
def trigger_toast(response: HttpResponse, message: str, toast_type: str = "success") -> None:
    """Set HX-Trigger header to show a toast notification on the client."""
    import json
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": toast_type}})
```

### FRONTEND.md

Root-level documentation covering the design system, every component with usage examples, and rules for when to use modals vs. inline forms vs. full pages.

---

## Components

### 1. `components/modal.html`

Reusable modal container. Content is passed via Django's `{% include %}` with `{% with %}` parameters or via wrapping the include in a block pattern.

**Parameters:**
- `modal_id` (required) — unique DOM id for Alpine.js targeting
- `modal_title` (required) — heading text
- `modal_size` — `sm` (400px), `md` (560px, default), `lg` (720px)

**Structure:**
```html
{% comment %}
  Usage:
    {% include "components/modal.html" with modal_id="add-to-tab" modal_title="Add to Tab" %}
  
  Open from anywhere:
    <button @click="$dispatch('open-modal', 'add-to-tab')">Add</button>
  
  Modal body is projected via a separate named block or HTMX load.
{% endcomment %}
<div x-data="{ open: false }"
     x-show="open"
     x-transition:enter="modal-enter"
     x-transition:leave="modal-leave"
     @open-modal.window="if ($event.detail === '{{ modal_id }}') open = true"
     @close-modal.window="if ($event.detail === '{{ modal_id }}') open = false"
     @keydown.escape.window="open = false"
     class="pl-modal-backdrop"
     style="display: none;">
    <div class="pl-modal pl-modal--{{ modal_size|default:'md' }}"
         @click.away="open = false">
        <div class="pl-modal__header">
            <h2 class="pl-modal__title">{{ modal_title }}</h2>
            <button type="button" @click="open = false" class="pl-modal__close">&times;</button>
        </div>
        <div class="pl-modal__body" id="{{ modal_id }}-body">
            {{ modal_body }}
        </div>
    </div>
</div>
```

**HTMX pattern for modal content:** Modals can load their body via HTMX when opened. The trigger button uses `hx-get` to fetch a partial template into the modal body, and `hx-trigger="click"` combined with the Alpine dispatch:

```html
<button
    @click="$dispatch('open-modal', 'eyop-modal')"
    hx-get="{% url 'hub_guild_eyop_form' guild.pk %}"
    hx-target="#eyop-modal-body"
    hx-swap="innerHTML">
    +
</button>
```

This keeps modal forms server-rendered (Django form validation works normally) while loading on demand.

**CSS classes:**
- `.pl-modal-backdrop` — fixed overlay, dark semi-transparent background, flex centering
- `.pl-modal` — white/dark card, border-radius, shadow, max-height with overflow-y scroll
- `.pl-modal--sm` / `--md` / `--lg` — max-width variants
- `.pl-modal__header` — flex row with title + close button
- `.pl-modal__body` — padding, contains form or content
- Transitions: fade in backdrop, slide up modal (Alpine.js `x-transition`)

### 2. `components/toast.html`

Toast notification container. Included once in `hub/base.html` and `admin/base.html`. Manages a stack of toasts via Alpine.js, triggered by HTMX response headers or JavaScript events.

**Structure:**
```html
<div x-data="toastManager()" @show-toast.window="add($event.detail)" class="pl-toast-container">
    <template x-for="toast in toasts" :key="toast.id">
        <div class="pl-toast" :class="'pl-toast--' + toast.type"
             x-show="toast.visible"
             x-transition:enter="toast-enter"
             x-transition:leave="toast-leave">
            <span x-text="toast.message"></span>
            <button @click="dismiss(toast.id)" class="pl-toast__close">&times;</button>
        </div>
    </template>
</div>
```

**Alpine.js component:**
```javascript
function toastManager() {
    return {
        toasts: [],
        add(detail) {
            const id = Date.now();
            this.toasts.push({ id, message: detail.message, type: detail.type || 'success', visible: true });
            setTimeout(() => this.dismiss(id), 4000);
        },
        dismiss(id) {
            const toast = this.toasts.find(t => t.id === id);
            if (toast) toast.visible = false;
            setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 300);
        }
    };
}
```

**Server-side trigger:**
```python
from hub.toast import trigger_toast

# In any view returning an HTMX response:
response = HttpResponse(status=204)
trigger_toast(response, "Added to your tab!", "success")
return response
```

The HTMX `htmx:afterRequest` event listener in `hub/base.html` parses `HX-Trigger` headers and dispatches `show-toast` events to Alpine.

**Toast types:** `success` (green accent), `error` (red accent), `info` (blue accent) — matching existing hub message colors.

**Behavior:** Toasts appear top-right of viewport, stack downward, auto-dismiss after 4 seconds, slide-in/fade-out animation. Click X to dismiss immediately.

**Coexistence with Django messages:** Existing `{% if messages %}` blocks in base templates continue to work for full-page loads. Toasts are specifically for HTMX partial responses where the page doesn't reload.

### 3. `components/toggle.html`

Standardized toggle switch that replaces the current one-off `.hub-toggle` in `email_preferences.html` and fixes the admin inline toggle bug.

**Parameters:**
- `field` (required) — Django form BooleanField
- `toggle_label` — display label text
- `toggle_description` — optional description text below the label

**Structure:**
```html
<div class="pl-toggle-row">
    {% if toggle_label %}
    <div class="pl-toggle-info">
        <div class="pl-toggle-label">{{ toggle_label }}</div>
        {% if toggle_description %}
        <div class="pl-toggle-desc">{{ toggle_description }}</div>
        {% endif %}
    </div>
    {% endif %}
    <label class="pl-toggle">
        {{ field }}
        <span class="pl-toggle__slider"></span>
    </label>
</div>
```

**CSS:** Consolidates the existing `.hub-toggle` styles under `.pl-toggle` (the `pl-` prefix is used project-wide for Past Lives components). Works in both hub (dark/light themes) and admin (unfold) contexts. The toggle is 44px wide, 24px tall (current spec), with the Tuscan Yellow checked state.

**Migration:** The existing `.hub-toggle` classes in `email_preferences.html` get replaced with this component. The `.hub-toggle` CSS remains temporarily as an alias mapping to `.pl-toggle` to avoid breaking anything during transition.

### 4. `components/form_field.html`

Standard form field wrapper. Replaces the manual `<div class="hub-form-group"><label>...</label>{{ field }}{% if field.errors %}...{% endif %}</div>` pattern repeated across templates.

**Parameters:**
- `field` (required) — Django form field
- `field_label` — optional label override (defaults to `field.label`)
- `field_hint` — optional hint text

**Structure:**
```html
{% if field.field.widget.input_type == "checkbox" %}
    {% include "components/toggle.html" with field=field toggle_label=field_label|default:field.label toggle_description=field_hint %}
{% else %}
<div class="pl-form-group">
    <label for="{{ field.id_for_label }}" class="pl-form-label">
        {{ field_label|default:field.label }}
    </label>
    {{ field }}
    {% if field.errors %}
    <ul class="pl-field-errors">
        {% for error in field.errors %}
        <li class="pl-field-error">{{ error }}</li>
        {% endfor %}
    </ul>
    {% endif %}
    {% if field_hint %}
    <p class="pl-field-hint">{{ field_hint }}</p>
    {% elif field.help_text %}
    <p class="pl-field-hint">{{ field.help_text }}</p>
    {% endif %}
</div>
{% endif %}
```

**Auto-detection:** If the field is a `BooleanField` (checkbox), it automatically renders as a toggle via `components/toggle.html` instead of a standard input. This is the key fix for the admin inline problem — every checkbox goes through the same rendering path.

**CSS:** `.pl-form-group`, `.pl-form-label`, `.pl-field-errors`, `.pl-field-hint` — consolidated from the existing `.hub-form-group` family. Theme-aware (dark/light).

### 5. `components/confirm_modal.html`

Lightweight "are you sure?" modal for destructive actions. Specialized version of the modal component.

**Parameters:**
- `confirm_id` (required) — unique DOM id
- `confirm_title` — heading (default: "Are you sure?")
- `confirm_message` — body text
- `confirm_action_url` — form POST target
- `confirm_button_text` — button label (default: "Confirm")
- `confirm_button_style` — `danger` (red) or `primary` (yellow)

**Structure:**
```html
<div x-data="{ open: false }"
     x-show="open"
     @open-confirm.window="if ($event.detail === '{{ confirm_id }}') open = true"
     @keydown.escape.window="open = false"
     class="pl-modal-backdrop"
     style="display: none;">
    <div class="pl-modal pl-modal--sm" @click.away="open = false">
        <div class="pl-modal__header">
            <h2 class="pl-modal__title">{{ confirm_title|default:"Are you sure?" }}</h2>
            <button type="button" @click="open = false" class="pl-modal__close">&times;</button>
        </div>
        <div class="pl-modal__body">
            <p>{{ confirm_message }}</p>
            <div class="pl-modal__actions">
                <form method="post" action="{{ confirm_action_url }}">
                    {% csrf_token %}
                    <button type="submit"
                            class="pl-btn pl-btn--{{ confirm_button_style|default:'danger' }}">
                        {{ confirm_button_text|default:"Confirm" }}
                    </button>
                </form>
                <button type="button" @click="open = false" class="pl-btn pl-btn--secondary">Cancel</button>
            </div>
        </div>
    </div>
</div>
```

**Replaces:** The current hand-built delete modal in `guild_product_inline.html` (lines 103-118) which reuses `.changelog-overlay` and `.changelog-modal` classes not designed for this purpose.

---

## Bug Fixes

### Admin Toggle Bug (Edit Guild → Add Product inline)

**Root cause:** The `.pl-admin-fieldset input[type="checkbox"]` rule at `unfold-custom.css:1146` sets `appearance: none` so unfold's custom toggle CSS can render. But the Add Product inline form (`guild_product_inline.html`) doesn't live inside a `.pl-admin-fieldset` container — it renders in `.pl-add-product__fields`. So the checkbox gets default browser rendering mixed with partial unfold styles.

**Fix:** Add a targeted rule for checkboxes inside `.pl-add-product__field` that matches the `.pl-admin-fieldset` treatment. Better yet, replace the raw `{{ field.field }}` rendering in the inline template with the `components/toggle.html` include for the `is_active` field.

### Horizontal Scroll Bug (Edit Guild admin page)

**Root cause:** The `.pl-add-product__fields` flex container with `flex: 1` children and `min-width: 140px` can exceed the viewport on narrow screens. Additionally, unfold's default content area may not have `overflow-x: hidden` applied.

**Fix:** Add `overflow-x: hidden` to the guild admin content wrapper. Constrain `.pl-add-product__fields` with `max-width: 100%` and set field `min-width` to `0` with a flex-basis instead. Audit the products table for the same issue.

### Add Product Form Visibility

**Current:** The Add Product form is always visible below the products table.

**Fix:** Wrap the `.pl-add-product` div in an Alpine.js toggle:
```html
<div x-data="{ showForm: false }">
    <button @click="showForm = !showForm" class="pl-product-btn pl-product-btn--add">
        + Add Product
    </button>
    <div x-show="showForm" x-transition class="pl-add-product">
        ...existing form...
    </div>
</div>
```

The "Add Product" button sits at the bottom of the products table. Clicking reveals the form with a slide-down transition. This is a quick fix using existing patterns — no modal needed since this is an admin-only action on a page already dedicated to editing the guild.

---

## Hub UX Improvements

### Guild Detail Page — Product Interactions

**Current state:** The guild detail page (`hub/guild_detail.html`) has:
- A product grid with "Add to tab" buttons that POST and redirect
- An "Enter Your Own Price" inline form at the bottom

**New design:**

1. **Product cards** get a quantity-aware "Add to Tab" interaction:
   - Clicking "Add to tab" on a product card opens a modal with:
     - Product name and price (read-only display)
     - Quantity picker (number input, default 1)
     - Calculated total (price × quantity, live-updated via Alpine.js)
     - "Add to Cart" button
   - On submit: HTMX POST to a new endpoint, item added to the in-page cart, toast confirmation

2. **"Enter Your Own Price"** moves from an inline form to a modal:
   - A `+` icon button at the top of the Products card (next to the "Products" heading) opens the modal
   - Modal contains the same form fields (description, amount)
   - On submit: HTMX POST, item added to cart, toast confirmation, modal closes

3. **Mini cart** — a persistent cart summary in the page:
   - Appears as a collapsible section at the bottom of the guild page (or as a sticky footer bar)
   - Shows items added this session: name, quantity, unit price, line total
   - "Remove" button per item
   - Total at the bottom
   - "Confirm & Add to Tab" button that POSTs all items as TabEntries in one request
   - Cart state managed in Alpine.js (client-side until confirmed)
   - On confirm: HTMX POST to a batch endpoint, toast "X items added to your tab!", cart clears

**Cart data flow:**
```
User clicks "Add to Tab" on product
  → Modal opens (quantity picker)
  → User confirms → Alpine.js adds to local cart array
  → Toast: "Laser Time x2 added to cart"
  → Cart section updates with new item

User clicks "Confirm & Add to Tab"
  → HTMX POST with cart JSON to /guilds/<pk>/add-to-tab/
  → Server creates TabEntry records via Tab.add_entry()
  → Response: HX-Trigger showToast "3 items added to your tab!"
  → Alpine.js clears cart
  → Tab balance pill in topbar updates (via HX-Trigger or OOB swap)
```

**New endpoints needed:**
- `POST /guilds/<pk>/cart/add/` — validates product + quantity, returns updated cart HTML partial (or 204 with toast)
- `POST /guilds/<pk>/cart/confirm/` — batch creates TabEntries, returns toast trigger
- `GET /guilds/<pk>/eyop-form/` — returns the EYOP form partial for the modal

**Note:** The cart is client-side only (Alpine.js state). Nothing is persisted until "Confirm & Add to Tab." This avoids the need for a Cart model and keeps the existing Tab/TabEntry model clean.

### Tab Detail Page — Void Charge

**Current:** Voiding a charge (if this action exists) uses a form or page navigation.

**New:** A "Void" link on pending tab entries opens a `confirm_modal.html` with a reason field. On confirm: HTMX POST, toast "Charge voided", entry removed from table via HTMX swap.

---

## CSS Organization

### New File: `static/css/components.css`

Shared component styles extracted from `hub.css` and `unfold-custom.css`:

```css
/* components.css — shared across hub and admin */

/* Prefix: pl- (Past Lives) for all component classes */

/* === Modal === */
.pl-modal-backdrop { ... }
.pl-modal { ... }
.pl-modal--sm { max-width: 400px; }
.pl-modal--md { max-width: 560px; }
.pl-modal--lg { max-width: 720px; }
.pl-modal__header { ... }
.pl-modal__title { ... }
.pl-modal__close { ... }
.pl-modal__body { ... }
.pl-modal__actions { ... }

/* === Toast === */
.pl-toast-container { ... }
.pl-toast { ... }
.pl-toast--success { ... }
.pl-toast--error { ... }
.pl-toast--info { ... }

/* === Toggle === */
.pl-toggle-row { ... }
.pl-toggle { ... }
.pl-toggle__slider { ... }

/* === Form Fields === */
.pl-form-group { ... }
.pl-form-label { ... }
.pl-field-errors { ... }
.pl-field-error { ... }
.pl-field-hint { ... }

/* === Buttons === */
.pl-btn { ... }
.pl-btn--primary { ... }
.pl-btn--secondary { ... }
.pl-btn--danger { ... }
.pl-btn--icon { ... }  /* icon-only button (for + button, etc.) */

/* === Cart === */
.pl-cart { ... }
.pl-cart__item { ... }
.pl-cart__total { ... }
.pl-cart__confirm { ... }
```

This file is loaded in both `hub/base.html` and `admin/base.html`, ensuring components look identical in both contexts. Theme-aware via existing `[data-theme="light"]` selectors and CSS variables.

### Migration from existing classes

| Old class | New class | Notes |
|-----------|-----------|-------|
| `.hub-toggle` | `.pl-toggle` | Alias kept temporarily |
| `.hub-toggle-row` | `.pl-toggle-row` | Alias kept temporarily |
| `.hub-toggle__slider` | `.pl-toggle__slider` | Alias kept temporarily |
| `.hub-form-group` | `.pl-form-group` | Alias kept temporarily |
| `.hub-field-errors` | `.pl-field-errors` | Alias kept temporarily |
| `.hub-field-hint` | `.pl-field-hint` | Alias kept temporarily |
| `.hub-btn` | `.pl-btn` | Alias kept temporarily |
| `.changelog-overlay` (modal) | `.pl-modal-backdrop` | Changelog modal migrated |

Old classes remain as aliases in `hub.css` during transition. Once all templates are updated, aliases are removed.

---

## Image Support (Future)

The component library is designed to accommodate image uploads in a future phase:

- **Product cards:** Layout includes space for a product thumbnail. Currently shows product name/price only. Future: 4:3 aspect-ratio image placeholder above the name.
- **Profile avatar:** The `.pl-profile__avatar` component currently renders initials. Future: replace with `<img>` when a profile image exists, fall back to initials.
- **Modal forms:** Form field component can render a file upload input with preview. Not built now, but the `.pl-form-group` pattern accommodates it.
- **No storage decisions made.** Image upload infrastructure (S3, local media, image processing) is a separate spec.

---

## FRONTEND.md

A root-level `FRONTEND.md` that serves as the single reference for anyone (human or AI) building pages in plfog.

### Contents:

1. **Design System Reference**
   - Color palette (CSS variables)
   - Typography (Lato headings, Inter body)
   - Spacing scale (8px grid)
   - Dark/light theme system

2. **Component Catalog**
   - Every component with: description, parameters, usage example, screenshot reference
   - When to use each (modal vs. inline form vs. full page)

3. **Page Patterns**
   - Hub page template (extends `hub/base.html`, card layout)
   - Admin custom view template (extends unfold skeleton)
   - Form page (validation flow, error rendering)

4. **Interaction Patterns**
   - Quick action → Modal + Toast (1-3 fields, no page navigation)
   - Data entry → Inline form (4+ fields, part of a larger page)
   - Complex workflow → Dedicated page
   - Destructive action → Confirm modal
   - Success feedback → Toast notification (HTMX) or Django message (full page load)

5. **HTMX Patterns**
   - Form submission via HTMX (hx-post, hx-target, hx-swap)
   - Toast trigger from server response
   - Partial template rendering for modal content
   - OOB swaps for updating related elements (e.g., tab balance pill)

6. **Rules for Claude / AI Agents**
   - Always use `components/form_field.html` for form fields — never render raw `{{ field }}`
   - Always use `components/modal.html` for modals — never build one-off modal HTML
   - Always use `components/toggle.html` for boolean fields — never render checkboxes directly
   - Use the `pl-` CSS prefix for all new component classes
   - Quick forms (1-3 fields) → modal. Longer forms → inline or dedicated page
   - After mutating actions, return a toast via `trigger_toast()` — don't redirect with Django messages for HTMX requests
   - Test both dark and light themes when adding CSS

---

## Phases

### Phase 1: Foundation (Component Library + Bug Fixes)
- Create `templates/components/` with all five components
- Create `static/css/components.css`
- Add `components/toast.html` to both base templates
- Add toast JS infrastructure (Alpine component + HTMX listener)
- Create `hub/toast.py` utility
- Fix admin toggle bug in Edit Guild → Add Product inline
- Fix horizontal scroll bug on Edit Guild page
- Hide Add Product form behind toggle button
- Migrate `email_preferences.html` to use `components/toggle.html`
- Write `FRONTEND.md`
- Update `CLAUDE.md` to reference `FRONTEND.md`

### Phase 2: Guild Page UX (Modals + Cart)
- Add "Add to Tab" modal with quantity picker on guild product cards
- Add "Enter Your Own Price" modal (+ icon trigger)
- Build mini cart (Alpine.js client-side state)
- Add batch "Confirm & Add to Tab" endpoint
- Add toast notifications for cart actions
- Update tab balance pill via HTMX OOB swap after cart confirm

### Phase 3: Remaining Migrations
- Migrate void charge action to confirm modal
- Migrate existing delete product modal to `components/confirm_modal.html`
- Audit all templates and replace manual form rendering with `components/form_field.html`
- Remove old `.hub-toggle` / `.hub-form-group` CSS aliases once all templates are updated

### Phase 4: Future (Out of Scope)
- Image uploads (products + profiles) — separate spec
- Product creation UI redesign (rethink admin_percent, better field explanations) — after component library is in place, can be done as a follow-up using the new components
