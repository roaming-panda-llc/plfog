# plfog Codebase Index

## Apps

| App | Purpose |
|-----|---------|
| `membership/` | Core domain: Member, Guild, Space, Lease, voting, funding snapshots |
| `billing/` | Stripe tab system: Tab, TabEntry, TabCharge, StripeAccount, Product |
| `core/` | Auth infrastructure: Invite, SiteConfiguration, PushSubscription |
| `hub/` | Member-facing views (guild voting, directory, tab, profile) |
| `airtable_sync/` | Airtable bidirectional sync for members, spaces, leases, votes |
| `plfog/` | Django project: settings, urls, wsgi, auto_admin, adapters |
| `education/` | Placeholder (empty — migrations only) |
| `outreach/` | Placeholder (empty — migrations only) |
| `tools/` | Placeholder (empty — migrations only) |

## Key Models

### membership
- `Member` — makerspace member; has Status, MemberType, FogRole; linked 1:1 to User via allauth
- `MembershipPlan` — tiered pricing (monthly_price, deposit_required)
- `Guild` — interest guild; members vote on which guild receives funding
- `VotePreference` — persistent 3-choice ranked vote per member (synced to Airtable)
- `FundingSnapshot` — immutable historical funding calc; guild allocations stored in results JSON
- `Space` — physical space (studio/storage/parking/desk); linked to Airtable
- `Lease` — tenant→space via GenericForeignKey (tenant = Member or Guild)
- `MemberEmail` — additional email aliases per member

### billing
- `BillingSettings` — singleton (pk=1); controls charge frequency/day/time, default_tab_limit
- `StripeAccount` — Stripe Connect account per guild (acct_xxx)
- `Product` — purchasable product offered by a guild
- `Tab` — one per member; accumulates entries; holds stripe_customer_id + payment_method
- `TabEntry` — single line item; pending until included in a TabCharge
- `TabCharge` — batched Stripe charge; status: pending→processing→succeeded|failed

### core
- `SiteConfiguration` — singleton (pk=1); controls RegistrationMode (open / invite_only)
- `Invite` — email invite with pre-created Member placeholder; accepted on signup
- `PushSubscription` — Web Push subscription per user

## URL Structure

```
/admin/                         Django admin
/admin/membership/member/invite/ Custom invite action
/admin/take-snapshot/           Trigger funding snapshot
/accounts/                      allauth (login, signup, email verification)
/billing/payment-method/...     Stripe setup, confirm, remove
/billing/api/setup-intent/      AJAX — create Stripe SetupIntent
/billing/webhooks/stripe/       Stripe webhook receiver
/billing/admin/dashboard/       Billing admin dashboard
/billing/admin/add-entry/       Admin: add tab entry for any member
/billing/connect/initiate/<id>/ Initiate Stripe Connect for a guild
/billing/connect/callback/      Stripe Connect OAuth callback
/guilds/voting/                 Guild voting page
/guilds/voting/history/         Snapshot history
/guilds/voting/history/<pk>/    Snapshot detail
/guilds/<pk>/                   Guild detail with products
/members/                       Member directory
/settings/profile/              Profile settings
/settings/emails/               Email preferences
/feedback/                      Beta feedback form
/tab/                           My Tab (current balance + add entry)
/tab/history/                   Past billing charges
/                               Home / redirects (core.views)
```

## Test Structure

All tests in `tests/` mirroring app names:
```
tests/
  billing/          models/, management/, views, forms, webhook_handlers, stripe_utils, ...
  membership/       models, admin, forms, guild, signals, vote_calculator, ...
  hub/              views, guild_voting, tab_views, guild_pages, templatetags, ...
  core/             models, admin, checks, context_processors, home, ...
  airtable_sync/    client, service, config, airtable_pull, integration, ...
  auth/             allauth_spec.py
  admin/            admin_login_spec.py
  plfog/            adapters, auto_admin, dashboard, settings, wsgi
```

Factories: `tests/membership/factories.py`, `tests/billing/factories.py`

Root `conftest.py` provides:
- `_disable_airtable_sync` (autouse) — sets `AIRTABLE_SYNC_ENABLED=False`
- `_fake_stripe_keys` (autouse) — uses test-safe fake Stripe keys

## External Integrations

| Integration | App | Config |
|-------------|-----|--------|
| Stripe (Connect + PaymentIntents) | `billing/` | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_CLIENT_ID` |
| Airtable | `airtable_sync/` | `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_SYNC_ENABLED` |
| allauth (email auth) | `plfog/` | `ACCOUNT_*` settings in `plfog/settings.py` |
| Web Push | `core/` | `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_ADMIN_EMAIL` |
| Discord webhook | GitHub Actions only | `DISCORD_WEBHOOK_URL` secret in repo |

## Important Patterns

- **Airtable-managed records**: `Member`, `Space`, `Lease` are read-only from Django's perspective — pulled via `airtable_pull` command. No save/delete sync overrides on those models.
- **VotePreference + FundingSnapshot** sync TO Airtable on save (outbound only).
- **Tab.add_entry()** uses `select_for_update()` + `transaction.atomic()` to prevent race conditions on balance checks.
- **Tab charges to guilds** use Stripe Connect destination charges (`create_destination_payment_intent`); charges without a guild use standard PaymentIntents.
- **Fog roles** map to Django permissions: admin→is_superuser+is_staff, guild_officer→is_staff, member→neither.

## Version & Changelog

`plfog/version.py` contains `VERSION` and `CHANGELOG`. Must be bumped on every PR. Discord workflow reads CHANGELOG on merge to main.

## Deployment

- **Production**: Render.com (`DATABASE_URL` points to PostgreSQL)
- **QA/Staging**: Hetzner VPS at `pastlives.plaza.codes`
- **Local**: SQLite (default when `DATABASE_URL` unset)
- See memory file `deployment.md` for Hetzner deploy commands
