# billing app

Stripe tab billing system. Members accumulate charges on a tab; a management command batches and charges them.

## Models

| Model | Key fields | Notes |
|-------|-----------|-------|
| `BillingSettings` | charge_frequency, charge_time, default_tab_limit, default_admin_percent, max_retry_attempts, connect_platform_* | Singleton (pk=1); load via `BillingSettings.load()` |
| `Product` | name, price, guild FK (nullable, display-only), revenue_split O2O, is_active | Purchasable item. `guild` controls which guild page the product appears on; revenue is split per `revenue_split`. |
| `RevenueSplit` | name, created_at | Reusable container for a set of payout recipients. Attached 1:1 to a Product. Must sum to exactly 100%. |
| `SplitRecipient` | split FK, guild FK (nullable=Admin), percent | One row in a RevenueSplit. `guild=None` means the Admin (Past Lives) share. |
| `Tab` | member 1:1, stripe_customer_id, stripe_payment_method_id, is_locked | One per member; accumulates entries |
| `TabEntry` | tab FK, tab_charge FK (null=pending), amount, voided_at, **split_snapshot** | Single line item. `split_snapshot` is a JSON list of `{guild_id, percent}` frozen at creation time in `Tab.add_entry()`. |
| `TabCharge` | tab FK, status, amount, stripe_payment_intent_id | Batched charge — one per tab per billing cycle |

**TabEntry.split_snapshot** is frozen at creation time from the product's `RevenueSplit`. Never recomputed at read time — historical reports stay stable when the underlying RevenueSplit changes later.

## Revenue split

Every product has its own private `RevenueSplit` with a list of `SplitRecipient` rows. Each recipient is either the Admin (guild=None) or a specific Guild, with a percent share. Recipients must sum to exactly 100%.

Owning guild (`Product.guild`) is **independent** from the revenue split — a product owned by Glass Guild can pay out to any combination of Admin + guilds. The owning guild only controls which guild page the product appears on.

`TabEntry.compute_splits()` walks `split_snapshot` in order and assigns each recipient `floor(entry_amount_cents * percent / 100)` cents, then distributes any rounding remainder one cent at a time to recipients in snapshot order. This is deterministic and always sums exactly to `entry.amount`. Returns a list of `EntrySplit(guild_id, amount)` where `guild_id=None` means the Admin row.

Manual (product-less) entries fall back to an implicit `[{guild_id: None, percent: 100}]` split — 100% to Admin.

New products auto-provision a default split via `Product.save()`: `BillingSettings.default_admin_percent` to Admin, remainder to the owning guild (if set), else 100% to Admin. Admins can then refine the split in the RevenueSplit admin page.

Guild payouts are reconciled manually via the admin Reports page; no automated Stripe Connect payouts (yet).

## Tab Flow

1. Member adds payment method → `Tab.set_payment_method()` attaches to Stripe customer
2. Entries accumulate via `Tab.add_entry()` (race-safe with `select_for_update`). Snapshots split fields onto each entry.
3. `bill_tabs` management command: for each tab with pending entries, creates ONE `TabCharge` with the sum of all pending amounts → calls `TabCharge.execute_stripe_charge()`
4. Webhook handlers update charge status on Stripe events
5. On failure: `BillingSettings.max_retry_attempts` retries, then `Tab.lock()`

## Single Stripe Account

All charges route through one platform Stripe account — credentials live on `BillingSettings` (encrypted). No per-guild Stripe accounts, no destination charges, no direct-keys Checkout. This was simplified in v1.5.0.

**Prereq**: `Tab.can_add_entry` requires a saved payment method on file. Off-session PaymentIntents don't work without one.

## Exceptions (billing/exceptions.py)

- `TabLockedError` — tab is locked (failed payment)
- `NoPaymentMethodError` — no payment method on file
- `TabLimitExceededError` — entry would exceed `Tab.effective_tab_limit`

## Stripe Utils (billing/stripe_utils.py)

Thin wrapper around stripe SDK. All functions use the single platform Stripe client (`_get_stripe_client()`).

- `create_customer()` — creates Stripe customer
- `attach_payment_method()` / `detach_payment_method()`
- `retrieve_payment_method()` → `{id, last4, brand}`
- `create_payment_intent()` — standard off-session PaymentIntent (the only charge path)
- `create_setup_intent()` — for collecting payment method without charging
- `construct_webhook_event()` — verify incoming Stripe webhook
- `verify_platform_credentials()` — test a pasted platform secret key from the Settings tab

### Encryption key

The Fernet encryption key (`STRIPE_FIELD_ENCRYPTION_KEY`) encrypts `BillingSettings.connect_platform_secret_key` and `connect_platform_webhook_secret`. Generate with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set on local, Hetzner, and Render. **Losing this key bricks the stored Stripe credentials.**

## URLs (prefix: /billing/)

- `payment-method/setup/` → renders Stripe Payment Element iframe
- `api/setup-intent/` → AJAX endpoint returns client_secret
- `payment-method/confirm/` → saves PM to Tab
- `payment-method/remove/` → detaches PM
- `webhooks/stripe/` → handles payment_intent.succeeded/.payment_failed
- `admin/dashboard/` → multi-tab admin payments page
- `admin/add-entry/` → admin add-charge-to-tab
- `admin/connect-platform/test/` → AJAX verify pasted platform secret
- `admin/connect-platform/save/` → persist platform credentials

## Management Command

`billing/management/commands/bill_tabs.py` — creates one `TabCharge` per tab with pending entries and executes the Stripe charge. Run on schedule per `BillingSettings.charge_frequency`.

## Factories

`tests/billing/factories.py` — `TabFactory`, `TabEntryFactory`, `TabChargeFactory`, `ProductFactory`, `BillingSettingsFactory`.
