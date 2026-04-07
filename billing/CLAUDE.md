# billing app

Stripe tab billing system. Members accumulate charges on a tab; a management command batches and charges them.

## Models

| Model | Key fields | Notes |
|-------|-----------|-------|
| `BillingSettings` | charge_frequency, charge_time, default_tab_limit, max_retry_attempts | Singleton (pk=1); load via `BillingSettings.load()` |
| `StripeAccount` | guild 1:1, auth_mode, stripe_account_id, direct_secret_key, direct_webhook_secret, platform_fee_percent | Two modes: `oauth` (Stripe Connect) or `direct_keys` (pasted API keys, encrypted at rest) |
| `Product` | name, price, guild FK, is_active | Purchasable item offered by a guild |
| `Tab` | member 1:1, stripe_customer_id, stripe_payment_method_id, is_locked | One per member; accumulates entries |
| `TabEntry` | tab FK, tab_charge FK (null=pending), amount, voided_at | Single line item |
| `TabCharge` | tab FK, stripe_account FK, status, amount, stripe_payment_intent_id | Batched charge; links to entries |

## Tab Flow

1. Member adds payment method → `Tab.set_payment_method()` attaches to Stripe customer
2. Entries accumulate via `Tab.add_entry()` (race-safe with `select_for_update`)
3. `bill_tabs` management command: groups pending entries by guild → creates `TabCharge` records → calls `TabCharge.execute_stripe_charge()`
4. Webhook handlers update charge status on Stripe events
5. On failure: `BillingSettings.max_retry_attempts` retries, then `Tab.lock()`

## Exceptions (billing/exceptions.py)

- `TabLockedError` — tab is locked (failed payment)
- `NoPaymentMethodError` — no payment method on file
- `TabLimitExceededError` — entry would exceed `Tab.effective_tab_limit`

## Stripe Utils (billing/stripe_utils.py)

Thin wrapper around stripe SDK. Key functions:
- `create_customer()` — creates Stripe customer
- `attach_payment_method()` / `detach_payment_method()`
- `retrieve_payment_method()` → `{id, last4, brand}`
- `create_payment_intent()` — standard charge (no Connect)
- `create_destination_payment_intent()` — Connect destination charge with application fee
- `create_setup_intent()` — for collecting payment method without charging

## Multi-Stripe Connect

Entries for products under different guilds are grouped by `StripeAccount`. If a guild has no `StripeAccount`, charge falls back to platform (no Connect).

`StripeAccount.compute_fee(amount)` calculates platform fee. `TabCharge.execute_stripe_charge()` passes `application_fee_cents` when charging to a destination account.

### Two auth modes

`StripeAccount.auth_mode` selects how charges are routed:

1. **`oauth`** — Stripe Connect destination charges. Customer + payment method live on the
   PL platform account. `application_fee_amount` skims `platform_fee_percent` to PL.
   Requires `STRIPE_CONNECT_CLIENT_ID` to be set on a registered Connect platform.
2. **`direct_keys`** — Each guild's own Stripe secret/publishable/webhook keys are pasted
   into the admin (encrypted at rest via `EncryptedCharField`/Fernet). Charges create
   hosted **Checkout sessions** on the guild's account directly. The member opens the
   returned `stripe_checkout_url` to pay; the per-guild webhook flips the charge to
   SUCCEEDED on `checkout.session.completed`. **No platform fee** — `clean()` enforces
   `platform_fee_percent == 0` in this mode. Use for consumables.

### Encryption key

Direct-keys mode requires `STRIPE_FIELD_ENCRYPTION_KEY` (a Fernet key) in the env. Generate with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set on local, Hetzner, and Render. **Losing this key bricks all stored direct-mode credentials.**

### Webhook URLs

- `/billing/webhooks/stripe/` — global, uses `STRIPE_WEBHOOK_SECRET`. Used for OAuth/platform events.
- `/billing/webhooks/stripe/guild/<guild_id>/` — per-guild, uses `StripeAccount.direct_webhook_secret`. Each direct-keys guild configures their own webhook in their Stripe dashboard pointing here.

## URLs (prefix: /billing/)

- `payment-method/setup/` → `setup_payment_method` — renders Stripe Payment Element iframe
- `api/setup-intent/` → `create_setup_intent_api` — AJAX endpoint returns client_secret
- `payment-method/confirm/` → `confirm_setup` — confirms SetupIntent, saves PM to Tab
- `payment-method/remove/` → `remove_payment_method`
- `webhooks/stripe/` → `stripe_webhook` — handles payment_intent.succeeded/.payment_failed
- `admin/dashboard/` → `admin_tab_dashboard`
- `admin/add-entry/` → `admin_add_tab_entry`
- `connect/initiate/<guild_id>/` / `connect/callback/` — Stripe Connect OAuth
- `admin/direct-keys/test/` — AJAX: verify a pasted secret key (`verify_account_credentials`)
- `admin/direct-keys/save/` — POST: persist a guild's direct-mode credentials (`upsert_direct_keys`)
- `webhooks/stripe/guild/<guild_id>/` — per-guild webhook for direct-keys mode

## Management Command

`billing/management/commands/bill_tabs.py` — groups pending `TabEntry` records by guild, creates `TabCharge` per group, executes Stripe charges. Run on schedule per `BillingSettings.charge_frequency`.

## Factories

`tests/billing/factories.py` — `TabFactory`, `TabEntryFactory`, `TabChargeFactory`, `ProductFactory`, `StripeAccountFactory`, `BillingSettingsFactory`.
