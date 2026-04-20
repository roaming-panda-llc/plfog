# Class Management System — Design Spec

**Version:** 1.7.0 (target)
**Date:** 2026-04-20
**Status:** Design approved pending user review

---

## 1. Overview

Replace the broken Drupal/Acuity class booking flow with a native plfog feature. Introduce a new `classes/` Django app that owns class listings, registrations, waivers, discount codes, instructor profiles, and payments. Public-facing pages are passwordless; instructors log in through allauth; admins manage everything from a tabbed `/classes/admin/` page.

The feature replaces the external `classes.pastlives.space` feed in the community calendar when the existing `SiteConfiguration.sync_classes_enabled` toggle is flipped off — during the slow-transfer period, both sources coexist on the calendar.

## 2. Goals

- Anyone can browse classes and register passwordlessly, with Stripe checkout.
- Registrants get a tokenized self-serve link to view/cancel their registrations, plus an email-lookup fallback.
- Instructors (who may or may not be makerspace members) manage their own classes and see their own registrations.
- Admins approve pending classes, manage categories, run discount codes, and configure global waiver text + email templates.
- Three automated emails fire: registration confirmation, instructor new-registration alert, upcoming-class reminder.
- Google Analytics tag on public pages; MailChimp auto-subscribe on registration.

## 3. Out of Scope (v1)

Explicitly deferred to future specs:

- Waitlist promotion UI (status can be stored, no UI to move people)
- Class transfer, QR check-in, self check-in
- Certificate of completion
- Instructor "follow" subscriptions
- Zapier / Google Sheets / any CRM integration beyond MailChimp
- White-label branding (logo per business), multi-business accounts
- Multi-language translations
- Per-class add-ons (books, meals)
- Attendee activity logs, private admin notes per attendee
- Embed widgets, external share buttons
- Event broadcast emails (memos)
- Feedback collection on classes (general feedback button already exists)
- Per-instructor Stripe Connect payouts (all money lands in the main plfog Stripe account)
- Drupal data migration (classes are rebuilt fresh in plfog as they go live)

## 4. Architecture

### 4.1 New app

```
classes/
├── __init__.py
├── apps.py
├── admin.py
├── forms.py
├── managers.py
├── models.py
├── signals.py
├── tokens.py           # token generation/validation for self-serve links
├── emails.py           # email renderers for the 3 notifications
├── stripe_helpers.py   # thin wrappers over billing/ helpers for class checkouts
├── mailchimp.py        # single-purpose MailChimp subscribe helper
├── tasks.py            # reminder scheduler entrypoint
├── urls.py
├── views.py            # public + instructor + admin views
├── spec/
│   ├── conftest.py
│   ├── models/
│   ├── views/
│   └── emails/
├── factories.py
└── migrations/
```

No empty placeholder app is repurposed (`education/` stays out of this — the name "classes" matches the user-facing term).

### 4.2 Roles

Extend `hub/view_as.py` role set with a parallel (non-hierarchical) `instructor` role:

```python
ROLE_MEMBER = "member"
ROLE_INSTRUCTOR = "instructor"   # NEW — parallel, not in ROLE_HIERARCHY
ROLE_GUILD_OFFICER = "guild_officer"
ROLE_ADMIN = "admin"
```

`instructor` is derived from the existence of an `Instructor` record linked to `request.user`. Admin and guild_officer still require a linked Member. A single user can hold any combination (e.g., member + instructor, or instructor-only).

The view-as hierarchy dropdown keeps its current behavior. Instructor sits outside the hierarchy: it's a capability, not a tier.

## 5. Data Model

All models live in `classes/models.py`. All use `TextChoices`, `help_text` on every field, and meaningful `__str__`.

### 5.1 `Category`

```python
class Category(models.Model):
    name          = CharField(max_length=100, unique=True)
    slug          = SlugField(max_length=100, unique=True)
    sort_order    = PositiveIntegerField(default=0)
    hero_image    = ImageField(upload_to="classes/categories/", blank=True)
    created_at    = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Categories"
```

### 5.2 `Instructor`

```python
class Instructor(models.Model):
    user           = OneToOneField(User, on_delete=CASCADE, related_name="instructor",
                                    help_text="Auth identity. Required.")
    display_name   = CharField(max_length=255)
    slug           = SlugField(max_length=255, unique=True)
    bio            = TextField(blank=True)
    photo          = ImageField(upload_to="classes/instructors/", blank=True)
    website        = URLField(blank=True)
    social_handle  = CharField(max_length=255, blank=True)
    is_active      = BooleanField(default=True)
    created_at     = DateTimeField(auto_now_add=True)
    updated_at     = DateTimeField(auto_now=True)
```

No separate `login_token` — instructors authenticate through allauth's existing email-code flow. Admin "Add instructor" action does three things in one transaction: (1) create `User` via `User.objects.create_user(email=..., username=...)`, (2) create a verified `allauth.account.EmailAddress` for that user so email-code login works immediately, (3) create the `Instructor` linked to the user and send a welcome email with the hub URL. Because the existing `core.Invite` model is hard-wired to `Member`, it is NOT reused for instructors.

`Instructor.user` is required. Instructors who also have `Member` records reach them via `instructor.user.member` (OneToOne).

### 5.3 `Class` (model class named `ClassOffering` to avoid `class class` collisions)

```python
class ClassOffering(models.Model):
    class Status(TextChoices):
        DRAFT     = "draft",     "Draft"
        PENDING   = "pending",   "Pending Review"
        PUBLISHED = "published", "Published"
        ARCHIVED  = "archived",  "Archived"

    class SchedulingModel(TextChoices):
        FIXED    = "fixed",    "Fixed sessions"
        FLEXIBLE = "flexible", "Flexible (arrange with instructor)"

    title                  = CharField(max_length=255)
    slug                   = SlugField(max_length=255, unique=True)
    category               = ForeignKey(Category, on_delete=PROTECT)
    instructor             = ForeignKey(Instructor, on_delete=PROTECT, related_name="classes")
    description            = TextField(blank=True)
    prerequisites          = TextField(blank=True)
    materials_included     = TextField(blank=True)
    materials_to_bring     = TextField(blank=True)
    safety_requirements    = TextField(blank=True)
    age_minimum            = PositiveIntegerField(null=True, blank=True)
    age_guardian_note      = TextField(blank=True)
    price_cents            = PositiveIntegerField()
    member_discount_pct    = PositiveIntegerField(default=10)   # 0 = no discount
    capacity               = PositiveIntegerField(default=6)
    scheduling_model       = CharField(..., choices=SchedulingModel.choices, default=FIXED)
    flexible_note          = TextField(blank=True)
    is_private             = BooleanField(default=False)
    private_for_name       = CharField(max_length=255, blank=True)
    recurring_pattern      = CharField(max_length=255, blank=True)
    image                  = ImageField(upload_to="classes/images/", blank=True)
    requires_model_release = BooleanField(default=False)
    status                 = CharField(..., choices=Status.choices, default=DRAFT)
    created_by             = ForeignKey(Instructor, null=True, related_name="+", on_delete=SET_NULL)
    approved_by            = ForeignKey(User, null=True, related_name="+", on_delete=SET_NULL)
    published_at           = DateTimeField(null=True, blank=True)
    created_at             = DateTimeField(auto_now_add=True)
    updated_at             = DateTimeField(auto_now=True)
```

Manager methods:
- `.public()` — status=PUBLISHED, not archived
- `.pending_review()` — status=PENDING
- `.for_instructor(instructor)` — filter to that instructor's classes

Model methods:
- `.submit_for_review()` — draft → pending
- `.approve(admin_user)` — pending → published, sets `approved_by`, `published_at`
- `.archive()` — any → archived
- `.spots_remaining` (property) — capacity minus pending+confirmed registrations
- `.first_upcoming_session_at` (property) — earliest session date in the future
- `.ical_feed()` — returns a `.ics` string for this class

### 5.4 `ClassSession`

```python
class ClassSession(models.Model):
    class_offering   = ForeignKey(ClassOffering, on_delete=CASCADE, related_name="sessions")
    starts_at        = DateTimeField()
    ends_at          = DateTimeField()
    sort_order       = PositiveIntegerField(default=0)

    class Meta:
        ordering = ["starts_at"]
        constraints = [CheckConstraint(check=Q(ends_at__gt=F("starts_at")), name="session_ends_after_starts")]
```

Uses tz-aware `DateTimeField` (not separate date + time + tz strings like the Flask prototype).

### 5.5 `Registration`

```python
class Registration(models.Model):
    class Status(TextChoices):
        PENDING    = "pending",    "Pending payment"
        CONFIRMED  = "confirmed",  "Confirmed"
        WAITLISTED = "waitlisted", "Waitlisted"
        CANCELLED  = "cancelled",  "Cancelled"
        REFUNDED   = "refunded",   "Refunded"

    class_offering       = ForeignKey(ClassOffering, on_delete=PROTECT, related_name="registrations")
    member               = ForeignKey(Member, null=True, blank=True, on_delete=SET_NULL, related_name="class_registrations",
                                       help_text="Auto-linked on save if email matches a verified Member email.")
    first_name           = CharField(max_length=100)
    last_name            = CharField(max_length=100)
    pronouns             = CharField(max_length=50, blank=True)
    email                = EmailField()
    phone                = CharField(max_length=20, blank=True)
    address_line1        = CharField(max_length=255, blank=True)
    address_city         = CharField(max_length=100, blank=True)
    address_state        = CharField(max_length=50, blank=True)
    address_zip          = CharField(max_length=20, blank=True)
    prior_experience     = TextField(blank=True)
    looking_for          = TextField(blank=True)
    discount_code        = ForeignKey(DiscountCode, null=True, blank=True, on_delete=SET_NULL)
    amount_paid_cents    = PositiveIntegerField(default=0)
    status               = CharField(..., choices=Status.choices, default=PENDING)
    stripe_session_id    = CharField(max_length=255, blank=True)
    stripe_payment_id    = CharField(max_length=255, blank=True)
    self_serve_token     = CharField(max_length=64, unique=True, db_index=True,
                                      help_text="Random 64-char token used in the self-serve URL.")
    subscribed_to_mailchimp = BooleanField(default=False)
    registered_at        = DateTimeField(auto_now_add=True)
    confirmed_at         = DateTimeField(null=True, blank=True)
    cancelled_at         = DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [Index(fields=["email"]), Index(fields=["class_offering", "status"])]
```

Model methods:
- `.save()` — on create, populate `self_serve_token` via `secrets.token_urlsafe(48)` and call `link_member_by_email()`.
- `.link_member_by_email()` — if no `member` set, find a Member whose `primary_email` or `MemberEmail` matches `self.email` (verified only); assign.
- `.apply_discount(price_cents)` — classmethod-esque helper returning post-discount amount.
- `.refund(amount_cents)` — refund via Stripe, set status to REFUNDED.
- `.cancel(reason)` — status → CANCELLED, stamp `cancelled_at`. Does NOT auto-refund (admin explicitly refunds).

### 5.6 `Registration` — no separate `Student` model

Unlike the Flask prototype, v1 does not have a `Student` table. The Registration row is the canonical record per event. Member registrations link via `Registration.member`. Cross-registration "student history for this email" is computed via `Registration.objects.filter(email__iexact=email)`. A `Student` model can be introduced later if profile-level data (allergies, emergency contact, long-term notes) is needed.

### 5.7 `Waiver`

```python
class Waiver(models.Model):
    class Kind(TextChoices):
        LIABILITY     = "liability",     "Liability"
        MODEL_RELEASE = "model_release", "Model Release"

    registration    = ForeignKey(Registration, on_delete=CASCADE, related_name="waivers")
    kind            = CharField(..., choices=Kind.choices)
    waiver_text     = TextField(help_text="Full text shown at signing; captured for legal record.")
    signature_text  = CharField(max_length=255)
    ip_address      = GenericIPAddressField(null=True, blank=True)
    signed_at       = DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["registration", "kind"], name="uq_waiver_registration_kind")]
```

### 5.8 `RegistrationReminder`

```python
class RegistrationReminder(models.Model):
    registration = ForeignKey(Registration, on_delete=CASCADE, related_name="reminders")
    session      = ForeignKey(ClassSession, on_delete=CASCADE, related_name="reminders")
    sent_at      = DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["registration", "session"],
                              name="uq_reminder_registration_session"),
        ]
```

Used by the reminder scheduler (§11) to guarantee at-most-once delivery per registration per session.

### 5.9 `DiscountCode`

```python
class DiscountCode(models.Model):
    code                  = CharField(max_length=40, unique=True)  # always stored uppercase
    description           = CharField(max_length=255, blank=True)
    discount_pct          = PositiveIntegerField(null=True, blank=True)
    discount_fixed_cents  = PositiveIntegerField(null=True, blank=True)
    valid_from            = DateField(null=True, blank=True)
    valid_until           = DateField(null=True, blank=True)
    max_uses              = PositiveIntegerField(null=True, blank=True)
    use_count             = PositiveIntegerField(default=0)
    is_active             = BooleanField(default=True)
    created_at            = DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=(Q(discount_pct__isnull=False) | Q(discount_fixed_cents__isnull=False)),
                name="discount_has_value",
            ),
        ]
```

Codes are case-insensitive on input (uppercased before lookup). Stacking rule: **a registration gets either the auto-applied member discount OR an entered discount code, whichever is larger — never both.**

### 5.10 `ClassSettings` (singleton)

```python
class ClassSettings(models.Model):
    enabled_publicly               = BooleanField(default=False,
                                          help_text="When False, /classes/ public routes return 404. "
                                                    "Admin + instructor dashboards stay available.")
    liability_waiver_text          = TextField()
    model_release_waiver_text      = TextField()
    default_member_discount_pct    = PositiveIntegerField(default=10)
    reminder_hours_before          = PositiveIntegerField(default=24)
    instructor_approval_required   = BooleanField(default=True)
    mailchimp_api_key              = CharField(max_length=255, blank=True)
    mailchimp_list_id              = CharField(max_length=255, blank=True)
    google_analytics_measurement_id = CharField(max_length=50, blank=True)
    confirmation_email_footer      = TextField(blank=True)

    class Meta:
        verbose_name = "Class Settings"
        verbose_name_plural = "Class Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            "liability_waiver_text": DEFAULT_LIABILITY_TEXT,
            "model_release_waiver_text": DEFAULT_MODEL_RELEASE_TEXT,
        })
        return obj
```

Default waiver texts (copied from the plm-classes prototype) live in `classes/models.py` as module-level constants and seed the singleton on first load.

## 6. URL Structure

### 6.1 Public (anonymous-allowed)

```
/classes/                              Public portal — filter by category, search, upcoming first
/classes/<slug>/                       Class detail + registration form
/classes/<slug>/register/              POST target (registration submit)
/classes/<slug>/ical/                  Per-class .ics download
/classes/category/<slug>/              Category landing
/classes/instructors/<slug>/           Public instructor profile
/classes/my/<token>/                   Self-serve — list registrations for this token's email
/classes/my/<token>/cancel/<reg_id>/   Self-serve cancel
/classes/lookup/                       Token recovery — enter email, get link emailed
/classes/stripe/return/                Stripe Checkout return URL
/classes/stripe/cancel/                Stripe Checkout cancel URL
/classes/webhooks/stripe/              Stripe webhook for checkout.session.completed + refund events
```

### 6.2 Instructor (login required, role=instructor)

```
/classes/instructor/                   Instructor dashboard — my classes
/classes/instructor/classes/new/       Create class
/classes/instructor/classes/<pk>/edit/ Edit class (if draft|pending)
/classes/instructor/classes/<pk>/submit/ Draft → pending transition
/classes/instructor/registrations/     Registrations for my classes
/classes/instructor/profile/           Edit my instructor profile (bio, photo)
```

### 6.3 Admin (login required, role=admin)

```
/classes/admin/                        Redirects to /classes/admin/classes/
/classes/admin/classes/                Tab: classes list + filters
/classes/admin/classes/<pk>/           Class detail + actions (approve/archive/duplicate)
/classes/admin/categories/             Tab: categories
/classes/admin/instructors/            Tab: instructors + invite form
/classes/admin/registrations/          Tab: all registrations + filters + bulk actions
/classes/admin/registrations/<pk>/     Registration detail with waiver viewer + refund button
/classes/admin/discount-codes/         Tab: discount codes
/classes/admin/settings/               Tab: class settings (waivers, email, MailChimp, GA)
```

Unlike the existing Django-admin-based `/admin/`, this tabbed UI lives entirely in the hub and is rendered with the hub's base template + components.

## 7. Registration Flow

### 7.1 Happy path (paid, spots available)

1. Anonymous user browses `/classes/<slug>/`, clicks "Register."
2. Form shows: name, email, phone, pronouns, optional address, discount code, liability waiver checkbox + signature, model release (if class requires it) + signature, prior experience + looking-for text areas.
3. POST to `/classes/<slug>/register/`. View delegates to `RegistrationForm.clean()` for all validation (per the fat-models rule: forms validate, models act).
4. On valid form, the view:
   - Calls `ClassOffering.create_registration(form.cleaned_data)` which wraps:
     - `select_for_update()` + `transaction.atomic()` on the ClassOffering row
     - Recomputes spots; if full → status=WAITLISTED
     - Creates Registration with `self_serve_token` generated via `secrets.token_urlsafe(48)`
     - Creates Waiver records (one or two)
     - Runs `registration.link_member_by_email()`
     - Applies the better of (member discount, discount code) to compute `amount_paid_cents`
     - Increments `DiscountCode.use_count` if used
   - If WAITLISTED or amount=0 → skip Stripe, send confirmation email, return success page.
   - Otherwise: create a Stripe Checkout Session via `classes.stripe_helpers.create_class_checkout_session(reg)` (see §9) with metadata `{"registration_id": reg.pk, "type": "classes_registration"}`, save `stripe_session_id`, redirect to Stripe.
5. Stripe redirects back to `/classes/stripe/return/?session_id=...` which shows a "Processing your registration..." page and polls the webhook-updated status.
6. `checkout.session.completed` webhook → mark registration CONFIRMED, set `confirmed_at`, send confirmation email (only now), fire MailChimp subscribe.

### 7.2 Self-serve

- Each registration has `self_serve_token`. Confirmation email includes the link `/classes/my/<token>/`.
- That page lists all registrations with this token's email (not just the one this token was issued for — so repeat registrants see all their classes). Cancel button per registration.
- Cancel is instant and free-text-required (for reporting). Does not trigger a refund — admin refunds explicitly.

### 7.3 Token lookup

- `/classes/lookup/` — email input, submit → server finds any registration with that email, sends email containing the token-link to the most recent registration. No password or code needed; the email delivery is the authentication.

### 7.4 Member linking

- On Registration save, if `member` is unset, lookup Members via `MemberEmail.objects.filter(email__iexact=self.email, is_verified=True)` AND via `allauth.account.EmailAddress.objects.filter(email__iexact=self.email, verified=True).values("user__member")`. If exactly one match → `self.member = match`. If ambiguous → leave unset (admin can link manually).
- When linked, the class's `member_discount_pct` applies automatically if no code was entered.

## 8. Waitlist Handling (v1 minimal)

- Status can be set to WAITLISTED when capacity is exceeded on registration.
- No promotion workflow in v1. Admin manually changes status PENDING/CONFIRMED and handles messaging out-of-band.
- The public class detail page shows "Full — registrations will be waitlisted" when at capacity.

## 9. Stripe Integration

### 9.1 Account

All class payments flow to the **main plfog Stripe platform account**. No Connect destination, no Guild routing. This is the same account that handles Tab charges without a guild attached.

### 9.2 Reuse from `billing/`

- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` — reuse.
- Create `classes/stripe_helpers.py` with `create_class_checkout_session(registration)` that builds a Stripe Checkout Session (one-time card payment — anonymous-friendly, no saved payment method required). This is a new helper — `billing/stripe_utils.py` currently exposes `create_payment_intent`, `create_customer`, `create_setup_intent` for saved-card Tab charges but no Checkout Session helper. The classes helper imports and reuses `billing.stripe_utils._get_stripe_client()` and `_platform_secret_key()` for configuration so all Stripe access stays centralized.
- A second webhook endpoint `/classes/webhooks/stripe/` keeps class events separate from Tab events. It filters on `event.type in {"checkout.session.completed", "charge.refunded"}` and metadata `type=classes_registration` (set when creating the session).

### 9.3 Refunds

- Admin registration detail page has a "Refund" action with amount input (default: full amount).
- Calls `stripe.Refund.create(payment_intent=..., amount=...)`, handles `charge.refunded` webhook to flip status to REFUNDED.

## 10. Calendar Integration

No code changes to `SiteConfiguration` — the `sync_classes_enabled` toggle already exists and keeps its current meaning (pull from external Drupal feed).

Local classes integrate as follows:

1. `hub/calendar_service.py` grows a `load_local_class_events()` function that returns `CalendarEvent`-shaped dicts from `ClassSession.objects.filter(class_offering__status=PUBLISHED, starts_at__gte=now)`.
2. The existing merge logic that assembles the calendar page consumes both local and external events.
3. When the admin eventually flips `sync_classes_enabled=False`, only local classes remain.

No calendar data model changes — `CalendarEvent` stays as-is.

## 11. Emails

Three emails, rendered via templated Django emails (same infrastructure as allauth emails and existing plfog notifications).

| Email | Trigger | Template | To |
|---|---|---|---|
| Registration confirmation | Stripe webhook `checkout.session.completed` OR free-class registration | `classes/emails/confirmation.{html,txt}` | Registrant |
| Instructor new-registration | Same webhook / free-class event | `classes/emails/instructor_new_registration.{html,txt}` | Class's instructor |
| Upcoming-class reminder | Scheduled — `reminder_hours_before` before `ClassSession.starts_at` | `classes/emails/reminder.{html,txt}` | Registrant |

The reminder scheduler is a management command `send_class_reminders` triggered every 15 minutes by the existing cron/scheduler used for tab charges (same pattern as `billing.management.commands.run_tab_charges`). It finds `ClassSession`s whose `starts_at - reminder_hours_before` window falls in the last 15 minutes and emails all confirmed registrants for those classes, marking a `reminder_sent_at` field on the Registration–Session join (added in §5 as a small `ReminderLog` table if needed to prevent duplicates).

Confirmation + reminder emails include the self-serve link with the registration's token.

## 12. MailChimp Integration

- Admin adds `mailchimp_api_key` + `mailchimp_list_id` in Classes → Settings.
- On successful registration confirmation, `classes/mailchimp.py::subscribe_registrant(registration)` fires: POST to Mailchimp's Lists API with email + first/last name, status `subscribed`, source `classes`.
- If API key unset → no-op.
- If API call fails → log warning, set `Registration.subscribed_to_mailchimp=False`. Does not block the registration flow.

## 13. Google Analytics

- Admin sets `google_analytics_measurement_id` in Classes → Settings.
- When set, `classes/base_public.html` (the base template for `/classes/*` public pages) renders the GA4 gtag snippet.
- Hub pages (logged-in member area) do NOT get the tag — classes portal only.

## 14. Admin Classes Page (`/classes/admin/`)

Layout: same hub-card + tab-list pattern used by `/settings/` and `/guilds/voting/`. Tabs:

### Classes
Filterable table with columns: title, instructor, category, next session, capacity/registered, status. Row actions: edit, archive, duplicate, approve (pending only). Top-right "Pending Review (N)" badge pulls attention to queue.

### Categories
Table: name, slug, sort order, hero image. Drag-to-reorder via HTMX drag handle. Add/edit uses modal.

### Instructors
Table: photo, display name, linked Member (if any), active toggle, class count. "Add instructor" opens modal with name + email → creates User + Instructor + sends allauth invite.

### Registrations
Filterable table: class (dropdown), status, date range, email search. Click row → detail page with waiver text + signature, Stripe payment info, refund button, cancel button, notes.

### Discount Codes
CRUD table: code, type (% or fixed), value, valid window, uses/max, active toggle.

### Settings
Form with all `ClassSettings` fields. Uses `components/form_field.html` and `components/toggle.html` throughout.

## 15. Instructor Dashboard

Hub sidebar gets a new "Teaching" section visible only when `request.view_as.has(ROLE_INSTRUCTOR)`:

- My Classes (`/classes/instructor/`)
- New Class (`/classes/instructor/classes/new/`)
- My Registrations (`/classes/instructor/registrations/`)
- Profile (`/classes/instructor/profile/`)

Forms are full-page inline forms (more than 3 fields — per FRONTEND.md rules). The class-create form has a sessions sub-form with add/remove session rows.

## 16. Frontend Conventions

- Public pages (`/classes/*` except `admin/` and `instructor/`) use a new `templates/classes/base_public.html` extending `templates/base.html` (the public one, not hub). This page is NOT inside the hub layout.
- Admin and instructor pages extend the existing `templates/hub/base.html`.
- All forms use `components/form_field.html` + `components/toggle.html`.
- Modals use `components/modal.html`.
- HTMX + Alpine per existing plfog conventions — no new JS framework.
- Colors: reuse design tokens from FRONTEND.md.

## 17. Testing

BDD-style pytest-describe specs in `classes/spec/`:

- `models/class_offering_spec.py` — state machine, spots_remaining, managers
- `models/registration_spec.py` — member linking, waiver creation, discount application, token generation, cancel/refund
- `models/waiver_spec.py` — uniqueness per registration+kind
- `models/discount_code_spec.py` — validation, expiry, usage limits
- `models/instructor_spec.py` — role derivation, slug uniqueness
- `views/public_registration_spec.py` — happy path, waitlist, waiver validation failures, token recovery
- `views/self_serve_spec.py` — token access, cancel
- `views/admin_classes_spec.py` — approval flow, category CRUD, settings save
- `views/instructor_dashboard_spec.py` — only sees own classes
- `emails/confirmation_spec.py` — rendering, link inclusion
- `emails/reminder_spec.py` — scheduler finds the right window
- `stripe_helpers_spec.py` — checkout session build, webhook dispatch (using `respx`)
- `mailchimp_spec.py` — subscribe succeeds, fails silently (using `respx`)

Coverage target: 100% on the `classes/` app per project standards.

## 18. Migrations Plan

One migration per logical step:
1. `0001_initial.py` — Category, Instructor, ClassOffering, ClassSession, Waiver, DiscountCode, ClassSettings
2. `0002_registration.py` — Registration (with FK to ClassOffering, Member, DiscountCode)
3. `0003_seed_waiver_defaults.py` — data migration to seed `ClassSettings` with default waiver texts; reverse migration is a no-op that deletes the singleton.

No schema changes in any other app. `hub/view_as.py` adds `ROLE_INSTRUCTOR` in code only.

## 19. Roll-out

1. Ship v1.7.0 with the feature flagged OFF via a new `ClassSettings.enabled_publicly` boolean (default False). When False, `/classes/` routes return 404. Admin tabs + instructor dashboard still work.
2. Admin builds categories, invites first instructors, instructors build their first classes in draft/pending.
3. Admin approves, flips `enabled_publicly=True`.
4. Drupal feed stays ON (`sync_classes_enabled=True`) during the transition. As classes migrate to plfog, admins remove them from Drupal.
5. Eventually flip `sync_classes_enabled=False` → plfog is the only source.

## 20. Versioning

This ships as **v1.7.0**. Changelog entry (member-friendly, per CLAUDE.md):

> **New — Classes on plfog!** Browse classes, register, and pay directly on plfog without needing an account. Instructors can build and manage their own class pages. Admins have a new Classes page with tabs for classes, categories, instructors, registrations, and discount codes. The community calendar shows new classes alongside the existing feed during the transition.

## 21. Known Limitations

- **Image storage on Render.** Render's filesystem is ephemeral — uploaded class/category/instructor images are lost on every deploy. V1 uses `ImageField` + `MEDIA_ROOT` for local and Hetzner QA only. A follow-up spec (S3 or Render persistent disks) must precede public launch on Render; until then, images on Render should be served from external URLs embedded by editors. Pillow is already a dependency (requirements.txt).
- **Single-tenant waiver text.** Global waiver applies to every class. Per-class waiver overrides are not in v1.
- **No refund automation on cancel.** Member-initiated cancel via self-serve does not auto-refund — admin must explicitly refund from the admin registration detail page. This is intentional for v1 (prevents accidental refund floods and lets admin decide policy per case).
- **Instructor approval required.** `ClassSettings.instructor_approval_required` defaults to True; any "trust this instructor" bypass requires admin to toggle it globally. Per-instructor trust flags are out of scope for v1.

## 22. Open Questions

None at design time — all 8 brainstorming questions resolved. Implementation plan will decompose into step-by-step phases.

