# billing app

Stripe tab billing system. Members accumulate charges on a tab; a management command batches and charges them.

## Models

| Model | Key fields | Notes |
|-------|-----------|-------|
| `BillingSettings` | charge_frequency, charge_time, default_tab_limit, max_retry_attempts | Singleton (pk=1); load via `BillingSettings.load()` |
| `StripeAccount` | guild 1:1, stripe_account_id (acct_xxx), platform_fee_percent | Stripe Connect per guild |
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

## URLs (prefix: /billing/)

- `payment-method/setup/` → `setup_payment_method` — renders Stripe Payment Element iframe
- `api/setup-intent/` → `create_setup_intent_api` — AJAX endpoint returns client_secret
- `payment-method/confirm/` → `confirm_setup` — confirms SetupIntent, saves PM to Tab
- `payment-method/remove/` → `remove_payment_method`
- `webhooks/stripe/` → `stripe_webhook` — handles payment_intent.succeeded/.payment_failed
- `admin/dashboard/` → `admin_tab_dashboard`
- `admin/add-entry/` → `admin_add_tab_entry`
- `connect/initiate/<guild_id>/` / `connect/callback/` — Stripe Connect OAuth

## Management Command

`billing/management/commands/bill_tabs.py` — groups pending `TabEntry` records by guild, creates `TabCharge` per group, executes Stripe charges. Run on schedule per `BillingSettings.charge_frequency`.

## Factories

`tests/billing/factories.py` — `TabFactory`, `TabEntryFactory`, `TabChargeFactory`, `ProductFactory`, `StripeAccountFactory`, `BillingSettingsFactory`.
