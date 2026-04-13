# Frontend Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable template component library (modal, toast, toggle, form_field, confirm_modal), fix admin UI bugs, redesign the guild page product interaction with a client-side cart, and write FRONTEND.md so Claude/agents produce consistent UI.

**Architecture:** Django template includes in `templates/components/` with Alpine.js for interactivity and HTMX for server communication. No new Python dependencies. A `hub/toast.py` utility sets `HX-Trigger` headers to fire toast notifications. Cart state is client-side Alpine.js only — nothing persisted until "Confirm & Add to Tab" POST. All component CSS lives in a new shared `static/css/components.css` loaded by both hub and admin base templates.

**Tech Stack:** Django 5.x templates, Alpine.js 3.x, HTMX, CSS custom properties, pytest-describe (BDD)

**Spec:** `docs/superpowers/specs/2026-04-12-frontend-standardization-design.md`

---

## File Map

### New Files

| File | Purpose |
|------|---------|
| `static/css/components.css` | Shared component styles (modal, toast, toggle, form field, buttons, cart) |
| `templates/components/modal.html` | Reusable modal container |
| `templates/components/toast.html` | Toast notification container (included in base templates) |
| `templates/components/toggle.html` | Standardized toggle switch for boolean fields |
| `templates/components/form_field.html` | Standard form field wrapper with auto-toggle for checkboxes |
| `templates/components/confirm_modal.html` | "Are you sure?" destructive action modal |
| `hub/toast.py` | Server-side `trigger_toast()` utility for HTMX responses |
| `tests/hub/toast_spec.py` | Tests for toast utility |
| `tests/hub/cart_views_spec.py` | Tests for new cart endpoints |
| `templates/hub/partials/eyop_form.html` | EYOP form partial for modal loading via HTMX |
| `templates/hub/partials/cart.html` | Cart section partial |
| `FRONTEND.md` | Design system + component catalog + rules for Claude/agents |

### Modified Files

| File | Changes |
|------|---------|
| `templates/hub/base.html` | Add `components/toast.html` include, Alpine toast manager, HTMX toast listener |
| `templates/admin/base.html` | Add `components/toast.html` include, load Alpine.js, toast manager |
| `static/css/hub.css` | Add alias mappings from old `.hub-toggle` to new `.pl-toggle` classes |
| `static/css/unfold-custom.css` | Fix inline checkbox/toggle bug, fix horizontal scroll, hide Add Product form by default |
| `templates/hub/email_preferences.html` | Migrate to `components/toggle.html` |
| `templates/hub/guild_detail.html` | Rewrite with modal triggers, cart section, HTMX endpoints |
| `templates/hub/tab_detail.html` | Add void confirm modal |
| `templates/admin/membership/guild_product_inline.html` | Migrate delete modal to `components/confirm_modal.html`, add Alpine toggle for Add Product |
| `hub/views.py` | Add `guild_cart_add`, `guild_cart_confirm`, `guild_eyop_form` view functions |
| `hub/urls.py` | Add new cart/EYOP URL patterns |
| `tests/hub/guild_pages_spec.py` | Update existing tests for new redirect behavior, add cart endpoint tests |
| `CLAUDE.md` | Add reference to `FRONTEND.md` |

---

## Phase 1: Foundation

### Task 1: Create `components.css` with Modal Styles

**Files:**
- Create: `static/css/components.css`

- [ ] **Step 1: Create the shared components CSS file**

Create `static/css/components.css` with the modal, toast, toggle, form field, button, and cart styles. This is the core CSS for all components.

```css
/* components.css — Past Lives shared component library
 *
 * Loaded by both hub/base.html and admin/base.html.
 * All classes use the pl- prefix.
 * Theme-aware via [data-theme="light"] selectors and CSS variables from hub.css.
 */

/* ========================================
   Modal
   ======================================== */
.pl-modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.6);
    padding: 1rem;
}

.pl-modal {
    background: var(--hub-card-bg, #0f2d44);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    width: 100%;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
}

.pl-modal--sm { max-width: 400px; }
.pl-modal--md { max-width: 560px; }
.pl-modal--lg { max-width: 720px; }

.pl-modal__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.pl-modal__title {
    font-family: 'Lato', system-ui, sans-serif;
    font-size: 1.125rem;
    font-weight: 700;
    color: var(--hub-text, #F4EFDD);
    margin: 0;
}

.pl-modal__close {
    background: none;
    border: none;
    color: var(--hub-text-muted, #96ACBB);
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0;
    line-height: 1;
}

.pl-modal__close:hover {
    color: var(--hub-text, #F4EFDD);
}

.pl-modal__body {
    padding: 1.5rem;
}

.pl-modal__actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 1.5rem;
}

/* Modal transitions */
.modal-enter {
    transition: opacity 0.2s ease;
}

.modal-leave {
    transition: opacity 0.15s ease;
}

/* ========================================
   Toast
   ======================================== */
.pl-toast-container {
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 600;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    pointer-events: none;
}

.pl-toast {
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    color: #F4EFDD;
    background: var(--hub-card-bg, #0f2d44);
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    min-width: 250px;
    max-width: 400px;
}

.pl-toast--success {
    border-left: 3px solid #4ade80;
}

.pl-toast--error {
    border-left: 3px solid #f87171;
}

.pl-toast--info {
    border-left: 3px solid #60a5fa;
}

.pl-toast__close {
    background: none;
    border: none;
    color: var(--hub-text-muted, #96ACBB);
    font-size: 1.125rem;
    cursor: pointer;
    padding: 0;
    margin-left: auto;
    line-height: 1;
}

.pl-toast__close:hover {
    color: var(--hub-text, #F4EFDD);
}

/* Toast transitions */
.toast-enter {
    transition: all 0.3s ease;
}

.toast-leave {
    transition: all 0.2s ease;
}

/* ========================================
   Toggle
   ======================================== */
.pl-toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.pl-toggle-row:last-child {
    border-bottom: none;
}

.pl-toggle-label {
    font-size: 0.9375rem;
    font-weight: 400;
    color: var(--hub-text, #F4EFDD);
}

.pl-toggle-desc {
    font-size: 0.8125rem;
    color: var(--hub-text-muted, #96ACBB);
    margin-top: 0.125rem;
}

.pl-toggle {
    position: relative;
    display: inline-block;
    width: 44px;
    height: 24px;
    flex-shrink: 0;
}

.pl-toggle input {
    opacity: 0;
    width: 0;
    height: 0;
    position: absolute;
}

.pl-toggle__slider {
    position: absolute;
    cursor: pointer;
    inset: 0;
    background-color: rgba(255, 255, 255, 0.15);
    border-radius: 24px;
    transition: background-color 0.2s ease;
}

.pl-toggle__slider::before {
    content: "";
    position: absolute;
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: #fff;
    border-radius: 50%;
    transition: transform 0.2s ease;
}

.pl-toggle input:checked + .pl-toggle__slider {
    background-color: var(--color-tuscan-yellow, #EEB44B);
}

.pl-toggle input:checked + .pl-toggle__slider::before {
    transform: translateX(20px);
}

.pl-toggle input:focus-visible + .pl-toggle__slider {
    box-shadow: 0 0 0 3px rgba(238, 180, 75, 0.3);
}

/* ========================================
   Form Field
   ======================================== */
.pl-form-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    margin-bottom: 1rem;
}

.pl-form-group:last-child {
    margin-bottom: 0;
}

.pl-form-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--hub-text-muted, #96ACBB);
}

.pl-form-group input,
.pl-form-group select,
.pl-form-group textarea {
    background: var(--hub-input-bg, rgba(255, 255, 255, 0.06));
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    color: var(--hub-text, #F4EFDD);
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    width: 100%;
    transition: border-color 0.15s ease;
}

.pl-form-group input:focus,
.pl-form-group select:focus,
.pl-form-group textarea:focus {
    border-color: var(--color-tuscan-yellow, #EEB44B);
    outline: none;
    box-shadow: 0 0 0 3px rgba(238, 180, 75, 0.15);
}

.pl-field-errors {
    list-style: none;
    margin: 0;
    padding: 0;
}

.pl-field-error {
    font-size: 0.8125rem;
    color: #f87171;
}

.pl-field-hint {
    font-size: 0.8125rem;
    color: var(--hub-text-muted, #96ACBB);
    margin: 0;
}

/* ========================================
   Buttons
   ======================================== */
.pl-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.5rem 1.25rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.15s ease;
    white-space: nowrap;
    min-height: 36px;
    text-decoration: none;
}

.pl-btn--primary {
    background: var(--color-tuscan-yellow, #EEB44B);
    color: #092E4C;
}

.pl-btn--primary:hover {
    background: #f5c86a;
}

.pl-btn--secondary {
    background: rgba(255, 255, 255, 0.08);
    color: var(--hub-text, #F4EFDD);
}

.pl-btn--secondary:hover {
    background: rgba(255, 255, 255, 0.12);
}

.pl-btn--danger {
    background: #dc2626;
    color: #fff;
}

.pl-btn--danger:hover {
    background: #ef4444;
}

.pl-btn--icon {
    width: 36px;
    height: 36px;
    padding: 0;
    border-radius: 50%;
}

/* ========================================
   Cart
   ======================================== */
.pl-cart {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 1.25rem;
    background: rgba(255, 255, 255, 0.02);
}

.pl-cart__title {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--hub-text-muted, #96ACBB);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 0 0 1rem;
}

.pl-cart__empty {
    font-size: 0.875rem;
    color: var(--hub-text-muted, #96ACBB);
}

.pl-cart__items {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
}

.pl-cart__item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    font-size: 0.875rem;
}

.pl-cart__item:last-child {
    border-bottom: none;
}

.pl-cart__item-name {
    flex: 1;
    color: var(--hub-text, #F4EFDD);
}

.pl-cart__item-qty {
    color: var(--hub-text-muted, #96ACBB);
    font-size: 0.8125rem;
}

.pl-cart__item-price {
    color: var(--hub-text, #F4EFDD);
    font-weight: 500;
    min-width: 60px;
    text-align: right;
}

.pl-cart__item-remove {
    background: none;
    border: none;
    color: var(--hub-text-muted, #96ACBB);
    cursor: pointer;
    padding: 0.25rem;
    font-size: 0.75rem;
}

.pl-cart__item-remove:hover {
    color: #f87171;
}

.pl-cart__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 0.75rem;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.pl-cart__total {
    font-size: 1rem;
    font-weight: 700;
    color: var(--hub-text, #F4EFDD);
}

/* ========================================
   Quantity picker (inside modal)
   ======================================== */
.pl-qty {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.pl-qty__btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.06);
    color: var(--hub-text, #F4EFDD);
    font-size: 1.125rem;
    cursor: pointer;
}

.pl-qty__btn:hover {
    background: rgba(255, 255, 255, 0.1);
}

.pl-qty__value {
    font-size: 1rem;
    font-weight: 600;
    color: var(--hub-text, #F4EFDD);
    min-width: 2rem;
    text-align: center;
}

/* ========================================
   Light theme overrides
   ======================================== */
[data-theme="light"] .pl-modal {
    background: #fff;
    border-color: #e5e7eb;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

[data-theme="light"] .pl-modal__title {
    color: #1f2937;
}

[data-theme="light"] .pl-modal__header {
    border-color: #e5e7eb;
}

[data-theme="light"] .pl-modal__close {
    color: #6b7280;
}

[data-theme="light"] .pl-modal__close:hover {
    color: #1f2937;
}

[data-theme="light"] .pl-toast {
    background: #fff;
    border-color: #e5e7eb;
    color: #1f2937;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

[data-theme="light"] .pl-toast__close {
    color: #6b7280;
}

[data-theme="light"] .pl-toggle__slider {
    background-color: #ccc;
}

[data-theme="light"] .pl-toggle-row {
    border-color: #e5e7eb;
}

[data-theme="light"] .pl-toggle-label {
    color: #1f2937;
}

[data-theme="light"] .pl-toggle-desc {
    color: #6b7280;
}

[data-theme="light"] .pl-form-label {
    color: #6b7280;
}

[data-theme="light"] .pl-form-group input,
[data-theme="light"] .pl-form-group select,
[data-theme="light"] .pl-form-group textarea {
    background: #fff;
    border-color: #d1d5db;
    color: #1f2937;
}

[data-theme="light"] .pl-field-hint {
    color: #6b7280;
}

[data-theme="light"] .pl-btn--secondary {
    background: #f3f4f6;
    color: #1f2937;
}

[data-theme="light"] .pl-btn--secondary:hover {
    background: #e5e7eb;
}

[data-theme="light"] .pl-cart {
    border-color: #e5e7eb;
    background: #fafafa;
}

[data-theme="light"] .pl-cart__title {
    color: #6b7280;
}

[data-theme="light"] .pl-cart__item {
    border-color: #e5e7eb;
}

[data-theme="light"] .pl-cart__item-name {
    color: #1f2937;
}

[data-theme="light"] .pl-cart__item-qty {
    color: #6b7280;
}

[data-theme="light"] .pl-cart__item-price {
    color: #1f2937;
}

[data-theme="light"] .pl-cart__footer {
    border-color: #e5e7eb;
}

[data-theme="light"] .pl-cart__total {
    color: #1f2937;
}

[data-theme="light"] .pl-qty__btn {
    border-color: #d1d5db;
    background: #fff;
    color: #1f2937;
}

[data-theme="light"] .pl-qty__btn:hover {
    background: #f3f4f6;
}

[data-theme="light"] .pl-qty__value {
    color: #1f2937;
}

[data-theme="light"] .pl-cart__empty {
    color: #6b7280;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/css/components.css
git commit -m "feat: add shared components.css with modal, toast, toggle, form, button, and cart styles"
```

---

### Task 2: Create Template Components

**Files:**
- Create: `templates/components/modal.html`
- Create: `templates/components/toggle.html`
- Create: `templates/components/form_field.html`
- Create: `templates/components/confirm_modal.html`
- Create: `templates/components/toast.html`

- [ ] **Step 1: Create the modal component**

Create `templates/components/modal.html`:

```html
{% comment %}
Reusable modal container.

Parameters (pass via {% include ... with %}):
  modal_id      — required, unique DOM id
  modal_title   — required, heading text
  modal_size    — optional: "sm" (400px), "md" (560px, default), "lg" (720px)

Open from anywhere:
  <button @click="$dispatch('open-modal', 'my-modal-id')">Open</button>

Modal body is loaded via HTMX into #<modal_id>-body, or set via modal_body variable.
{% endcomment %}
<div x-data="{ open: false }"
     x-show="open"
     x-transition:enter="modal-enter"
     x-transition:leave="modal-leave"
     @open-modal.window="if ($event.detail === '{{ modal_id }}') open = true"
     @close-modal.window="if ($event.detail === '{{ modal_id }}') open = false"
     @keydown.escape.window="open = false"
     class="pl-modal-backdrop"
     style="display: none;"
     role="dialog"
     aria-modal="true"
     aria-labelledby="{{ modal_id }}-title">
    <div class="pl-modal pl-modal--{{ modal_size|default:'md' }}" @click.outside="open = false">
        <div class="pl-modal__header">
            <h2 class="pl-modal__title" id="{{ modal_id }}-title">{{ modal_title }}</h2>
            <button type="button" @click="open = false" class="pl-modal__close" aria-label="Close">&times;</button>
        </div>
        <div class="pl-modal__body" id="{{ modal_id }}-body">
            {{ modal_body }}
        </div>
    </div>
</div>
```

- [ ] **Step 2: Create the toggle component**

Create `templates/components/toggle.html`:

```html
{% comment %}
Standardized toggle switch for boolean form fields.

Parameters (pass via {% include ... with %}):
  field              — required, Django BooleanField
  toggle_label       — optional, display label text
  toggle_description — optional, description below label
{% endcomment %}
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

- [ ] **Step 3: Create the form field component**

Create `templates/components/form_field.html`:

```html
{% comment %}
Standard form field wrapper with auto-toggle for checkbox fields.

Parameters (pass via {% include ... with %}):
  field       — required, Django form field
  field_label — optional, label override (defaults to field.label)
  field_hint  — optional, hint text (defaults to field.help_text)
{% endcomment %}
{% if field.field.widget.input_type == "checkbox" %}
    {% include "components/toggle.html" with field=field toggle_label=field_label|default:field.label toggle_description=field_hint|default:field.help_text %}
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

- [ ] **Step 4: Create the confirm modal component**

Create `templates/components/confirm_modal.html`:

```html
{% comment %}
Destructive action confirmation modal.

Parameters (pass via {% include ... with %}):
  confirm_id           — required, unique DOM id
  confirm_title        — optional, heading (default: "Are you sure?")
  confirm_message      — required, body text
  confirm_action_url   — required, form POST target
  confirm_button_text  — optional, button label (default: "Confirm")
  confirm_button_style — optional, "danger" (default) or "primary"
{% endcomment %}
<div x-data="{ open: false }"
     x-show="open"
     x-transition:enter="modal-enter"
     x-transition:leave="modal-leave"
     @open-confirm.window="if ($event.detail === '{{ confirm_id }}') open = true"
     @keydown.escape.window="open = false"
     class="pl-modal-backdrop"
     style="display: none;"
     role="dialog"
     aria-modal="true">
    <div class="pl-modal pl-modal--sm" @click.outside="open = false">
        <div class="pl-modal__header">
            <h2 class="pl-modal__title">{{ confirm_title|default:"Are you sure?" }}</h2>
            <button type="button" @click="open = false" class="pl-modal__close" aria-label="Close">&times;</button>
        </div>
        <div class="pl-modal__body">
            <p style="margin:0 0 1.5rem;">{{ confirm_message }}</p>
            <div class="pl-modal__actions">
                <form method="post" action="{{ confirm_action_url }}" style="flex:1;">
                    {% csrf_token %}
                    <button type="submit" class="pl-btn pl-btn--{{ confirm_button_style|default:'danger' }}" style="width:100%;">
                        {{ confirm_button_text|default:"Confirm" }}
                    </button>
                </form>
                <button type="button" @click="open = false" class="pl-btn pl-btn--secondary" style="flex:1;">Cancel</button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 5: Create the toast component**

Create `templates/components/toast.html`:

```html
{% comment %}
Toast notification container. Include once in base templates.

Triggered by:
  1. Server-side: HX-Trigger header with showToast event (via hub.toast.trigger_toast)
  2. Client-side: $dispatch('show-toast', {message: '...', type: 'success'})
{% endcomment %}
<div x-data="plToastManager()" @show-toast.window="add($event.detail)" class="pl-toast-container" aria-live="polite">
    <template x-for="toast in toasts" :key="toast.id">
        <div class="pl-toast" :class="'pl-toast--' + toast.type"
             x-show="toast.visible"
             x-transition:enter="toast-enter"
             x-transition:leave="toast-leave">
            <span x-text="toast.message"></span>
            <button @click="dismiss(toast.id)" class="pl-toast__close" aria-label="Dismiss">&times;</button>
        </div>
    </template>
</div>

<script>
function plToastManager() {
    return {
        toasts: [],
        add(detail) {
            var id = Date.now();
            this.toasts.push({id: id, message: detail.message, type: detail.type || 'success', visible: true});
            var self = this;
            setTimeout(function() { self.dismiss(id); }, 4000);
        },
        dismiss(id) {
            var toast = this.toasts.find(function(t) { return t.id === id; });
            if (toast) toast.visible = false;
            var self = this;
            setTimeout(function() { self.toasts = self.toasts.filter(function(t) { return t.id !== id; }); }, 300);
        }
    };
}
</script>
```

- [ ] **Step 6: Commit**

```bash
git add templates/components/
git commit -m "feat: add reusable template components (modal, toast, toggle, form_field, confirm_modal)"
```

---

### Task 3: Create Toast Utility and Tests

**Files:**
- Create: `hub/toast.py`
- Create: `tests/hub/toast_spec.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/hub/toast_spec.py`:

```python
"""BDD specs for the toast notification utility."""

from __future__ import annotations

import json

from django.http import HttpResponse

from hub.toast import trigger_toast


def describe_trigger_toast():
    def it_sets_hx_trigger_header_with_success_type():
        response = HttpResponse(status=204)
        trigger_toast(response, "Item added!", "success")
        payload = json.loads(response["HX-Trigger"])
        assert payload == {"showToast": {"message": "Item added!", "type": "success"}}

    def it_defaults_to_success_type():
        response = HttpResponse(status=204)
        trigger_toast(response, "Done!")
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "success"

    def it_supports_error_type():
        response = HttpResponse(status=200)
        trigger_toast(response, "Something went wrong", "error")
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "error"

    def it_supports_info_type():
        response = HttpResponse(status=200)
        trigger_toast(response, "FYI", "info")
        payload = json.loads(response["HX-Trigger"])
        assert payload["showToast"]["type"] == "info"

    def it_preserves_existing_response_content():
        response = HttpResponse("OK", status=200)
        trigger_toast(response, "Added!")
        assert response.content == b"OK"
        assert response.status_code == 200
        assert "HX-Trigger" in response
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/hub/toast_spec.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.toast'`

- [ ] **Step 3: Write the implementation**

Create `hub/toast.py`:

```python
"""Toast notification utility for HTMX responses."""

from __future__ import annotations

import json

from django.http import HttpResponse


def trigger_toast(response: HttpResponse, message: str, toast_type: str = "success") -> None:
    """Set the HX-Trigger header to show a toast notification on the client.

    Args:
        response: The HttpResponse to add the header to.
        message: The toast message text.
        toast_type: One of "success", "error", "info".
    """
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": toast_type}})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/hub/toast_spec.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hub/toast.py tests/hub/toast_spec.py
git commit -m "feat: add trigger_toast utility for HTMX toast notifications"
```

---

### Task 4: Wire Toast + Components into Base Templates

**Files:**
- Modify: `templates/hub/base.html`
- Modify: `templates/admin/base.html`

- [ ] **Step 1: Add components.css and toast to hub/base.html**

In `templates/hub/base.html`, add the components.css link after the hub.css link (after line 11):

```html
    <link rel="stylesheet" href="{% static 'css/components.css' %}">
```

Add the toast component include and HTMX toast event listener. After line 163 (after `{% endblock %}` for content, before the changelog modal include), add:

```html
        {% include "components/toast.html" %}
```

After the existing `htmx:afterSettle` listener (after line 180), add the HTMX toast event bridge:

```html
    <script>
        document.body.addEventListener('htmx:afterRequest', function(event) {
            var trigger = event.detail.xhr && event.detail.xhr.getResponseHeader('HX-Trigger');
            if (trigger) {
                try {
                    var data = JSON.parse(trigger);
                    if (data.showToast) {
                        window.dispatchEvent(new CustomEvent('show-toast', {detail: data.showToast}));
                    }
                } catch(e) {}
            }
        });
    </script>
```

- [ ] **Step 2: Add components.css, Alpine.js, and toast to admin/base.html**

In `templates/admin/base.html`, the admin base extends unfold's skeleton. Add a stylesheet link for `components.css` in the `{% block extrahead %}` section. Also add Alpine.js (the admin doesn't currently load it) and the toast component.

Read the current file to find the exact insertion points, then:

1. In the `<head>` / `extrahead` block, add:
```html
<link rel="stylesheet" href="{% static 'css/components.css' %}">
```

2. Before `</body>` (at the end of the template), add:
```html
{% include "components/toast.html" %}
<script src="{% static 'js/alpine.min.js' %}" defer></script>
<script>
    document.body.addEventListener('htmx:afterRequest', function(event) {
        var trigger = event.detail.xhr && event.detail.xhr.getResponseHeader('HX-Trigger');
        if (trigger) {
            try {
                var data = JSON.parse(trigger);
                if (data.showToast) {
                    window.dispatchEvent(new CustomEvent('show-toast', {detail: data.showToast}));
                }
            } catch(e) {}
        }
    });
</script>
```

Note: Check if HTMX is already loaded in admin — if not, it may need to be added. If unfold provides its own HTMX, the listener will still work.

- [ ] **Step 3: Commit**

```bash
git add templates/hub/base.html templates/admin/base.html
git commit -m "feat: wire toast notifications and components.css into hub and admin base templates"
```

---

### Task 5: Fix Admin Toggle Bug + Horizontal Scroll + Add Product Visibility

**Files:**
- Modify: `static/css/unfold-custom.css` (lines 1145-1154 for toggle fix, product section for scroll/visibility)
- Modify: `templates/admin/membership/guild_product_inline.html` (lines 78-100 for Add Product toggle)

- [ ] **Step 1: Fix the toggle/checkbox bug in admin inlines**

The bug: `.pl-admin-fieldset input[type="checkbox"]` at `unfold-custom.css:1146` resets checkbox appearance, but the Add Product inline's fields live inside `.pl-add-product__field`, not `.pl-admin-fieldset`. So the `is_active` checkbox in the inline gets default browser styling mixed with partial unfold overrides.

Add this rule after the `.pl-add-product__field input:focus` block (after line 1849 in `unfold-custom.css`):

```css
/* Fix: checkbox in Add Product inline — match the admin fieldset toggle treatment */
.pl-add-product__field input[type="checkbox"] {
    width: auto !important;
    max-width: none !important;
    appearance: none !important;
    -webkit-appearance: none !important;
    padding: 0 !important;
    box-shadow: none !important;
    border: none !important;
}
```

- [ ] **Step 2: Fix horizontal scroll on the Edit Guild page**

The `.pl-add-product__fields` flex container can overflow. Add `overflow-x: hidden` to the products section and constrain the flex children. Find `.pl-products-section` (around line 1673) and add:

```css
.pl-products-section {
    margin-top: 2rem;
    overflow-x: hidden;
    max-width: 100%;
}
```

Also update `.pl-add-product__fields` (around line 1812) to add `max-width: 100%`:

```css
.pl-add-product__fields {
    display: flex;
    gap: 1rem;
    align-items: flex-end;
    flex-wrap: wrap;
    margin-bottom: 1rem;
    max-width: 100%;
}
```

And update `.pl-add-product__field` (around line 1820) to replace `min-width: 140px` with a safer value:

```css
.pl-add-product__field {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    flex: 1 1 140px;
    min-width: 0;
}
```

- [ ] **Step 3: Hide Add Product form behind a toggle button**

In `templates/admin/membership/guild_product_inline.html`, wrap the Add Product section (lines 78-99) in an Alpine.js toggle. Replace the existing block:

Find this section (lines 78-99):
```html
    {# Add product form — first non-original form; skip the last one (JS empty template) #}
    {% for inline_admin_form in inline_admin_formset %}
        {% if not inline_admin_form.original and not forloop.last %}
        <div class="pl-add-product">
            <h4 class="pl-add-product__title">Add Product</h4>
```

Replace with an Alpine-wrapped version:

```html
    {# Add product form — hidden by default, revealed on button click #}
    <div x-data="{ showForm: false }">
        <button type="button" @click="showForm = !showForm" class="pl-product-btn pl-product-btn--add" style="margin-top:1rem;">
            <span x-text="showForm ? '− Cancel' : '+ Add Product'"></span>
        </button>
        {% for inline_admin_form in inline_admin_formset %}
            {% if not inline_admin_form.original and not forloop.last %}
            <div x-show="showForm" x-transition class="pl-add-product" style="margin-top:0.75rem;">
                <div class="pl-add-product__fields">
                    {% for fieldset in inline_admin_form %}
                        {% for line in fieldset %}
                            {% for field in line %}
                                {% if not field.field.is_hidden %}
                                <div class="pl-add-product__field">
                                    <label for="{{ field.field.auto_id }}">{{ field.field.label }}</label>
                                    {{ field.field }}
                                </div>
                                {% endif %}
                            {% endfor %}
                        {% endfor %}
                    {% endfor %}
                </div>
                <button type="submit" name="_save" class="pl-add-product__btn">Add Product</button>
            </div>
            {% endif %}
        {% endfor %}
    </div>
```

Note: The admin base template needs Alpine.js loaded (handled in Task 4). Verify Alpine is available on admin pages before this works.

- [ ] **Step 4: Add CSS for the new "Add Product" toggle button**

Add to `unfold-custom.css` after the existing `.pl-product-btn--delete:hover` rule (around line 1787):

```css
.pl-product-btn--add {
    background: rgba(238, 180, 75, 0.1);
    color: #EEB44B;
    border: 1px dashed rgba(238, 180, 75, 0.3);
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 600;
    transition: all 0.15s ease;
}

.pl-product-btn--add:hover {
    background: rgba(238, 180, 75, 0.15);
    border-color: rgba(238, 180, 75, 0.5);
}

[data-theme="light"] .pl-product-btn--add {
    background: rgba(238, 180, 75, 0.08);
    border-color: rgba(238, 180, 75, 0.4);
}

[data-theme="light"] .pl-product-btn--add:hover {
    background: rgba(238, 180, 75, 0.15);
}
```

- [ ] **Step 5: Commit**

```bash
git add static/css/unfold-custom.css templates/admin/membership/guild_product_inline.html
git commit -m "fix: admin toggle bug, horizontal scroll, and hide Add Product form behind toggle"
```

---

### Task 6: Migrate Email Preferences to Toggle Component

**Files:**
- Modify: `templates/hub/email_preferences.html`
- Modify: `static/css/hub.css` (add `.hub-toggle` → `.pl-toggle` aliases)

- [ ] **Step 1: Add CSS alias mappings in hub.css**

At the end of `static/css/hub.css`, add backward-compat aliases so existing code doesn't break during transition:

```css
/* Backward-compat aliases — maps old .hub-toggle to new .pl-toggle from components.css.
   Remove these once all templates are migrated. */
.hub-toggle-row { composes: pl-toggle-row; }
```

Actually, CSS `composes` is CSS Modules only. Instead, just keep the old classes in hub.css for now — they'll be removed in Phase 3 when all templates are migrated. The migration here is to update `email_preferences.html` to use the new component.

- [ ] **Step 2: Update email_preferences.html to use the toggle component**

Replace the manual toggle HTML in `templates/hub/email_preferences.html`. The current content (lines 11-19) is:

```html
    <div class="hub-toggle-row">
        <div>
            <div class="hub-toggle-label">Voting Result Emails</div>
            <div class="hub-toggle-desc">Get notified when guild voting results are published</div>
        </div>
        <label class="hub-toggle">
            {{ form.voting_results }}
            <span class="hub-toggle__slider"></span>
        </label>
    </div>
```

Replace with:

```html
    {% include "components/toggle.html" with field=form.voting_results toggle_label="Voting Result Emails" toggle_description="Get notified when guild voting results are published" %}
```

- [ ] **Step 3: Verify the page renders correctly**

Run: `python manage.py runserver`
Navigate to `/settings/emails/` and verify:
- The toggle renders correctly in both dark and light themes
- The toggle still submits the form correctly
- The visual appearance matches the previous design

- [ ] **Step 4: Commit**

```bash
git add templates/hub/email_preferences.html
git commit -m "refactor: migrate email preferences toggle to reusable component"
```

---

### Task 7: Migrate Admin Delete Modal to Confirm Modal Component

**Files:**
- Modify: `templates/admin/membership/guild_product_inline.html`

- [ ] **Step 1: Replace the hand-built delete modal with the confirm_modal component**

The current delete modal (lines 103-118 of `guild_product_inline.html`) uses `.changelog-overlay` and `.changelog-modal` classes that aren't designed for this purpose, and has inline JavaScript for state management.

This is more complex than a simple `confirm_modal.html` swap because the product name is dynamic (set via JS when clicking a specific product's delete button). We need to keep the Alpine.js approach but use the new modal styles.

Replace the delete modal section (lines 103-118) with:

```html
{# Delete confirmation modal — uses pl-modal component styles #}
<div x-data="{ open: false, productName: '', deletePrefix: '' }"
     x-show="open"
     x-transition:enter="modal-enter"
     x-transition:leave="modal-leave"
     @open-product-delete.window="open = true; productName = $event.detail.name; deletePrefix = $event.detail.prefix"
     @keydown.escape.window="open = false"
     class="pl-modal-backdrop"
     style="display: none;"
     role="dialog"
     aria-modal="true">
    <div class="pl-modal pl-modal--sm" @click.outside="open = false">
        <div class="pl-modal__header">
            <h2 class="pl-modal__title">Delete product?</h2>
            <button type="button" @click="open = false" class="pl-modal__close" aria-label="Close">&times;</button>
        </div>
        <div class="pl-modal__body">
            <p style="margin:0 0 1.5rem;">Are you sure you want to delete <strong x-text="productName"></strong>? This cannot be undone.</p>
            <div class="pl-modal__actions">
                <button type="submit" name="_save" class="pl-btn pl-btn--danger" style="flex:1;"
                    @click="var input = document.querySelector('[name=\'' + deletePrefix + '-DELETE\']'); if (input) input.checked = true; open = false;">
                    Yes, delete
                </button>
                <button type="button" @click="open = false" class="pl-btn pl-btn--secondary" style="flex:1;">Cancel</button>
            </div>
        </div>
    </div>
</div>
```

Also update the delete button onclick in the product rows (line 52) from:

```html
onclick="plOpenDeleteModal('{{ inline_admin_form.original.name|escapejs }}', '{{ inline_admin_formset.formset.prefix }}-{{ forloop.counter0 }}')"
```

To use Alpine dispatch:

```html
@click="$dispatch('open-product-delete', {name: '{{ inline_admin_form.original.name|escapejs }}', prefix: '{{ inline_admin_formset.formset.prefix }}-{{ forloop.counter0 }}'})"
```

Remove the old `<script>` block at the bottom of the file (lines 120-137) since Alpine handles everything now.

- [ ] **Step 2: Commit**

```bash
git add templates/admin/membership/guild_product_inline.html
git commit -m "refactor: migrate product delete modal to pl-modal component styles with Alpine.js"
```

---

### Task 8: Write FRONTEND.md

**Files:**
- Create: `FRONTEND.md`
- Modify: `CLAUDE.md` (add reference)

- [ ] **Step 1: Create FRONTEND.md**

Create `FRONTEND.md` at the project root:

```markdown
# plfog Frontend Guide

Reference for building pages, forms, and components in plfog. Read this before creating any template.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Templates | Django templates with `{% include %}` components |
| Interactivity | Alpine.js 3.x (`x-data`, `x-show`, `@click`, `$dispatch`) |
| Server communication | HTMX (`hx-get`, `hx-post`, `hx-target`, `hx-swap`) |
| Styling | Custom CSS with `pl-` prefix, CSS variables, dark/light themes |
| Admin | django-unfold + custom overrides in `unfold-custom.css` |

No build step. No npm. No bundler. All JS is loaded via `<script>` tags.

## Design System

### Colors (CSS Variables)

| Token | Dark | Light | Usage |
|-------|------|-------|-------|
| `--hub-bg` | `#12121f` | `#f5f5f5` | Page background |
| `--hub-card-bg` | `#0f2d44` | `#fff` | Card/modal background |
| `--hub-text` | `#F4EFDD` | `#1f2937` | Primary text |
| `--hub-text-muted` | `#96ACBB` | `#6b7280` | Secondary text, labels, hints |
| `--color-tuscan-yellow` | `#EEB44B` | `#EEB44B` | Primary accent, buttons, active toggles |
| `--color-matte-navy` | `#092E4C` | `#092E4C` | Sidebar, brand areas |

### Typography

- **Headings:** Lato (400, 700, 900)
- **Body:** Inter (300, 400, 500, 700)
- Loaded via Google Fonts CDN in base templates.

### Spacing

8px grid: `0.25rem`, `0.5rem`, `0.75rem`, `1rem`, `1.25rem`, `1.5rem`, `2rem`

## Component Library

All components live in `templates/components/`. Include via `{% include "components/<name>.html" with param=value %}`.

### Modal (`components/modal.html`)

Reusable modal container. Content loaded via HTMX or passed as context.

**Parameters:**
- `modal_id` (required) — unique DOM id
- `modal_title` (required) — heading text
- `modal_size` — `sm` (400px), `md` (560px), `lg` (720px)

**Open a modal:**
```html
<button @click="$dispatch('open-modal', 'my-modal')">Open</button>
```

**Close a modal (from inside):**
```html
<button @click="$dispatch('close-modal', 'my-modal')">Done</button>
```

**Load content via HTMX:**
```html
<button
    @click="$dispatch('open-modal', 'edit-item')"
    hx-get="/items/42/edit-form/"
    hx-target="#edit-item-body"
    hx-swap="innerHTML">
    Edit
</button>
{% include "components/modal.html" with modal_id="edit-item" modal_title="Edit Item" %}
```

### Toast (`components/toast.html`)

Toast notifications. Already included in `hub/base.html` and `admin/base.html` — do not include again.

**Server-side (from views):**
```python
from hub.toast import trigger_toast

def my_view(request):
    # ... do work ...
    response = HttpResponse(status=204)
    trigger_toast(response, "Item saved!", "success")
    return response
```

**Client-side (from Alpine.js):**
```html
<button @click="$dispatch('show-toast', {message: 'Copied!', type: 'info'})">Copy</button>
```

**Types:** `success` (green), `error` (red), `info` (blue)

### Toggle (`components/toggle.html`)

Toggle switch for boolean fields. Automatically used by `form_field.html` for checkbox inputs.

**Parameters:**
- `field` (required) — Django BooleanField
- `toggle_label` — display label
- `toggle_description` — description text

```html
{% include "components/toggle.html" with field=form.is_active toggle_label="Active" toggle_description="Show this product to members" %}
```

### Form Field (`components/form_field.html`)

Standard field wrapper. Auto-detects checkboxes and renders as toggle.

**Parameters:**
- `field` (required) — Django form field
- `field_label` — label override
- `field_hint` — hint text override

```html
{% include "components/form_field.html" with field=form.name %}
{% include "components/form_field.html" with field=form.email field_hint="We'll never share this" %}
{% include "components/form_field.html" with field=form.is_active %}  {# auto-renders as toggle #}
```

### Confirm Modal (`components/confirm_modal.html`)

For destructive actions (delete, void, deactivate).

**Parameters:**
- `confirm_id` (required) — unique DOM id
- `confirm_title` — heading (default: "Are you sure?")
- `confirm_message` — body text
- `confirm_action_url` — form POST target
- `confirm_button_text` — button label (default: "Confirm")
- `confirm_button_style` — `danger` (default) or `primary`

```html
<button @click="$dispatch('open-confirm', 'void-charge')">Void</button>
{% include "components/confirm_modal.html" with confirm_id="void-charge" confirm_title="Void this charge?" confirm_message="This will remove the charge from the member's tab." confirm_action_url="/billing/void/42/" confirm_button_text="Void Charge" %}
```

## Interaction Patterns

| Scenario | Pattern | Example |
|----------|---------|---------|
| Quick action (1-3 fields) | Modal + Toast | "Add to Tab", "Enter Your Own Price" |
| Data entry (4+ fields) | Inline form on page | Profile settings, billing settings |
| Destructive action | Confirm modal | Delete product, void charge |
| Success feedback (HTMX) | Toast notification | "Added to your tab!" |
| Success feedback (full page) | Django messages | Login, signup |

**Rule of thumb:** If the action doesn't need the user to leave the page, use a modal + toast. If it's a full form with many fields, use an inline form or dedicated page.

## HTMX Patterns

### Form submission returning a toast

```python
# views.py
from hub.toast import trigger_toast

def add_to_cart(request, pk):
    # ... validate and process ...
    response = HttpResponse(status=204)
    trigger_toast(response, "Added to cart!", "success")
    return response
```

```html
<!-- template -->
<form hx-post="{% url 'hub_cart_add' guild.pk %}" hx-swap="none">
    {% csrf_token %}
    <input type="hidden" name="product_pk" value="{{ product.pk }}">
    <button type="submit">Add to Tab</button>
</form>
```

### Loading a partial into a modal

```html
<button
    @click="$dispatch('open-modal', 'my-modal')"
    hx-get="{% url 'my_partial' %}"
    hx-target="#my-modal-body"
    hx-swap="innerHTML">
    Open Form
</button>
```

### Updating another element after a form submit (OOB swap)

```python
# Return the updated element in the response body
response = render(request, "hub/partials/tab_pill.html", {"tab_balance": new_balance})
trigger_toast(response, "Items added to your tab!")
return response
```

```html
<!-- In the partial, use hx-swap-oob to update the tab pill -->
<a id="tab-balance-pill" hx-swap-oob="true" ...>${{ tab_balance }}</a>
```

## Rules for Claude / AI Agents

1. **Always use `components/form_field.html`** for form fields — never render raw `{{ field }}` with manual label/error HTML.
2. **Always use `components/modal.html`** for modals — never build one-off modal HTML with custom overlay/backdrop.
3. **Always use `components/toggle.html`** for boolean fields — never render checkboxes directly or build custom toggle HTML.
4. **Use the `pl-` CSS prefix** for all new component classes. Never add classes with other prefixes.
5. **Quick forms (1-3 fields) → modal.** Longer forms → inline or dedicated page.
6. **After mutating actions, return a toast** via `trigger_toast()`. Don't redirect with Django messages for HTMX requests.
7. **Test both dark and light themes** when adding new CSS.
8. **Card layout:** Wrap content sections in `<div class="hub-card">` for hub pages.
9. **No inline styles** except for truly one-off layout adjustments. Add a CSS class instead.
10. **Image placeholders:** When designing product cards or profile sections, leave space for future image support but don't build upload infrastructure.

## CSS Files

| File | Scope | What goes here |
|------|-------|---------------|
| `static/css/style.css` | Public pages (login, signup, landing) | Auth forms, hero, navigation |
| `static/css/hub.css` | Member hub | Hub layout, sidebar, topbar, page-specific styles |
| `static/css/components.css` | Shared (hub + admin) | All reusable component styles (modal, toast, toggle, etc.) |
| `static/css/unfold-custom.css` | Admin only | Unfold overrides, admin-specific layouts |
```

- [ ] **Step 2: Add FRONTEND.md reference to CLAUDE.md**

In `CLAUDE.md`, after the line `> **Quick orientation:** See [CODEBASE_INDEX.md](CODEBASE_INDEX.md)...`, add:

```markdown
> **Frontend:** See [FRONTEND.md](FRONTEND.md) for the component library, design system, and rules for building pages.
```

- [ ] **Step 3: Commit**

```bash
git add FRONTEND.md CLAUDE.md
git commit -m "docs: add FRONTEND.md component catalog and design system reference"
```

---

## Phase 2: Guild Page UX

### Task 9: Add Cart and EYOP View Endpoints

**Files:**
- Modify: `hub/views.py` (add 3 new view functions)
- Modify: `hub/urls.py` (add 3 new URL patterns)

- [ ] **Step 1: Write the failing tests for the new endpoints**

Create `tests/hub/cart_views_spec.py`:

```python
"""BDD specs for guild cart endpoints."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.models import Product, TabEntry
from tests.billing.factories import BillingSettingsFactory, ProductFactory, TabFactory
from tests.membership.factories import GuildFactory, MembershipPlanFactory


def _linked_user(client: Client, *, username: str = "cartu") -> tuple:
    """Create a user + linked Member + Tab (with a saved card) + login."""
    MembershipPlanFactory()
    user = User.objects.create_user(username=username, password="pass")
    member = user.member
    tab = TabFactory(member=member, stripe_payment_method_id="pm_test", stripe_customer_id="cus_test")
    client.login(username=username, password="pass")
    return user, tab


@pytest.mark.django_db
def describe_guild_cart_confirm():
    def it_creates_tab_entries_for_each_cart_item(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        p1 = ProductFactory(guild=guild, name="Laser Time", price=Decimal("10.00"))
        p2 = ProductFactory(guild=guild, name="3D Print", price=Decimal("5.00"))
        _user, tab = _linked_user(client)

        response = client.post(
            f"/guilds/{guild.pk}/cart/confirm/",
            data=json.dumps({"items": [
                {"product_pk": p1.pk, "quantity": 2},
                {"product_pk": p2.pk, "quantity": 1},
            ]}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        entries = TabEntry.objects.filter(tab=tab).order_by("description")
        assert entries.count() == 3
        assert entries.filter(description="Laser Time").count() == 2
        assert entries.filter(description="3D Print").count() == 1

    def it_returns_toast_on_success(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        product = ProductFactory(guild=guild, price=Decimal("10.00"))
        _user, _tab = _linked_user(client)

        response = client.post(
            f"/guilds/{guild.pk}/cart/confirm/",
            data=json.dumps({"items": [{"product_pk": product.pk, "quantity": 1}]}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        trigger = json.loads(response["HX-Trigger"])
        assert "showToast" in trigger
        assert trigger["showToast"]["type"] == "success"

    def it_rejects_empty_cart(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        _user, _tab = _linked_user(client)

        response = client.post(
            f"/guilds/{guild.pk}/cart/confirm/",
            data=json.dumps({"items": []}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400

    def it_rejects_invalid_product(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        _user, _tab = _linked_user(client)

        response = client.post(
            f"/guilds/{guild.pk}/cart/confirm/",
            data=json.dumps({"items": [{"product_pk": 99999, "quantity": 1}]}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 400

    def it_requires_login(client: Client):
        guild = GuildFactory()
        response = client.post(f"/guilds/{guild.pk}/cart/confirm/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def it_rejects_get_method(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        _user, _tab = _linked_user(client)

        response = client.get(f"/guilds/{guild.pk}/cart/confirm/")
        assert response.status_code == 405


@pytest.mark.django_db
def describe_guild_eyop_form():
    def it_returns_form_partial_for_htmx(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        _user, _tab = _linked_user(client, username="eyopu")

        response = client.get(
            f"/guilds/{guild.pk}/eyop-form/",
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert b"description" in response.content.lower() or b"Description" in response.content

    def it_creates_entry_on_post(client: Client):
        BillingSettingsFactory()
        guild = GuildFactory()
        _user, tab = _linked_user(client, username="eyopp")

        response = client.post(
            f"/guilds/{guild.pk}/eyop-form/",
            {"description": "Custom item", "amount": "7.50"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        entry = TabEntry.objects.get(tab=tab)
        assert entry.description == "Custom item"
        assert entry.amount == Decimal("7.50")

    def it_requires_login(client: Client):
        guild = GuildFactory()
        response = client.get(f"/guilds/{guild.pk}/eyop-form/")
        assert response.status_code == 302
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/hub/cart_views_spec.py -v`
Expected: FAIL — URL patterns don't exist yet

- [ ] **Step 3: Add URL patterns**

In `hub/urls.py`, add the new patterns after the existing `guilds/<int:pk>/` pattern:

```python
    path("guilds/<int:pk>/cart/confirm/", views.guild_cart_confirm, name="hub_guild_cart_confirm"),
    path("guilds/<int:pk>/eyop-form/", views.guild_eyop_form, name="hub_guild_eyop_form"),
```

- [ ] **Step 4: Implement the cart confirm view**

In `hub/views.py`, add the new view function. Add these imports at the top (some may already exist):

```python
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
```

Add the view function:

```python
@login_required
@require_POST
def guild_cart_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    """Batch-add cart items to the member's tab. Expects JSON body with items array."""
    from hub.toast import trigger_toast

    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)
    if member is None:
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

    response = HttpResponse(status=204)
    item_word = "item" if entries_created == 1 else "items"
    trigger_toast(response, f"{entries_created} {item_word} added to your tab!", "success")
    return response
```

- [ ] **Step 5: Implement the EYOP form view**

In `hub/views.py`, add:

```python
@login_required
@require_http_methods(["GET", "POST"])
def guild_eyop_form(request: HttpRequest, pk: int) -> HttpResponse:
    """Return the EYOP form partial (GET) or process submission (POST)."""
    from billing.forms import CONTEXT_MEMBER_GUILD_PAGE, TabItemForm
    from hub.toast import trigger_toast

    guild = get_object_or_404(Guild, pk=pk)
    member = _get_member(request)
    if member is None:
        return HttpResponse("No linked membership.", status=400)

    tab, _created = Tab.objects.get_or_create(member=member)

    if request.method == "POST":
        form = TabItemForm(request.POST, context=CONTEXT_MEMBER_GUILD_PAGE, user=request.user, guild=guild)
        if form.is_valid():
            try:
                if not tab.can_add_entry:
                    raise NoPaymentMethodError("Payment method required.")
                form.apply_to_tab(tab, added_by=request.user, is_self_service=True)
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
```

- [ ] **Step 6: Create the EYOP form partial template**

Create `templates/hub/partials/eyop_form.html`:

```html
<form hx-post="{% url 'hub_guild_eyop_form' guild.pk %}"
      hx-target="#eyop-modal-body"
      hx-swap="innerHTML">
    {% csrf_token %}
    {% include "components/form_field.html" with field=eyop_form.description %}
    {% include "components/form_field.html" with field=eyop_form.amount %}
    {% if eyop_form.non_field_errors %}
    <div class="pl-field-error" style="margin-bottom:1rem;">{{ eyop_form.non_field_errors.0 }}</div>
    {% endif %}
    <button type="submit" class="pl-btn pl-btn--primary" style="width:100%;margin-top:0.5rem;">Add to Cart</button>
</form>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/hub/cart_views_spec.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add hub/views.py hub/urls.py templates/hub/partials/eyop_form.html tests/hub/cart_views_spec.py
git commit -m "feat: add cart confirm and EYOP form endpoints for guild page"
```

---

### Task 10: Rewrite Guild Detail Template with Modals and Cart

**Files:**
- Modify: `templates/hub/guild_detail.html`

- [ ] **Step 1: Rewrite the guild detail template**

Replace the entire content of `templates/hub/guild_detail.html` with the new version that includes:
- Product cards with "Add to Cart" buttons (Alpine.js modal trigger)
- "Add to Cart" modal with quantity picker
- "+" icon button for EYOP that opens a modal loaded via HTMX
- Client-side cart managed by Alpine.js
- "Confirm & Add to Tab" button that POSTs to the cart confirm endpoint

```html
{% extends "hub/base.html" %}
{% load static %}
{% block title %}{{ guild.name }}{% endblock %}

{% block content %}
<div x-data="guildCart({{ guild.pk }})">

{# Guild info card #}
<div class="hub-card">
    <h1 class="hub-page-title">{{ guild.name }}</h1>
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

{# Products card #}
<div class="hub-card" style="margin-top:1.5rem;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
        <h3 class="hub-detail-label" style="margin:0;">Products</h3>
        {% if tab and tab.can_add_entry %}
        <button
            class="pl-btn pl-btn--icon pl-btn--secondary"
            @click="$dispatch('open-modal', 'eyop-modal')"
            hx-get="{% url 'hub_guild_eyop_form' guild.pk %}"
            hx-target="#eyop-modal-body"
            hx-swap="innerHTML"
            title="Enter Your Own Price">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 5v14"/><path d="M5 12h14"/>
            </svg>
        </button>
        {% endif %}
    </div>
    {% if products %}
    <div class="guild-product-grid">
        {% for product in products %}
        <div class="guild-product-card">
            <div class="guild-product-card__name">{{ product.name }}</div>
            <div class="guild-product-card__price">${{ product.price }}</div>
            {% if tab and tab.can_add_entry %}
            <button type="button"
                    class="guild-product-card__add-btn"
                    @click="openAddModal({{ product.pk }}, '{{ product.name|escapejs }}', '{{ product.price }}')">
                Add to Cart
            </button>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% else %}
    <p class="hub-text-muted">No products listed yet.</p>
    {% endif %}
</div>

{% if tab and not tab.can_add_entry %}
<div class="hub-card" style="margin-top:1.5rem;">
    {% if tab.is_locked %}
    <p class="hub-text-muted">Your tab is locked. Contact an admin.</p>
    {% else %}
    <p class="hub-text-muted">
        You need a saved payment method before you can add items.
        <a href="{% url 'billing_setup_payment_method' %}">Add a card &rarr;</a>
    </p>
    {% endif %}
</div>
{% endif %}

{# Cart section — only visible when items are in the cart #}
{% if tab and tab.can_add_entry %}
<div class="hub-card pl-cart" style="margin-top:1.5rem;" x-show="items.length > 0" x-transition x-cloak>
    <h3 class="pl-cart__title">Your Cart</h3>
    <div class="pl-cart__items">
        <template x-for="(item, index) in items" :key="index">
            <div class="pl-cart__item">
                <span class="pl-cart__item-name" x-text="item.name"></span>
                <span class="pl-cart__item-qty" x-text="'x' + item.quantity"></span>
                <span class="pl-cart__item-price" x-text="'$' + (item.price * item.quantity).toFixed(2)"></span>
                <button class="pl-cart__item-remove" @click="removeItem(index)" title="Remove">&times;</button>
            </div>
        </template>
    </div>
    <div class="pl-cart__footer">
        <span class="pl-cart__total" x-text="'Total: $' + cartTotal()"></span>
        <button class="pl-btn pl-btn--primary" @click="confirmCart()" :disabled="submitting">
            <span x-text="submitting ? 'Adding...' : 'Confirm & Add to Tab'"></span>
        </button>
    </div>
</div>
{% endif %}

{# Add to Cart modal — quantity picker #}
<div x-show="addModalOpen"
     x-transition:enter="modal-enter"
     x-transition:leave="modal-leave"
     @keydown.escape.window="addModalOpen = false"
     class="pl-modal-backdrop"
     style="display: none;"
     role="dialog"
     aria-modal="true">
    <div class="pl-modal pl-modal--sm" @click.outside="addModalOpen = false">
        <div class="pl-modal__header">
            <h2 class="pl-modal__title">Add to Cart</h2>
            <button type="button" @click="addModalOpen = false" class="pl-modal__close" aria-label="Close">&times;</button>
        </div>
        <div class="pl-modal__body">
            <div style="margin-bottom:1.25rem;">
                <div style="font-size:1rem;font-weight:600;color:var(--hub-text, #F4EFDD);" x-text="addModalProduct.name"></div>
                <div style="font-size:0.875rem;color:var(--hub-text-muted, #96ACBB);margin-top:0.25rem;" x-text="'$' + addModalProduct.price + ' each'"></div>
            </div>
            <div style="margin-bottom:1.25rem;">
                <label class="pl-form-label" style="margin-bottom:0.5rem;display:block;">Quantity</label>
                <div class="pl-qty">
                    <button type="button" class="pl-qty__btn" @click="if (addModalQty > 1) addModalQty--">&minus;</button>
                    <span class="pl-qty__value" x-text="addModalQty"></span>
                    <button type="button" class="pl-qty__btn" @click="addModalQty++">+</button>
                </div>
            </div>
            <div style="font-size:0.9375rem;font-weight:600;color:var(--hub-text, #F4EFDD);margin-bottom:1.25rem;"
                 x-text="'Total: $' + (addModalProduct.price * addModalQty).toFixed(2)"></div>
            <button class="pl-btn pl-btn--primary" style="width:100%;" @click="addToCart()">Add to Cart</button>
        </div>
    </div>
</div>

{# EYOP modal — content loaded via HTMX #}
{% include "components/modal.html" with modal_id="eyop-modal" modal_title="Enter Your Own Price" modal_size="sm" %}

</div>{# /x-data guildCart #}
{% endblock %}

{% block extra_js %}
<script>
function guildCart(guildPk) {
    return {
        items: [],
        addModalOpen: false,
        addModalProduct: {pk: 0, name: '', price: 0},
        addModalQty: 1,
        submitting: false,

        openAddModal(pk, name, price) {
            this.addModalProduct = {pk: pk, name: name, price: parseFloat(price)};
            this.addModalQty = 1;
            this.addModalOpen = true;
        },

        addToCart() {
            var existing = this.items.find(function(i) { return i.pk === this.addModalProduct.pk; }.bind(this));
            if (existing) {
                existing.quantity += this.addModalQty;
            } else {
                this.items.push({
                    pk: this.addModalProduct.pk,
                    name: this.addModalProduct.name,
                    price: this.addModalProduct.price,
                    quantity: this.addModalQty
                });
            }
            this.addModalOpen = false;
            window.dispatchEvent(new CustomEvent('show-toast', {
                detail: {message: this.addModalProduct.name + ' x' + this.addModalQty + ' added to cart', type: 'success'}
            }));
        },

        removeItem(index) {
            this.items.splice(index, 1);
        },

        cartTotal() {
            return this.items.reduce(function(sum, item) {
                return sum + (item.price * item.quantity);
            }, 0).toFixed(2);
        },

        confirmCart() {
            if (this.items.length === 0 || this.submitting) return;
            this.submitting = true;
            var self = this;
            var payload = {
                items: this.items.map(function(item) {
                    return {product_pk: item.pk, quantity: item.quantity};
                })
            };
            fetch('/guilds/' + guildPk + '/cart/confirm/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')
                        ? document.querySelector('[name=csrfmiddlewaretoken]').value
                        : '{{ csrf_token }}'
                },
                body: JSON.stringify(payload)
            }).then(function(resp) {
                self.submitting = false;
                if (resp.ok) {
                    self.items = [];
                    var trigger = resp.headers.get('HX-Trigger');
                    if (trigger) {
                        try {
                            var data = JSON.parse(trigger);
                            if (data.showToast) {
                                window.dispatchEvent(new CustomEvent('show-toast', {detail: data.showToast}));
                            }
                        } catch(e) {}
                    }
                } else {
                    resp.json().then(function(data) {
                        window.dispatchEvent(new CustomEvent('show-toast', {
                            detail: {message: data.error || 'Something went wrong', type: 'error'}
                        }));
                    }).catch(function() {
                        window.dispatchEvent(new CustomEvent('show-toast', {
                            detail: {message: 'Something went wrong', type: 'error'}
                        }));
                    });
                }
            }).catch(function() {
                self.submitting = false;
                window.dispatchEvent(new CustomEvent('show-toast', {
                    detail: {message: 'Network error. Try again.', type: 'error'}
                }));
            });
        }
    };
}
</script>
{% endblock %}
```

- [ ] **Step 2: Add `x-cloak` style to hub.css**

Add to `static/css/hub.css` (near the top, with the base styles):

```css
[x-cloak] { display: none !important; }
```

This ensures Alpine.js-controlled elements don't flash before Alpine initializes.

- [ ] **Step 3: Update the existing guild_detail view to still serve the page correctly**

The existing `guild_detail` view in `hub/views.py` still needs to serve the guild page with products, tab, and EYOP form context. However, the EYOP form is now loaded via HTMX into a modal, so the view no longer needs to handle EYOP POST submissions inline. The `product_pk` POST handling also changes — products are now added via the cart confirm endpoint instead.

Update the `guild_detail` view to remove the POST handling (it becomes GET-only for the page render):

Replace `hub/views.py` `guild_detail` function (lines 222-282) with:

```python
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

    return render(
        request,
        "hub/guild_detail.html",
        {
            **ctx,
            "guild": guild,
            "products": products,
            "tab": tab,
        },
    )
```

Also remove the `_handle_guild_product_add` function (lines 197-219) since product adds now go through the cart confirm endpoint.

- [ ] **Step 4: Update existing guild page tests**

In `tests/hub/guild_pages_spec.py`, the existing tests for `describe_product_quick_add` and `describe_eyop_form` test the old POST-to-guild-detail pattern. These need to be updated:

- Tests that POST `product_pk` to `/guilds/<pk>/` should be moved to test the cart confirm endpoint (already covered in `cart_views_spec.py`)
- Tests that POST EYOP data to `/guilds/<pk>/` should be moved to test the EYOP form endpoint (already covered in `cart_views_spec.py`)
- The existing tests can be marked to verify the page renders correctly (GET-only behavior)

Update `tests/hub/guild_pages_spec.py`:

Remove the `describe_product_quick_add` block (lines 75-138) and the `describe_eyop_form` block (lines 140-end). Replace with simpler GET-only tests:

```python
    def describe_product_cards():
        def it_shows_add_to_cart_button_when_member_can_add(client: Client):
            BillingSettingsFactory()
            guild = GuildFactory()
            ProductFactory(guild=guild, name="Laser Time", is_active=True)
            _linked_user(client)
            response = client.get(f"/guilds/{guild.pk}/")
            assert b"Add to Cart" in response.content

        def it_hides_add_button_when_no_payment_method(client: Client):
            MembershipPlanFactory()
            guild = GuildFactory()
            ProductFactory(guild=guild, is_active=True)
            user = User.objects.create_user(username="nocard_grid", password="pass")
            TabFactory(member=user.member, stripe_payment_method_id="")
            client.login(username="nocard_grid", password="pass")
            response = client.get(f"/guilds/{guild.pk}/")
            assert b"Add to Cart" not in response.content
            assert b"saved payment method" in response.content
```

- [ ] **Step 5: Run all guild page tests**

Run: `pytest tests/hub/guild_pages_spec.py tests/hub/cart_views_spec.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add templates/hub/guild_detail.html hub/views.py hub/urls.py static/css/hub.css tests/hub/guild_pages_spec.py tests/hub/cart_views_spec.py
git commit -m "feat: guild page cart UX with modals, quantity picker, and batch confirm"
```

---

### Task 11: Add Void Charge Confirm Modal to Tab Detail

**Files:**
- Modify: `templates/hub/tab_detail.html`
- Modify: `hub/views.py` (add void endpoint)
- Modify: `hub/urls.py` (add void URL)
- Create: `tests/hub/void_entry_spec.py`

- [ ] **Step 1: Write failing tests for the void endpoint**

Create `tests/hub/void_entry_spec.py`:

```python
"""BDD specs for voiding tab entries."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from billing.models import TabEntry
from tests.billing.factories import BillingSettingsFactory, TabEntryFactory, TabFactory
from tests.membership.factories import MembershipPlanFactory


def _linked_user(client: Client) -> tuple:
    MembershipPlanFactory()
    user = User.objects.create_user(username="voider", password="pass")
    tab = TabFactory(member=user.member, stripe_payment_method_id="pm_test", stripe_customer_id="cus_test")
    client.login(username="voider", password="pass")
    return user, tab


@pytest.mark.django_db
def describe_void_tab_entry():
    def it_voids_a_pending_entry(client: Client):
        BillingSettingsFactory()
        _user, tab = _linked_user(client)
        entry = TabEntryFactory(tab=tab, amount=Decimal("10.00"))

        response = client.post(
            f"/tab/void/{entry.pk}/",
            {"reason": "Changed my mind"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        entry.refresh_from_db()
        assert entry.is_voided

    def it_returns_toast_on_success(client: Client):
        BillingSettingsFactory()
        _user, tab = _linked_user(client)
        entry = TabEntryFactory(tab=tab, amount=Decimal("5.00"))

        response = client.post(
            f"/tab/void/{entry.pk}/",
            {"reason": "Mistake"},
            HTTP_HX_REQUEST="true",
        )

        trigger = json.loads(response["HX-Trigger"])
        assert trigger["showToast"]["type"] == "success"

    def it_rejects_void_of_another_users_entry(client: Client):
        BillingSettingsFactory()
        MembershipPlanFactory()  # second plan not needed — just need another user
        _user, _tab = _linked_user(client)

        other_user = User.objects.create_user(username="other", password="pass")
        other_tab = TabFactory(member=other_user.member)
        entry = TabEntryFactory(tab=other_tab, amount=Decimal("10.00"))

        response = client.post(
            f"/tab/void/{entry.pk}/",
            {"reason": "Trying to void someone else's"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 404

    def it_requires_login(client: Client):
        response = client.post("/tab/void/1/")
        assert response.status_code == 302
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/hub/void_entry_spec.py -v`
Expected: FAIL — URL pattern doesn't exist

- [ ] **Step 3: Add the void URL pattern**

In `hub/urls.py`, add:

```python
    path("tab/void/<int:entry_pk>/", views.void_tab_entry, name="hub_void_tab_entry"),
```

- [ ] **Step 4: Implement the void view**

In `hub/views.py`, add:

```python
@login_required
@require_POST
def void_tab_entry(request: HttpRequest, entry_pk: int) -> HttpResponse:
    """Void a pending tab entry. Only the owning member can void their own entries."""
    from billing.forms import VoidTabEntryForm
    from billing.models import TabEntry as TabEntryModel
    from hub.toast import trigger_toast

    member = _get_member(request)
    if member is None:
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
```

- [ ] **Step 5: Update tab_detail.html with void confirm modals**

In `templates/hub/tab_detail.html`, add a "Void" button to each pending entry row and include confirm modals. Update the table body in the pending entries section:

Replace the `<tbody>` section (lines 51-59) with:

```html
            <tbody>
                {% for entry in entries %}
                <tr>
                    <td>{{ entry.description }}{% if entry.product %} <span class="tab-entry-guild">&rarr; {{ entry.product.guild.name }}</span>{% endif %}</td>
                    <td class="tab-table__right">${{ entry.amount }}</td>
                    <td class="tab-table__date">{{ entry.created_at|date:"M j, Y" }}</td>
                    <td>
                        <button type="button"
                                class="pl-btn pl-btn--secondary"
                                style="padding:0.25rem 0.5rem;font-size:0.75rem;"
                                @click="$dispatch('open-confirm', 'void-{{ entry.pk }}')">
                            Void
                        </button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
```

Add a header cell for the actions column in `<thead>`:

```html
                    <tr>
                        <th>Description</th>
                        <th class="tab-table__right">Amount</th>
                        <th>Date</th>
                        <th></th>
                    </tr>
```

After the table, add confirm modals for each entry (inside the hub-card):

```html
    {% for entry in entries %}
    <div x-data="{ open: false }"
         x-show="open"
         x-transition:enter="modal-enter"
         x-transition:leave="modal-leave"
         @open-confirm.window="if ($event.detail === 'void-{{ entry.pk }}') open = true"
         @keydown.escape.window="open = false"
         class="pl-modal-backdrop"
         style="display: none;">
        <div class="pl-modal pl-modal--sm" @click.outside="open = false">
            <div class="pl-modal__header">
                <h2 class="pl-modal__title">Void this charge?</h2>
                <button type="button" @click="open = false" class="pl-modal__close">&times;</button>
            </div>
            <div class="pl-modal__body">
                <p style="margin:0 0 1rem;">This will remove <strong>{{ entry.description }}</strong> (${{ entry.amount }}) from your tab.</p>
                <form hx-post="{% url 'hub_void_tab_entry' entry.pk %}" hx-swap="none"
                      @htmx:after-request="if (event.detail.successful) { open = false; location.reload(); }">
                    {% csrf_token %}
                    <div style="margin-bottom:1rem;">
                        {% include "components/form_field.html" with field=void_form.reason field_label="Reason" field_hint="Brief reason for voiding this charge" %}
                    </div>
                    <div class="pl-modal__actions">
                        <button type="submit" class="pl-btn pl-btn--danger" style="flex:1;">Void Charge</button>
                        <button type="button" @click="open = false" class="pl-btn pl-btn--secondary" style="flex:1;">Cancel</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    {% endfor %}
```

- [ ] **Step 6: Update the tab_detail view to include void_form in context**

In `hub/views.py`, update the `tab_detail` function to pass a `VoidTabEntryForm` in the context:

Add at the top of the function (inside the `else` block that builds context, before the return):

```python
    from billing.forms import VoidTabEntryForm
    void_form = VoidTabEntryForm()
```

And add `"void_form": void_form` to the render context dict.

- [ ] **Step 7: Run tests**

Run: `pytest tests/hub/void_entry_spec.py tests/hub/tab_views_spec.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add templates/hub/tab_detail.html hub/views.py hub/urls.py tests/hub/void_entry_spec.py
git commit -m "feat: void tab entry via confirm modal with toast notification"
```

---

## Phase 3: Template Migrations and Cleanup

### Task 12: Migrate Remaining Forms to Component Includes

**Files:**
- Modify: `templates/hub/profile_settings.html`
- Modify: `templates/hub/beta_feedback.html`
- Modify: `templates/hub/tab_detail.html` (self-service add form section)

- [ ] **Step 1: Read current templates to understand what needs migrating**

Read each template file to identify manual form field rendering that should be replaced with `{% include "components/form_field.html" %}`.

- [ ] **Step 2: Migrate profile_settings.html**

Replace manual field rendering with component includes. For each field in the form, replace the manual `<div class="hub-form-group">...</div>` with:

```html
{% include "components/form_field.html" with field=form.preferred_name %}
{% include "components/form_field.html" with field=form.pronouns %}
{# ... etc for each field ... #}
```

- [ ] **Step 3: Migrate beta_feedback.html**

Same pattern — replace manual form field HTML with component includes.

- [ ] **Step 4: Migrate the self-service add form in tab_detail.html**

The "Add to Tab" section at the bottom of `tab_detail.html` has manual form rendering. Replace with component includes.

- [ ] **Step 5: Verify all pages render correctly**

Run: `python manage.py runserver`
Check each migrated page in both dark and light themes.

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add templates/hub/profile_settings.html templates/hub/beta_feedback.html templates/hub/tab_detail.html
git commit -m "refactor: migrate remaining hub forms to use component includes"
```

---

### Task 13: Remove Old CSS Aliases and Clean Up

**Files:**
- Modify: `static/css/hub.css` (remove old `.hub-toggle`, `.hub-form-group` etc. if no longer referenced)

- [ ] **Step 1: Search for old class usage across all templates**

Search for `.hub-toggle`, `.hub-form-group`, `.hub-field-errors`, `.hub-field-hint` in all templates. If no template references them, the CSS rules can be removed.

Run: `grep -r "hub-toggle\|hub-form-group\|hub-field-errors\|hub-field-hint" templates/`

- [ ] **Step 2: Remove unreferenced CSS rules**

For any old class names no longer referenced in templates, remove the corresponding CSS rules from `hub.css`.

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add static/css/hub.css
git commit -m "chore: remove unused legacy CSS classes replaced by pl- component styles"
```

---

### Task 14: Final Verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v --tb=short`
Expected: All tests PASS, 100% coverage maintained

- [ ] **Step 2: Run linter and type checker**

Run: `ruff check . && ruff format --check . && mypy .`
Expected: No errors

- [ ] **Step 3: Manual smoke test**

Start the dev server and verify:
1. `/guilds/<pk>/` — products show, "Add to Cart" modal works, quantity picker, cart accumulates, "Confirm" creates entries, toast shows
2. `/guilds/<pk>/` — "+" button opens EYOP modal, form submits, toast shows
3. `/tab/` — Void button shows on pending entries, confirm modal works, toast shows
4. `/settings/emails/` — Toggle renders correctly with new component
5. `/admin/membership/guild/<pk>/change/` — "Is Active" toggle works in both main form and Add Product inline
6. `/admin/membership/guild/<pk>/change/` — No horizontal scroll, Add Product hidden behind button
7. All of the above work in both dark and light themes

- [ ] **Step 4: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final adjustments from smoke testing"
```
