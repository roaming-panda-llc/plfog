# Stripe Payment Element Upgrade

**Date:** 2026-04-03
**Branch:** feat/tab-billing

## Summary

Replace the legacy Stripe `CardElement` on the payment method setup page with the modern `PaymentElement`. This enables:

- Stripe Link — users enter their email and retrieve a previously saved card via phone verification (no card number typing required)
- Apple Pay and Google Pay — wallet buttons appear automatically when the browser supports them
- Better visual rendering — the Payment Element adapts to the site theme and renders labeled fields rather than a single compressed row

This is a frontend-only change. The backend (`create_setup_intent_api`, `confirm_setup`, `stripe_utils.py`, `webhook_handlers.py`, `models.py`) is entirely unchanged.

CC data is never sent to or stored by plfog in either the old or new implementation. Stripe tokenizes everything client-side.

---

## Architecture

### What changes

**`templates/billing/setup_payment_method.html`** — the only file modified.

The JavaScript initialization and submit handler are rewritten. The HTML structure gains a new mount point (`#payment-element` instead of `#card-element`). Everything else — page structure, the "current card" block, the remove form, the back link — stays the same.

### What does not change

| File | Status |
|------|--------|
| `billing/views.py` | Unchanged |
| `billing/stripe_utils.py` | Unchanged |
| `billing/webhook_handlers.py` | Unchanged |
| `billing/models.py` | Unchanged |
| `billing/urls.py` | Unchanged |
| All other templates | Unchanged |

---

## Implementation Detail

### Initialization

```javascript
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
```

`mode: 'setup'` tells the Payment Element this is a SetupIntent flow (not a one-time payment). `setupFutureUsage: 'off_session'` signals the card will be charged later without the user present — Stripe uses this to enable 3DS authentication upfront where required.

### Submit flow (deferred intent)

The SetupIntent is created lazily on submit, not on page load. This avoids creating abandoned SetupIntents for users who navigate away.

```
1. User clicks Save
2. elements.submit()          — validates fields, activates wallets if selected
3. POST /billing/api/setup-intent/  — creates SetupIntent, returns client_secret
4. stripe.confirmSetup(...)   — tokenizes card, confirms with Stripe
5. POST /billing/payment-method/confirm/  — saves payment_method_id to Tab
6. Redirect to hub_tab_detail
```

`confirmSetup` is called with `redirect: 'if_required'` so card and wallet payments stay in-page. The `return_url` is included as a required parameter fallback (used only for redirect-based payment methods like bank redirects, which aren't expected here but Stripe requires the field).

### Apple Pay / Google Pay

No extra configuration needed. The Payment Element shows wallet buttons automatically when:
- The browser supports the relevant wallet (Safari for Apple Pay, Chrome for Google Pay)
- The domain is registered in the Stripe dashboard (must be done once)

The wallet payment completes entirely within the browser's native payment sheet. The result comes back as a `payment_method_id` just like a card — the confirm endpoint receives it identically.

### Stripe Link

The Payment Element includes a Link email field by default. When a user enters an email associated with a Stripe Link account, Stripe sends a one-time code to their phone. On verification, the card auto-fills. From plfog's perspective this is transparent — the result is still a `payment_method_id`.

---

## Error Handling

- `elements.submit()` returns validation errors (empty fields, invalid card number) — displayed in an error div below the element
- SetupIntent creation failure (network error, server error) — displayed in the same error div, button re-enabled
- `stripe.confirmSetup()` failure (card declined, authentication failed) — Stripe returns an error object, displayed in the error div, button re-enabled
- On any error the submit button is re-enabled and its label restored to "Save Card"

---

## Testing

No new test files needed — the backend is unchanged and already covered. Manual verification:

1. Add a card via card number — confirm it appears on tab detail
2. Add a card via Apple Pay (Safari) — confirm it saves correctly
3. Enter an email with a Stripe Link account — confirm the phone verification prompt appears
4. Submit with an invalid card number — confirm inline error appears
5. Replace an existing card — confirm the old payment method is detached and new one saved
6. Remove a card — confirm it is detached and cleared from the tab

---

## Stripe Dashboard Prerequisite

To enable Apple Pay / Google Pay, the plfog domain must be registered under **Stripe Dashboard → Settings → Payment methods → Apple Pay**. This is a one-time manual step, not a code change.
