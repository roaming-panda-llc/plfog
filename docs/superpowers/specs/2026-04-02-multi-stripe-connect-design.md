# Multi-Stripe Account Support via Stripe Connect

## Context

Past Lives Makerspace has 12+ Stripe accounts — one per guild and one for the makerspace admin. The tab billing system (v1.3.0) currently charges everything through a single platform Stripe account. This feature adds Stripe Connect destination charges so that tab entries route money to the correct guild's Stripe account automatically.

## Approach

**Stripe Connect with Standard Connected Accounts and Destination Charges.**

- Past Lives' main Stripe account is the **platform**
- Each guild's existing Stripe account becomes a **connected account** via OAuth
- At billing time, entries are grouped by destination guild — each group becomes a separate destination charge
- Stripe handles the money transfer to connected accounts automatically
- Optional per-guild platform fee (percentage kept by makerspace) via `application_fee_amount`

## What Members See

### Adding to Tab
- Product picker on the My Tab page — active products grouped by guild
- Selecting a product auto-fills description and amount
- Manual entry option remains for non-product charges (routes to platform account)
- Pending entries show which guild they'll route to (e.g., "Clay - 5lb bag → Ceramics Guild")

### Tab History
- Each charge shows which account it was routed to
- Multiple charges may appear for a single billing cycle if entries span multiple guilds

### Payment Method
- No changes. The member's payment method is attached to the platform customer. Stripe Connect destination charges accept platform customer payment methods natively — no cloning or per-account customers needed.

## What Admins See

### Stripe Accounts (new admin section)
- List of connected guild Stripe accounts with status (active/disconnected)
- "Connect" button per guild → starts OAuth flow with Stripe
- "Disconnect" button → clears connection, deactivates account
- Platform fee percentage per guild (default 0%, configurable)

### Products (new admin section)
- Product catalog: name, price, guild, active toggle
- Each product is tied to a guild — the guild's connected Stripe account is the charge destination
- Superadmin-only for MVP (guild self-service is future)

### Admin Add-Entry
- Product dropdown added to the quick-add form
- Manual entries (no product) continue to route to the platform

## New Models

### StripeAccount

| Field | Type | Notes |
|---|---|---|
| `guild` | OneToOneField(Guild, null/blank, on_delete=SET_NULL) | Null for makerspace admin account |
| `stripe_account_id` | CharField(255) | The `acct_xxx` ID from Connect OAuth |
| `display_name` | CharField(255) | "Ceramics Guild", "Past Lives Admin" |
| `is_active` | BooleanField(default=True) | Toggle to disable without deleting |
| `platform_fee_percent` | DecimalField(5,2, default=0) | Percentage kept by platform (0-100) |
| `connected_at` | DateTimeField(null/blank) | When OAuth link completed |
| `created_at` | DateTimeField(auto_now_add) | |

### Product

| Field | Type | Notes |
|---|---|---|
| `name` | CharField(255) | "Clay - 5lb bag" |
| `price` | DecimalField(8,2) | Default price |
| `guild` | ForeignKey(Guild, on_delete=CASCADE) | Determines charge destination |
| `is_active` | BooleanField(default=True) | |
| `created_by` | ForeignKey(User, SET_NULL, null) | |
| `created_at` | DateTimeField(auto_now_add) | |

### TabEntry Changes

| Field | Type | Notes |
|---|---|---|
| `product` | ForeignKey(Product, SET_NULL, null/blank) | When set, routing is `product.guild.stripe_account` |

Routing logic: `entry.product.guild.stripe_account` → destination. No product → platform account (direct charge, same as today).

### TabCharge Changes

| Field | Type | Notes |
|---|---|---|
| `stripe_account` | ForeignKey(StripeAccount, SET_NULL, null/blank) | Destination account. Null = platform direct charge. |
| `application_fee` | DecimalField(8,2, null/blank) | Platform fee amount collected on this charge |

## Billing Engine Changes

### Entry Grouping

Today: one TabCharge per member (all entries bundled).
New: entries grouped by destination, one TabCharge per group.

Grouping logic:
1. Partition pending entries into groups by `entry.product.guild` (or "platform" if no product)
2. Each group becomes its own TabCharge
3. Skip groups below $0.50

### Charge Flow Per Group

**Guild destination charge:**
```
stripe.PaymentIntents.create(
    customer=tab.stripe_customer_id,
    payment_method=tab.stripe_payment_method_id,
    amount=group_total_cents,
    currency="usd",
    transfer_data={"destination": stripe_account.stripe_account_id},
    application_fee_amount=fee_cents,  # only if platform_fee_percent > 0
    off_session=True,
    confirm=True,
)
```

**Platform direct charge (no product / future dues/rent):**
Same as today — no `transfer_data`, no `application_fee_amount`.

### Retries and Locking

Each TabCharge retries independently. A member's tab locks only when ALL their charges from a billing cycle have exhausted retries, not when a single guild's charge fails.

### Concrete Example

Member's pending entries:
- Clay ($12) → Ceramics Guild (15% platform fee)
- Glass beads ($8) → Glass Guild (0% fee)
- Manual charge ($5) → no product

Billing creates 3 TabCharges:
1. $12 destination charge to Ceramics connected account. $1.80 application fee to platform.
2. $8 destination charge to Glass connected account. No fee.
3. $5 direct charge to platform account.

## Stripe Connect OAuth Flow

### Linking a Guild Account

1. Superadmin clicks "Connect" for a guild in admin
2. Redirected to Stripe's hosted Connect OAuth page
3. Guild owner authorizes Past Lives Makerspace
4. Stripe redirects back with authorization code
5. Callback exchanges code for `acct_xxx`, saves to StripeAccount

### Disconnecting

Admin clicks "Disconnect" → clears `stripe_account_id`, sets `is_active=False`. Products remain but can't be charged to the guild until reconnected. At billing time, entries whose guild has a disconnected/missing Stripe account are **skipped** (not charged, not grouped) and an admin warning is logged. This prevents money from silently going to the wrong place — the admin must either reconnect the guild or void the entries.

### Webhook Behavior

Destination charges fire webhooks on the **platform** account. No changes to existing webhook endpoint — `payment_intent.succeeded` and `payment_intent.payment_failed` continue to work as-is.

## Refunds

- **Pre-charge voiding** — unchanged, no Stripe interaction
- **Post-charge refunds** — deferred to post-MVP. Admins use Stripe dashboard directly. Stripe Connect handles transfer reversal automatically for destination charges.

## stripe_utils.py Changes

New/modified functions:
- `create_destination_payment_intent(*, customer_id, payment_method_id, amount_cents, description, metadata, idempotency_key, destination_account_id, application_fee_cents=None)` — new function for Connect destination charges
- Existing `create_payment_intent` stays unchanged for platform direct charges
- `get_connect_oauth_url(*, guild_id)` — generates the OAuth redirect URL
- `complete_connect_oauth(*, code)` — exchanges auth code for account ID

## Files to Create

- `billing/models.py` — add StripeAccount, Product models
- `billing/connect_views.py` — OAuth initiation + callback views
- `billing/connect_urls.py` — Connect OAuth routes
- `templates/billing/admin_connect_accounts.html`
- `tests/billing/models/stripe_account_spec.py`
- `tests/billing/models/product_spec.py`
- `tests/billing/connect_views_spec.py`

## Files to Modify

- `billing/models.py` — add `product` FK to TabEntry, add `stripe_account` + `application_fee` to TabCharge
- `billing/admin.py` — register StripeAccount, Product admins
- `billing/stripe_utils.py` — add destination charge + OAuth functions
- `billing/management/commands/bill_tabs.py` — grouping logic, destination charges
- `billing/views.py` — update admin add-entry with product picker
- `billing/forms.py` — update forms with product field
- `hub/views.py` — update tab_detail with product picker
- `hub/forms.py` — update AddTabEntryForm with product field
- `templates/hub/tab_detail.html` — product picker, guild labels on entries
- `templates/hub/tab_history.html` — show destination per charge
- `plfog/settings.py` — add STRIPE_CONNECT_CLIENT_ID env var, Unfold sidebar entries

## Out of Scope

- Dues/rent routing through Connect (future: add as entry types with destinations)
- Refund model (future: use Stripe dashboard for now)
- Guild self-service product management
- Inventory or quantity tracking
- Individual commission payouts to guild leads
- Per-product platform fee override (uses guild-level fee)

## Migration Path to Full Connect (Future)

When ready to route dues/rent through Connect:
1. Create a StripeAccount for the makerspace admin (connected to itself or a designated account)
2. Add entry types for DUES, RENT with guild/destination mapping
3. All charges become destination charges — no more direct platform charges
4. No architectural changes needed, just data configuration
