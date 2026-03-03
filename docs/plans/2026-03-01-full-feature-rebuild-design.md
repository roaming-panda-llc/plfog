# plfog Full Feature Rebuild — Design Document

**Date:** 2026-03-01
**Goal:** Port all missing features from makerspace-tea (Laravel/Filament) to plfog (Django/Unfold), deploy to plos.plaza.codes.

## Decisions

- **Scope:** Single PR covering all missing features
- **Stripe:** Full integration via dj-stripe
- **UI:** Admin-only (django-unfold), no separate member portal
- **Permissions:** django-guardian for object-level permissions
- **User/Member:** Keep Member as separate model (OneToOne to auth.User)

## Current State (plfog)

6 models in `membership` app: MembershipPlan, Member, Guild, GuildVote, Space, Lease.
Auth via django-allauth (Google, GitHub, Discord). Admin via django-unfold. Docker + CI/CD. 100% test coverage.

## New App Structure

| App | Purpose | New Models |
|-----|---------|-----------|
| `membership` (existing) | Members, plans, spaces, leases, guilds | Enhanced Guild, GuildMembership, GuildDocument, GuildWishlistItem, MemberSchedule, ScheduleBlock |
| `billing` (new) | Tab system, orders, invoices, payouts | Order, Invoice, RevenueSplit, Payout, SubscriptionPlan, MemberSubscription |
| `tools` (new) | Equipment tracking, rentals, reservations | Tool, ToolReservation, Rentable, Rental, Document |
| `education` (new) | Classes, orientations | MakerClass, ClassSession, ClassImage, ClassDiscountCode, Student, Orientation, ScheduledOrientation |
| `outreach` (new) | Leads, tours, events, buyables | Lead, Tour, Event, Buyable, BuyablePurchase |
| `core` (existing) | Auth, health, home, settings | Setting |

## Data Models

### billing app

**RevenueSplit** — name (unique), splits (JSONField: [{entity_type, entity_id, percentage}]), notes

**Order** — user (FK User), description, amount (int, cents), revenue_split (FK), status (on_tab|billed|paid|failed), orderable (GenericFK), issued_at, billed_at

**Invoice** — user (FK User), stripe_invoice_id, amount_due (int, cents), amount_paid (int, cents), status, line_items (JSONField), pdf_url, issued_at, paid_at

**Payout** — payee_type (user|guild), payee_id, amount (int, cents), invoice_ids (JSONField), status (pending|distributed), distributed_at, distributed_by (FK User), period_start, period_end

**SubscriptionPlan** — name, description, price (Decimal), interval (monthly|yearly), stripe_price_id, plan_type, is_active

**MemberSubscription** — user (FK User), subscription_plan (FK), stripe_subscription_id, status (active|cancelled|past_due), discount_percentage, starts_at, ends_at, next_billing_at, cancelled_at

### tools app

**Tool** — guild (FK), name, description, image, estimated_value, owner_type (guild|member|org), owner_id, is_reservable, is_rentable, notes

**ToolReservation** — tool (FK), user (FK), starts_at, ends_at, status (active|completed|cancelled)

**Rentable** — tool (FK), rental_period (hours|days|weeks), cost_per_period, revenue_split (FK), is_active

**Rental** — rentable (FK), user (FK), checked_out_at, due_at, returned_at, status (active|returned|overdue), order (FK Order)

**Document** — content_type + object_id (GenericFK), name, file_path (FileField), uploaded_by (FK User)

### education app

**MakerClass** — guild (FK, null), name, description, image, location, price, max_students, revenue_split (FK), registration_email_copy, status (draft|published|archived), created_by (FK User), published_at, instructors (M2M User), discount_codes (M2M ClassDiscountCode)

**ClassSession** — maker_class (FK), starts_at, ends_at, notes

**ClassImage** — maker_class (FK), image_path, sort_order

**ClassDiscountCode** — code (unique), discount_type (percentage|fixed), discount_value, is_active. Method: calculate_discount(price)

**Student** — maker_class (FK), user (FK, null), name, email, phone, discount_code (FK, null), amount_paid, invoice_id, registered_at

**Orientation** — guild (FK), name, description, duration_minutes, price, revenue_split (FK), is_active, tools (M2M Tool), orienters (M2M User)

**ScheduledOrientation** — orientation (FK), user (FK, student), scheduled_at, claimed_by (FK User, orienter), claimed_at, completed_at, status (pending|claimed|completed|cancelled), order (FK Order)

### outreach app

**Lead** — name, email, phone, interests, notes, source, status (new|contacted|toured|converted|lost), greenlighted_for_membership

**Tour** — lead (FK), scheduled_at, claimed_by (FK User), claimed_at, completed_at, completion_notes, status (scheduled|claimed|completed|cancelled|no_show)

**Event** — guild (FK, null), name, description, starts_at, ends_at, location, is_recurring, recurrence_rule, created_by (FK User), is_published

**Buyable** — guild (FK, null), name, description, image, unit_price, revenue_split (FK), total_quantity_sold, is_active

**BuyablePurchase** — buyable (FK), user (FK), quantity, order (FK Order), purchased_at

### membership app (enhancements)

**Guild** (add fields) — slug (SlugField unique), intro, description, cover_image, icon, is_active, members (M2M User through GuildMembership)

**GuildMembership** (new) — guild (FK), user (FK), is_lead, joined_at

**GuildDocument** — guild (FK), name, file_path, uploaded_by (FK User)

**GuildWishlistItem** — guild (FK), name, description, image, link, estimated_cost, is_fulfilled, created_by (FK User)

**MemberSchedule** — user (OneToOne), notes

**ScheduleBlock** — member_schedule (FK), day_of_week (0-6), start_time, end_time, is_recurring

### core app (enhancement)

**Setting** — key (unique), value (JSONField), type (text|number|boolean|json), updated_by (FK User). Class methods: get(key, default), set(key, value, type, updated_by)

## Permissions & Roles (django-guardian)

Groups: super-admin, guild-manager, class-manager, orientation-manager, accountant, tour-guide, membership-manager, guild-lead, orienter, teacher

Guild-lead and orienter use object-level permissions via django-guardian for per-guild scoping.

## Stripe Integration (dj-stripe)

- Tab billing cycle via management command (monthly)
- Order to Invoice generation
- Subscription management (create/cancel/update)
- Payout report generation
- Webhook handling for payment events

## Admin Interface

All models registered with django-unfold admin classes. Key features:
- Computed fields (tab balance, rental costs, revenue)
- Inline editing (sessions on classes, tools on guilds, etc.)
- Filtered views per role
- CSV export capability
- Custom sidebar navigation organized by app

## Deployment

Target: plos.plaza.codes. Existing Docker + CI/CD pipeline. Add dj-stripe and django-guardian to requirements.
