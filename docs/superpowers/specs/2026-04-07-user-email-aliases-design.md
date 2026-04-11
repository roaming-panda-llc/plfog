# User-Managed Email Aliases with Login

**Date:** 2026-04-07
**Branch:** `feature/user-email-aliases` (from `main`)
**Target version:** `1.4.0`

## Problem

Members cannot currently:
1. Change their email address themselves
2. Add a second email to their account to log in with either one

The `MemberEmail` model exists but is admin-only, does NOT participate in login (allauth reads a different table), and has a meaningless `is_primary` toggle in the admin inline that duplicates `Member.email`.

## Goal

Let members manage multiple email addresses on their own account, log in with any verified address, and change which one is primary — all through a self-service settings page. Fix the confusing admin inline at the same time.

## The Three-Email-Store Problem (READ THIS FIRST)

Three tables currently hold email state. This is unavoidable on this branch because we are not introducing a custom User model. Future agents reading the code MUST understand which is authoritative:

| Table | Role after this change |
|---|---|
| `django.contrib.auth.User.email` | **Mirror only.** Kept in sync by allauth as a reflection of the primary `EmailAddress`. No application code should read or write this directly. |
| `allauth.account.models.EmailAddress` | **Source of truth for any `Member` that has a linked `User`.** Owns login, verification, primary flag. |
| `membership.MemberEmail` | **Pre-signup staging only.** Holds known emails for `Member` records imported from Airtable that do NOT yet have a `User`. When a `User` is linked, rows migrate into `EmailAddress` and `MemberEmail` is no longer consulted for that member. |

**Every model, manager, and view touched by this change MUST have a docstring explaining this split.** The confusion is the whole reason this spec exists.

`Member.email` becomes a `@property` that returns:
1. The primary `EmailAddress.email` if the member has a linked user, else
2. A stored pre-signup email field on `Member` (rename the existing `Member.email` CharField to `Member._pre_signup_email` in a migration — keep it on the model but mark it private with a docstring: "Only used when `user` is None. Once a User is linked, read from EmailAddress instead.").

## Non-Goals

- Custom User model (too invasive)
- Removing `User.email` (can't without a custom user model)
- Changing how Airtable sync writes emails (it still writes to `Member._pre_signup_email`)
- Social login / OAuth email merging

## Design

### Data model changes

1. **`Member`**
   - Rename field `email` → `_pre_signup_email` (DB column renamed too). Add docstring.
   - Add `@property email` returning primary EmailAddress.email or `_pre_signup_email`.
   - Add `@email.setter` that routes writes correctly (for Airtable import paths).
   - Update all reads of `member.email` — they keep working via the property.

2. **`MemberEmail`**
   - Drop `is_primary` field (migration).
   - Add class docstring: "Pre-signup staging table. See spec 2026-04-07-user-email-aliases-design.md. Do NOT use for login lookups — allauth's EmailAddress is the truth for linked users."
   - Add `MemberEmail.objects.migrate_to_user(user)` manager method that moves all rows for `user.member` into `EmailAddress` (first one becomes primary+verified, rest become verified aliases), then deletes the `MemberEmail` rows.

3. **Signal update (`membership/signals.py`)**
   - When a `User` is linked to a `Member` (existing signal), after linking, call `MemberEmail.objects.migrate_to_user(instance)` to promote staging emails into allauth.
   - The linking email itself is already handled by allauth (it creates the `EmailAddress` on signup).

### Login integration

Nothing to build — allauth already authenticates against any verified `EmailAddress` row. Once aliases live in `EmailAddress`, login-by-code works automatically. An integration test will assert this.

### User-facing UI

New URL: `/account/emails/` (login required). We will use allauth's built-in `account_email` view as the starting point and override its template to match our site style (same approach we use for the login pages).

Features (all provided by the built-in view):
- List of email addresses with verified badge
- Add new email (triggers allauth confirmation email — reuses the existing 6-digit code infrastructure via `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` or the current setting)
- Re-send verification
- Remove (blocked on primary)
- Make primary (allauth's `set_as_primary` — also syncs `User.email`)

Link added from the existing member profile/settings area.

### Admin fix

- `MemberEmailInline.fields` becomes `["email"]` only — `is_primary` gone.
- Rename the inline label to "Pre-signup email aliases (unlinked members only)".
- On the `Member` change page, when `member.user` is not None, **hide the `MemberEmailInline` entirely** and add a new read-only inline showing the user's `EmailAddress` rows with a link to the user's allauth email management page. This prevents admins from editing stale staging data.
- Remove the `email` field from the Member admin form's personal-info fieldset when `member.user` is set (read-only display of the property value instead). Leave it editable for unlinked members (it writes to `_pre_signup_email`).

### Migrations

Three migrations, in order:

1. **Schema:** rename `Member.email` → `Member._pre_signup_email`. Drop `MemberEmail.is_primary`.
2. **Data:** for every `Member` with a `user`, create `EmailAddress(user=member.user, email=member._pre_signup_email, verified=True, primary=True)` if one does not already exist; then promote each `MemberEmail` row for that member into a verified non-primary `EmailAddress` and delete the `MemberEmail` row. Reverse: best-effort restore by reading `EmailAddress` rows back into `MemberEmail` and `_pre_signup_email` (documented as lossy — note in the migration).
3. No further schema change; `_pre_signup_email` stays on the model permanently for the unlinked-member case.

### Testing

BDD specs under the conventions in `CLAUDE.md`:

- `membership/spec/models/member_email_property_spec.py` — the property returns EmailAddress value when user linked, `_pre_signup_email` when not, setter routes correctly.
- `membership/spec/models/member_email_staging_spec.py` — `migrate_to_user` promotes rows and deletes staging rows; idempotent; handles no-op when EmailAddress already exists.
- `membership/spec/signals/user_link_spec.py` — signal triggers migration on user link.
- `membership/spec/views/account_email_spec.py` — view is login-gated, add/verify/remove/make-primary round-trips work, unverified email cannot be used to log in, verified alias CAN.
- `membership/spec/admin/member_email_inline_spec.py` — inline hidden for linked members, shown for unlinked; `is_primary` field is gone.
- Integration test: create Member with User, add verified alias via view, log out, trigger login-by-code against the alias address, assert login succeeds.

### Documentation requirements

Every one of the following files MUST carry a docstring block pointing to this spec and explaining the three-store split:

- `membership/models.py` (on `Member.email` property, on `MemberEmail` class)
- `membership/signals.py` (on the user-link signal)
- `membership/managers.py` or wherever `migrate_to_user` lives
- The new account-email view
- `membership/admin.py` `MemberEmailInline` class
- `membership/CLAUDE.md` — add a new "Email model" section explaining the three stores and that `Member.email` is a property.

Future agents should be able to run `grep -r "2026-04-07-user-email-aliases" plfog/ membership/` and find every load-bearing piece.

### Version & changelog

Bump `plfog/version.py` to `1.4.0`. Changelog entry (member-friendly):

> **Manage multiple email addresses**
> - You can now add a second (or third) email address to your account from your settings page
> - Log in with any of your verified addresses
> - Change which one is your primary at any time

## Risks

- **Data migration correctness** — the reverse function is lossy. Acceptable because we only run it on staging if we need to roll back; document this in the migration.
- **Double-write during rollout** — if any code still writes to `Member.email` (now a property), the setter must handle it. Audit all writes before merging.
- **Admin confusion** — mitigated by hiding the staging inline for linked members and by the docstrings.

## Out of scope / follow-ups

- Deleting `MemberEmail` entirely (requires guaranteeing all members have a user — not true today)
- Custom user model
- Merging accounts when an alias collides with another user's primary
