# Stripe Payment Element Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy Stripe CardElement with the modern Payment Element to enable Stripe Link (email/phone card lookup), Apple Pay, and Google Pay on the payment method setup page.

**Architecture:** Single template file change — `templates/billing/setup_payment_method.html`. The mount point changes from `#card-element` to `#payment-element`, and the JavaScript is rewritten to use the deferred intent flow: `elements.submit()` → create SetupIntent → `stripe.confirmSetup()`. The backend is entirely unchanged.

**Tech Stack:** Stripe.js v3 Payment Element, Django templates, vanilla JS (no framework)

---

## Files

| Action | Path |
|--------|------|
| Modify | `templates/billing/setup_payment_method.html` |

No other files change. Backend (`billing/views.py`, `billing/stripe_utils.py`, `billing/webhook_handlers.py`, `billing/models.py`, `billing/urls.py`) is untouched.

---

### Task 1: Replace CardElement with Payment Element

**Files:**
- Modify: `templates/billing/setup_payment_method.html`

- [ ] **Step 1: Replace the template**

Replace the entire contents of `templates/billing/setup_payment_method.html` with:

```html
{% extends "hub/base.html" %}
{% block title %}Payment Method{% endblock %}

{% block content %}
<div class="tab-page-header">
    <h1 class="hub-page-title">Payment Method</h1>
    <a href="{% url 'hub_tab_detail' %}" class="tab-history-link">Back to My Tab</a>
</div>

{% if tab.has_payment_method %}
<div class="hub-card">
    <h2 class="tab-section-title">Current Card</h2>
    <p style="margin-bottom: 1rem;">
        <strong>{{ tab.payment_method_brand|title }}</strong> ending in <strong>{{ tab.payment_method_last4 }}</strong>
    </p>
    <form method="post" action="{% url 'billing_remove_payment_method' %}">
        {% csrf_token %}
        <button type="submit" class="tab-add-form__btn" style="background: var(--color-error-bg); color: var(--color-error);">
            Remove Card
        </button>
    </form>
</div>
{% endif %}

<div class="hub-card">
    <h2 class="tab-section-title">{% if tab.has_payment_method %}Replace Card{% else %}Add a Card{% endif %}</h2>
    <p class="hub-text-muted" style="margin-bottom: 1rem;">
        By adding a payment method, you authorize Past Lives Makerspace to charge your card
        for accumulated tab balances on the billing schedule set by the organization.
    </p>
    <div id="payment-element" style="margin-bottom: 1rem;"></div>
    <div id="payment-errors" class="tab-form-error" style="margin-bottom: 0.75rem;"></div>
    <button id="submit-btn" class="tab-add-form__btn">Save Card</button>
</div>

<script src="https://js.stripe.com/v3/"></script>
<script>
(function() {
    const stripe = Stripe('{{ stripe_publishable_key }}');
    const elements = stripe.elements({
        mode: 'setup',
        currency: 'usd',
        setupFutureUsage: 'off_session',
        appearance: {
            theme: 'night',
            variables: {
                colorPrimary: '#3b82f6',
                fontFamily: 'Inter, system-ui, sans-serif',
                borderRadius: '6px',
            }
        }
    });
    const paymentElement = elements.create('payment');
    paymentElement.mount('#payment-element');

    const errorEl = document.getElementById('payment-errors');
    const submitBtn = document.getElementById('submit-btn');

    submitBtn.addEventListener('click', async function() {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';
        errorEl.textContent = '';

        // 1. Validate fields and activate wallet if selected
        const { error: submitError } = await elements.submit();
        if (submitError) {
            errorEl.textContent = submitError.message;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save Card';
            return;
        }

        // 2. Create SetupIntent via our API (lazy — only on submit)
        const intentResp = await fetch('{% url "billing_create_setup_intent" %}', {
            method: 'POST',
            headers: {
                'X-CSRFToken': '{{ csrf_token }}',
                'Content-Type': 'application/json'
            }
        });
        const intentData = await intentResp.json();

        if (intentData.error) {
            errorEl.textContent = intentData.error;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save Card';
            return;
        }

        // 3. Confirm the SetupIntent with the payment element
        // return_url is required by Stripe but only used for redirect-based payment
        // methods (e.g. bank redirects) — cards and wallets stay in-page.
        const returnUrl = window.location.origin + '{% url "billing_confirm_setup" %}';
        const { setupIntent, error } = await stripe.confirmSetup({
            elements,
            clientSecret: intentData.client_secret,
            confirmParams: { return_url: returnUrl },
            redirect: 'if_required'
        });

        if (error) {
            errorEl.textContent = error.message;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save Card';
            return;
        }

        // 4. POST the payment method ID to our confirm endpoint (same as before)
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '{% url "billing_confirm_setup" %}';

        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = '{{ csrf_token }}';
        form.appendChild(csrfInput);

        const pmInput = document.createElement('input');
        pmInput.type = 'hidden';
        pmInput.name = 'payment_method_id';
        pmInput.value = setupIntent.payment_method;
        form.appendChild(pmInput);

        document.body.appendChild(form);
        form.submit();
    });
})();
</script>
{% endblock %}
```

Key differences from the old template:
- `#card-element` → `#payment-element`
- `#card-errors` → `#payment-errors`
- Submit button no longer starts `disabled` (Payment Element validates via `elements.submit()`)
- No `cardElement.on('change', ...)` listener (removed — not used by Payment Element)
- New JS: `stripe.elements({ mode: 'setup', ... })` with `appearance` config
- New submit flow: `elements.submit()` → fetch setup intent → `stripe.confirmSetup()`

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
cd /Users/joshplaza/Code/hexagonstorms/plfog
pytest billing/ -v
```

Expected: all billing tests pass. The view tests render templates and check context — the template swap doesn't affect them.

- [ ] **Step 3: Run linter**

```bash
ruff check . && ruff format .
```

Expected: no errors (no Python changed, template files aren't linted).

- [ ] **Step 4: Manual verification checklist**

Start the dev server: `python manage.py runserver`

Navigate to `/billing/payment-method/` and verify:

1. **Payment Element renders** — you see labeled card fields (Card number, Expiry, CVC) instead of a single compressed row
2. **Stripe Link email field** — an email input appears above the card fields; entering a known Stripe Link email triggers the phone verification prompt
3. **Apple Pay / Google Pay** — wallet buttons appear in Safari / Chrome when the browser supports them (requires domain registered in Stripe dashboard)
4. **Card entry works** — use Stripe test card `4242 4242 4242 4242`, exp `12/34`, CVC `123`; clicking Save Card should redirect to tab detail with the card saved
5. **Validation error** — click Save Card with empty fields; an inline error appears and the button re-enables
6. **Replace card** — if a card is already on file, the "Replace Card" section shows the new Payment Element; saving replaces the stored payment method
7. **Remove card** — the Remove Card button still works (form POST, no JS involved)

- [ ] **Step 5: Commit**

```bash
git add templates/billing/setup_payment_method.html
git commit -m "feat: upgrade payment form to Stripe Payment Element with Link and wallet support"
```

---

## Post-Deploy: Stripe Dashboard Step

After deploying, register the production domain for Apple Pay:

**Stripe Dashboard → Settings → Payment methods → Apple Pay → Add domain**

This is a one-time manual step. Apple Pay buttons will not appear until this is done. Google Pay requires no registration.
