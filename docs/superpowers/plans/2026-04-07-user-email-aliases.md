# User-Managed Email Aliases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let members add, verify, remove, and change primary email addresses themselves, and log in with any verified address. Fix the confusing admin inline. Document the three-email-store architecture.

**Architecture:** Adopt `allauth.account.models.EmailAddress` as the source of truth for any `Member` that has a linked `User`. `membership.MemberEmail` becomes a pre-signup staging table only. `Member.email` is renamed to `Member._pre_signup_email` and a new `Member.primary_email` property returns the live value. Airtable sync code is updated to reference the renamed field but NOT otherwise changed. A new self-service view (built on allauth's `account_email`) lets members manage their addresses.

**Tech Stack:** Django 5.x, django-allauth (already configured with `ACCOUNT_LOGIN_METHODS = {"email"}` and login-by-code), pytest-describe BDD tests, factory-boy.

**Spec:** `docs/superpowers/specs/2026-04-07-user-email-aliases-design.md`

**Deviation from spec:** Per user instruction "don't actually edit Airtable stuff", `airtable_sync/` files DO get mechanical field-rename updates (required for the code to run) but NO behavioral changes — they still push the stored `_pre_signup_email` value to the Airtable "Email" column.

**Branch:** `feature/user-email-aliases` off `main`.

---

## File Structure

### New files
- `membership/managers.py` — holds `MemberEmailManager` with `migrate_to_user()` classmethod. Keeps the domain logic out of `models.py`.
- `membership/views.py` (new) — `account_email` override view that extends allauth's built-in and re-renders our themed template.
- `templates/account/email.html` — themed version of allauth's email management template.
- `tests/membership/spec/models/member_primary_email_spec.py`
- `tests/membership/spec/models/member_email_staging_spec.py`
- `tests/membership/spec/signals/user_link_email_migration_spec.py`
- `tests/membership/spec/views/account_email_spec.py`
- `tests/membership/spec/integration/login_via_alias_spec.py`
- `tests/membership/spec/admin/member_email_inline_spec.py`

### Modified files
- `membership/models.py` — rename `Member.email` → `Member._pre_signup_email`, add `primary_email` property, update `MemberEmail` (drop `is_primary`, add docstrings).
- `membership/signals.py` — after linking a `User` to a `Member`, call `MemberEmail.objects.migrate_to_user(user)` and ensure a primary `EmailAddress` exists.
- `membership/admin.py` — fix the `MemberEmailInline` (drop `is_primary`), conditionally hide for linked members, add read-only `EmailAddress` display for linked members.
- `membership/forms.py` — update field reference from `Member.email` lookups to `_pre_signup_email`.
- `membership/CLAUDE.md` — add "Email model" section.
- `core/forms.py`, `core/models.py`, `core/views.py` — update email reads to use `member.primary_email` where the live email is needed; update queries to use `_pre_signup_email`.
- `core/urls.py` — register new `account_email` view override.
- `billing/models.py`, `billing/notifications.py`, `billing/admin.py` — use `primary_email` for sending; rename `member__email` search fields to `member___pre_signup_email` or add search against `EmailAddress`.
- `airtable_sync/config.py`, `airtable_sync/management/commands/airtable_backfill.py`, `airtable_sync/management/commands/airtable_pull.py` — mechanical rename of `member.email` → `member._pre_signup_email` and `email__iexact` → `_pre_signup_email__iexact`. **Behavior unchanged.**
- `plfog/adapters.py` — update allauth adapter email lookups to use `_pre_signup_email`.
- `membership/management/commands/set_fog_role.py` — rename query field.
- `plfog/version.py` — bump to `1.4.0` + changelog entry.
- `membership/migrations/00XX_rename_member_email.py` (new)
- `membership/migrations/00XX_drop_memberemail_is_primary.py` (new)
- `membership/migrations/00XX_seed_allauth_emailaddresses.py` (new, data)

---

## Pre-Task: Branch setup

- [ ] **Step 1: Create feature branch**

```bash
git checkout main
git pull
git checkout -b feature/user-email-aliases
```

- [ ] **Step 2: Verify tests pass on main**

Run: `pytest -x -q`
Expected: all pass (establishes baseline).

---

## Task 1: Rename `Member.email` → `Member._pre_signup_email` (schema only)

**Files:**
- Modify: `membership/models.py` (the `email` field on `Member`)
- Create: `membership/migrations/00XX_rename_member_email.py`

Note: this task ONLY renames the field. All call sites still reference `.email` and will break — we fix them in Task 2 in the same commit-ready sequence. Do NOT run the full test suite until Task 2 is done.

- [ ] **Step 1: Rename the field in `membership/models.py`**

Locate the `Member` model's `email` field (around line 136):

```python
email = models.EmailField(blank=True, default="")
```

Replace with:

```python
_pre_signup_email = models.EmailField(
    blank=True,
    default="",
    db_column="email",  # keep existing DB column name to avoid an extra migration
    help_text=(
        "Stored email used ONLY when this Member has no linked User. "
        "Once a User is linked, allauth.account.EmailAddress becomes the source of truth; "
        "read `member.primary_email` instead. See "
        "docs/superpowers/specs/2026-04-07-user-email-aliases-design.md for the full architecture."
    ),
)
```

Using `db_column="email"` means Django still reads/writes the existing `email` column — no DB schema change needed for the rename itself.

- [ ] **Step 2: Create the rename migration**

Run: `python manage.py makemigrations membership --name rename_member_email_to_pre_signup`
Expected: migration generated that renames the field (Django will detect it as a rename because of the `db_column`).

Open the generated file and verify it contains `migrations.RenameField(model_name='member', old_name='email', new_name='_pre_signup_email')`. If Django instead generated an AddField/RemoveField pair, manually edit to use `RenameField`.

- [ ] **Step 3: Do NOT commit yet** — proceed to Task 2.

---

## Task 2: Update all call sites to the renamed field

**Files:**
- Modify: `membership/signals.py:33`
- Modify: `membership/forms.py:34`
- Modify: `membership/management/commands/set_fog_role.py:33`
- Modify: `core/models.py:118`
- Modify: `plfog/adapters.py:138,140`
- Modify: `airtable_sync/config.py:96`
- Modify: `airtable_sync/management/commands/airtable_backfill.py:91,129`
- Modify: `airtable_sync/management/commands/airtable_pull.py:93`
- Modify: `billing/admin.py:89`

This is a mechanical rename of `member.email` → `member._pre_signup_email` and `email__iexact` → `_pre_signup_email__iexact` ONLY at call sites that do ORM queries or field writes. Call sites that want "the live email to display or send to" will be updated in Task 3 to use the new property.

- [ ] **Step 1: `membership/signals.py` line 33**

Old:
```python
member = Member.objects.get(email__iexact=email, user__isnull=True)
```
New:
```python
member = Member.objects.get(_pre_signup_email__iexact=email, user__isnull=True)
```

- [ ] **Step 2: `membership/signals.py` line 70 (the `Member.objects.create(...)` call)**

Old:
```python
Member.objects.create(
    user=instance,
    full_legal_name=name,
    email=instance.email or "",
    membership_plan=plan,
    status=Member.Status.ACTIVE,
)
```
New:
```python
Member.objects.create(
    user=instance,
    full_legal_name=name,
    _pre_signup_email=instance.email or "",
    membership_plan=plan,
    status=Member.Status.ACTIVE,
)
```

- [ ] **Step 3: `membership/forms.py` line 34**

Old:
```python
if Member.objects.filter(email__iexact=email).exclude(status=Member.Status.INVITED).exists():
```
New:
```python
if Member.objects.filter(_pre_signup_email__iexact=email).exclude(status=Member.Status.INVITED).exists():
```

- [ ] **Step 4: `membership/management/commands/set_fog_role.py` line 33**

Old:
```python
member = Member.objects.get(email=email)
```
New:
```python
member = Member.objects.get(_pre_signup_email=email)
```

- [ ] **Step 5: `core/models.py` line 118**

Old:
```python
if Member.objects.filter(email__iexact=email).exclude(status=Member.Status.INVITED).exists():
```
New:
```python
if Member.objects.filter(_pre_signup_email__iexact=email).exclude(status=Member.Status.INVITED).exists():
```

- [ ] **Step 6: `plfog/adapters.py` lines 138 and 140**

Old:
```python
if email and not User.objects.filter(email__iexact=email).exists():
    ...
    if Member.objects.filter(email__iexact=email, user__isnull=True).exists():
```
New:
```python
if email and not User.objects.filter(email__iexact=email).exists():
    ...
    if Member.objects.filter(_pre_signup_email__iexact=email, user__isnull=True).exists():
```

(Leave the `User.objects.filter(email__iexact=...)` alone — that's `User.email`, not `Member.email`.)

- [ ] **Step 7: `airtable_sync/config.py` line 96**

Old:
```python
"Email": member.email,
```
New:
```python
"Email": member._pre_signup_email,
```

Add this comment directly above the line:
```python
# NOTE: We read the stored _pre_signup_email field here, not member.primary_email,
# because Airtable is the source of truth for unlinked members. The primary_email
# property would re-enter allauth for linked members and we don't want to change
# what we push upstream. See specs/2026-04-07-user-email-aliases-design.md.
```

- [ ] **Step 8: `airtable_sync/management/commands/airtable_backfill.py` lines 91 and 129**

Old:
```python
email = member.email.strip().lower()
...
existing_by_email = Member.objects.filter(email__iexact=email).first() if email else None
```
New:
```python
email = member._pre_signup_email.strip().lower()
...
existing_by_email = Member.objects.filter(_pre_signup_email__iexact=email).first() if email else None
```

- [ ] **Step 9: `airtable_sync/management/commands/airtable_pull.py` line 93**

Old:
```python
existing_by_email = model.objects.filter(email__iexact=email).first() if email else None
```

This line is generic (`model` could be any synced model). Only apply the rename if `model` is `Member`. Replace with:

```python
if model is Member:
    existing_by_email = model.objects.filter(_pre_signup_email__iexact=email).first() if email else None
else:
    existing_by_email = model.objects.filter(email__iexact=email).first() if email else None
```

Make sure `Member` is imported at the top of the file.

- [ ] **Step 10: `billing/admin.py` line 89**

Old:
```python
search_fields = ["member__full_legal_name", "member__preferred_name", "member__email"]
```
New:
```python
search_fields = ["member__full_legal_name", "member__preferred_name", "member___pre_signup_email"]
```

(Django supports leading-underscore field names in search_fields; the double underscore is the lookup separator followed by the field name `_pre_signup_email`.)

- [ ] **Step 11: Run migrations and smoke test**

```bash
python manage.py migrate
python manage.py check
pytest -x -q
```

Expected: check passes, tests pass (except possibly for call sites we haven't reached yet — see Task 3 for display/send sites). If a test fails because something reads `member.email` for display purposes, skip it for now; Task 3 will fix.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor(membership): rename Member.email to _pre_signup_email

Keeps the same DB column via db_column='email' so this is a schema no-op.
All ORM queries and writes updated to the new name. Display/send sites
will migrate to the new primary_email property in a follow-up commit.

Part of user-email-aliases work. See
docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 3: Add `Member.primary_email` property and migrate display/send sites

**Files:**
- Modify: `membership/models.py` (add property)
- Modify: `core/forms.py:33,44,49`
- Modify: `billing/models.py:558`
- Modify: `billing/notifications.py:22,40`
- Test: `tests/membership/spec/models/member_primary_email_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/membership/spec/models/member_primary_email_spec.py`:

```python
"""Specs for Member.primary_email property.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md for context
on why this property exists (the three-email-store split).
"""
from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from tests.membership.factories import MemberFactory

User = get_user_model()


def describe_Member_primary_email():
    def context_no_linked_user():
        def it_returns_the_pre_signup_email(db):
            member = MemberFactory(user=None, _pre_signup_email="staged@example.com")
            assert member.primary_email == "staged@example.com"

        def it_returns_empty_string_when_no_stored_email(db):
            member = MemberFactory(user=None, _pre_signup_email="")
            assert member.primary_email == ""

    def context_with_linked_user():
        def it_returns_the_primary_EmailAddress(db):
            user = User.objects.create_user(username="u1", email="primary@example.com")
            EmailAddress.objects.create(user=user, email="primary@example.com", verified=True, primary=True)
            EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)
            member = MemberFactory(user=user, _pre_signup_email="stale@example.com")
            assert member.primary_email == "primary@example.com"

        def it_falls_back_to_user_email_when_no_EmailAddress_rows(db):
            user = User.objects.create_user(username="u2", email="fallback@example.com")
            member = MemberFactory(user=user, _pre_signup_email="stale@example.com")
            assert member.primary_email == "fallback@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/membership/spec/models/member_primary_email_spec.py -v`
Expected: FAIL with `AttributeError: 'Member' object has no attribute 'primary_email'` (or similar).

- [ ] **Step 3: Implement the property on `Member`**

In `membership/models.py`, inside the `Member` class, add:

```python
@property
def primary_email(self) -> str:
    """Return the live primary email for this member.

    THREE-EMAIL-STORE NOTE: This project has three places an email can live
    (see docs/superpowers/specs/2026-04-07-user-email-aliases-design.md):

    1. `self._pre_signup_email` — stored field, used ONLY when self.user is None.
    2. `allauth.account.EmailAddress` — source of truth for linked users.
    3. `User.email` — mirrored from (2) by allauth; used as a fallback only.

    Never read `self._pre_signup_email` directly outside of Airtable sync
    and admin-for-unlinked-members flows. Use this property instead.
    """
    if self.user_id is None:
        return self._pre_signup_email
    # Lazy import to avoid a circular dep between membership and allauth at load time
    from allauth.account.models import EmailAddress
    primary = EmailAddress.objects.filter(user=self.user, primary=True).first()
    if primary is not None:
        return primary.email
    return self.user.email or ""
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/membership/spec/models/member_primary_email_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Update `core/forms.py` send sites**

In `core/forms.py`, the `send_login_email` method currently reads `member.email` at lines 33, 44, 49. Replace:

Old:
```python
if member is None or not member.email:
    return
...
f"Your account email is: {member.email}\n\n"
...
recipient_list=[member.email],
```
New:
```python
if member is None or not member.primary_email:
    return
...
f"Your account email is: {member.primary_email}\n\n"
...
recipient_list=[member.primary_email],
```

- [ ] **Step 6: Update `billing/models.py` line 558**

Old:
```python
email=self.member.email,
```
New:
```python
email=self.member.primary_email,
```

- [ ] **Step 7: Update `billing/notifications.py` lines 22 and 40**

Old:
```python
if not member.email:
    ...
recipient_list=[member.email],
```
New:
```python
if not member.primary_email:
    ...
recipient_list=[member.primary_email],
```

- [ ] **Step 8: Run the full test suite**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(membership): add Member.primary_email property

Introduces the live-email property that reads from allauth's EmailAddress
for linked users and falls back to _pre_signup_email for unlinked members.
All display/send call sites migrated to use it.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 4: Drop `MemberEmail.is_primary` and add staging-table docstring

**Files:**
- Modify: `membership/models.py` (`MemberEmail` class)
- Create: `membership/migrations/00XX_drop_memberemail_is_primary.py`

- [ ] **Step 1: Update the model**

In `membership/models.py`, replace the `MemberEmail` class with:

```python
class MemberEmail(models.Model):
    """Pre-signup staging table for member email addresses.

    THREE-EMAIL-STORE NOTE (see
    docs/superpowers/specs/2026-04-07-user-email-aliases-design.md):

    This table holds known email addresses for Member records that do NOT
    yet have a linked User (typically imported from Airtable). When a User
    is linked to the Member, `MemberEmail.objects.migrate_to_user(user)`
    promotes every row into `allauth.account.EmailAddress` and deletes the
    staging rows. After that, EmailAddress is the source of truth; do NOT
    read MemberEmail for login lookups on linked members.

    The `is_primary` field was removed in version 1.4.0 because Member
    already has a dedicated stored email (_pre_signup_email); a second
    primary flag on a staging row was meaningless and confusing in the
    admin inline.
    """

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="emails",
        help_text="The unlinked member this staged email belongs to.",
    )
    email = models.EmailField(unique=True, help_text="A staged email address for this member.")

    class Meta:
        ordering = ["email"]
        verbose_name = "Staged Email (pre-signup)"
        verbose_name_plural = "Staged Emails (pre-signup)"

    def __str__(self) -> str:
        return f"{self.email} ({self.member.display_name})"
```

- [ ] **Step 2: Create the migration**

Run: `python manage.py makemigrations membership --name drop_memberemail_is_primary`
Expected: migration generated that removes `is_primary`.

- [ ] **Step 3: Run migration**

```bash
python manage.py migrate
```
Expected: success.

- [ ] **Step 4: Run tests**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(membership): drop MemberEmail.is_primary and add staging docs

The is_primary toggle was meaningless — Member already stores a primary
in _pre_signup_email. Class docstring now explains the staging-table
role explicitly for future agents.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 5: `MemberEmail.objects.migrate_to_user()` manager method

**Files:**
- Create: `membership/managers.py`
- Modify: `membership/models.py` (wire up `objects = MemberEmailManager()`)
- Test: `tests/membership/spec/models/member_email_staging_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/membership/spec/models/member_email_staging_spec.py`:

```python
"""Specs for MemberEmail.objects.migrate_to_user().

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""
from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from membership.models import MemberEmail
from tests.membership.factories import MemberFactory

User = get_user_model()


def describe_MemberEmail_migrate_to_user():
    def it_promotes_each_staging_row_to_a_verified_EmailAddress(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        member = MemberFactory(user=user, _pre_signup_email="primary@example.com")
        MemberEmail.objects.create(member=member, email="alias1@example.com")
        MemberEmail.objects.create(member=member, email="alias2@example.com")

        MemberEmail.objects.migrate_to_user(user)

        assert EmailAddress.objects.filter(user=user, email="alias1@example.com", verified=True).exists()
        assert EmailAddress.objects.filter(user=user, email="alias2@example.com", verified=True).exists()

    def it_deletes_the_staging_rows_after_promotion(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        member = MemberFactory(user=user, _pre_signup_email="primary@example.com")
        MemberEmail.objects.create(member=member, email="alias@example.com")

        MemberEmail.objects.migrate_to_user(user)

        assert not MemberEmail.objects.filter(member=member).exists()

    def it_is_idempotent(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        member = MemberFactory(user=user, _pre_signup_email="primary@example.com")
        MemberEmail.objects.create(member=member, email="alias@example.com")

        MemberEmail.objects.migrate_to_user(user)
        MemberEmail.objects.migrate_to_user(user)  # second call is a no-op

        assert EmailAddress.objects.filter(user=user, email="alias@example.com").count() == 1

    def it_ensures_primary_EmailAddress_exists_for_the_user(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        member = MemberFactory(user=user, _pre_signup_email="primary@example.com")

        MemberEmail.objects.migrate_to_user(user)

        primary = EmailAddress.objects.get(user=user, primary=True)
        assert primary.email == "primary@example.com"
        assert primary.verified is True

    def it_does_nothing_when_member_has_no_staging_rows_and_primary_already_exists(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        EmailAddress.objects.create(user=user, email="primary@example.com", verified=True, primary=True)
        MemberFactory(user=user, _pre_signup_email="primary@example.com")

        MemberEmail.objects.migrate_to_user(user)  # should not raise

        assert EmailAddress.objects.filter(user=user).count() == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/membership/spec/models/member_email_staging_spec.py -v`
Expected: FAIL with `AttributeError` on `migrate_to_user`.

- [ ] **Step 3: Create `membership/managers.py`**

```python
"""Custom managers for the membership app.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md for
context on the three-email-store architecture that `MemberEmailManager`
bridges.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models, transaction

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class MemberEmailManager(models.Manager):
    """Manager for MemberEmail with the pre-signup → allauth promotion logic."""

    @transaction.atomic
    def migrate_to_user(self, user: "AbstractUser") -> None:
        """Promote staging emails for this user's Member into allauth.EmailAddress.

        Creates (if missing) a primary, verified EmailAddress for the Member's
        stored _pre_signup_email, then promotes each MemberEmail row for that
        Member into a verified non-primary EmailAddress, then deletes the
        staging rows. Idempotent.

        THREE-EMAIL-STORE NOTE: After this runs, `allauth.account.EmailAddress`
        is authoritative for the user. See the spec for the full design.
        """
        from allauth.account.models import EmailAddress

        from .models import Member, MemberEmail

        try:
            member = user.member
        except Member.DoesNotExist:
            return

        # 1. Ensure a primary EmailAddress exists.
        primary_email_value = (member._pre_signup_email or user.email or "").strip().lower()
        if primary_email_value:
            EmailAddress.objects.get_or_create(
                user=user,
                email__iexact=primary_email_value,
                defaults={"email": primary_email_value, "verified": True, "primary": True},
            )
            # If an EmailAddress existed but wasn't primary, make it primary.
            ea = EmailAddress.objects.get(user=user, email__iexact=primary_email_value)
            if not ea.primary:
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                ea.primary = True
                ea.verified = True
                ea.save(update_fields=["primary", "verified"])

        # 2. Promote each staging row.
        for staging in MemberEmail.objects.filter(member=member):
            EmailAddress.objects.get_or_create(
                user=user,
                email__iexact=staging.email,
                defaults={"email": staging.email, "verified": True, "primary": False},
            )

        # 3. Delete staging rows.
        MemberEmail.objects.filter(member=member).delete()
```

- [ ] **Step 4: Wire the manager up in `membership/models.py`**

In the `MemberEmail` class, add above `class Meta:`:

```python
    from membership.managers import MemberEmailManager  # noqa: E402
    objects = MemberEmailManager()
```

Actually, to avoid an inline import, add this at the top of `membership/models.py` (after the other imports):

```python
from membership.managers import MemberEmailManager
```

And inside `MemberEmail`:

```python
    objects = MemberEmailManager()
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/membership/spec/models/member_email_staging_spec.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full test suite**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(membership): add MemberEmail.objects.migrate_to_user()

Promotes pre-signup staging emails into allauth.account.EmailAddress
when a User is linked to a Member. Idempotent.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 6: Hook the promotion into the user-link signal

**Files:**
- Modify: `membership/signals.py`
- Test: `tests/membership/spec/signals/user_link_email_migration_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/membership/spec/signals/user_link_email_migration_spec.py`:

```python
"""When a User is linked to a Member via signal, staged emails are promoted.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""
from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from membership.models import MemberEmail
from tests.membership.factories import MemberFactory

User = get_user_model()


def describe_user_link_signal():
    def it_promotes_staging_emails_when_user_signs_up_with_alias(db):
        member = MemberFactory(user=None, _pre_signup_email="primary@example.com")
        MemberEmail.objects.create(member=member, email="alias@example.com")

        # Simulate signup: create a User whose email matches the alias.
        # The existing signal links member.user to this User; our new code
        # should then promote both addresses into EmailAddress.
        User.objects.create_user(username="new", email="alias@example.com")

        member.refresh_from_db()
        assert member.user is not None
        assert EmailAddress.objects.filter(user=member.user, email="primary@example.com", verified=True).exists()
        assert EmailAddress.objects.filter(user=member.user, email="alias@example.com", verified=True).exists()
        assert not MemberEmail.objects.filter(member=member).exists()
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/membership/spec/signals/user_link_email_migration_spec.py -v`
Expected: FAIL (the EmailAddress rows won't exist yet).

- [ ] **Step 3: Update `membership/signals.py`**

After the linking logic for both the primary-email and alias branches (i.e., after each `return` statement that fires after a successful link), call the migration. The cleanest place is right before each `return` in both branches:

Replace the current signal body (lines 19-74) with:

```python
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_has_member(sender: type, instance: Any, **kwargs: Any) -> None:
    """Auto-create or link a Member record for any user who doesn't have one.

    After linking, promote any MemberEmail staging rows into allauth EmailAddress
    so the user can log in via any of them. See
    docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
    """
    from .models import Member, MemberEmail, MembershipPlan

    try:
        instance.member
        MemberEmail.objects.migrate_to_user(instance)  # idempotent safety net
        return
    except Member.DoesNotExist:
        pass

    email = getattr(instance, "email", "") or ""
    if email:
        # Check primary email on Member
        try:
            member = Member.objects.get(_pre_signup_email__iexact=email, user__isnull=True)
            member.user = instance
            member.full_legal_name = instance.get_full_name() or member.full_legal_name or instance.username
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["user", "full_legal_name", "status"])
            logger.info("Linked existing Member (primary email) to user %s.", instance.username)
            MemberEmail.objects.migrate_to_user(instance)
            return
        except Member.DoesNotExist:
            pass

        # Check email aliases (staging table)
        try:
            alias = MemberEmail.objects.select_related("member").get(email__iexact=email, member__user__isnull=True)
            member = alias.member
            member.user = instance
            member.full_legal_name = instance.get_full_name() or member.full_legal_name or instance.username
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["user", "full_legal_name", "status"])
            logger.info("Linked existing Member (alias email %s) to user %s.", email, instance.username)
            MemberEmail.objects.migrate_to_user(instance)
            return
        except MemberEmail.DoesNotExist:
            pass

    # No pre-existing member found; create one
    try:
        plan = MembershipPlan.objects.order_by("pk").earliest("pk")
    except MembershipPlan.DoesNotExist:
        logger.warning(
            "Cannot auto-create Member for user %s: no MembershipPlan exists.",
            instance.username,
        )
        return

    name = instance.get_full_name() or instance.username
    Member.objects.create(
        user=instance,
        full_legal_name=name,
        _pre_signup_email=instance.email or "",
        membership_plan=plan,
        status=Member.Status.ACTIVE,
    )
    # Also promote (creates the primary EmailAddress for the fresh member)
    MemberEmail.objects.migrate_to_user(instance)
    logger.info("Auto-created Member for user %s with plan '%s'.", instance.username, plan.name)
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/membership/spec/signals/user_link_email_migration_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(membership): promote staging emails on user link

When the user-link signal fires, MemberEmail rows for that Member are
migrated into allauth.EmailAddress so the user can log in with any of
them.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 7: Data migration — seed `EmailAddress` for existing linked members

**Files:**
- Create: `membership/migrations/00XX_seed_allauth_emailaddresses.py`

This migration runs the promotion for every currently-linked Member, so existing production data is brought up to the new model.

- [ ] **Step 1: Create the migration**

Run: `python manage.py makemigrations membership --empty --name seed_allauth_emailaddresses`

- [ ] **Step 2: Edit the generated file**

Replace its body with:

```python
"""Seed allauth.account.EmailAddress rows from existing Member emails.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.

For every Member that has a linked User, this migration:
1. Creates a primary verified EmailAddress for Member._pre_signup_email
   (if one doesn't already exist).
2. Promotes each MemberEmail staging row into a verified non-primary
   EmailAddress.
3. Deletes the staging rows.

Reverse is lossy: it copies EmailAddress rows back into MemberEmail but
cannot distinguish rows that were originally staged from rows the user
added later. Documented as acceptable for staging rollback only.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Member = apps.get_model("membership", "Member")
    MemberEmail = apps.get_model("membership", "MemberEmail")
    EmailAddress = apps.get_model("account", "EmailAddress")

    for member in Member.objects.filter(user__isnull=False).select_related("user"):
        user = member.user
        primary_value = (member._pre_signup_email or user.email or "").strip().lower()

        if primary_value:
            existing = EmailAddress.objects.filter(user=user, email__iexact=primary_value).first()
            if existing is None:
                # Unset any other primary first
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                EmailAddress.objects.create(
                    user=user, email=primary_value, verified=True, primary=True
                )
            elif not existing.primary:
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                existing.primary = True
                existing.verified = True
                existing.save()

        for staging in MemberEmail.objects.filter(member=member):
            if not EmailAddress.objects.filter(user=user, email__iexact=staging.email).exists():
                EmailAddress.objects.create(
                    user=user, email=staging.email, verified=True, primary=False
                )

        MemberEmail.objects.filter(member=member).delete()


def backwards(apps, schema_editor):
    """Lossy reverse: copy non-primary EmailAddress rows back into MemberEmail."""
    Member = apps.get_model("membership", "Member")
    MemberEmail = apps.get_model("membership", "MemberEmail")
    EmailAddress = apps.get_model("account", "EmailAddress")

    for member in Member.objects.filter(user__isnull=False).select_related("user"):
        for ea in EmailAddress.objects.filter(user=member.user, primary=False):
            MemberEmail.objects.get_or_create(member=member, email=ea.email)


class Migration(migrations.Migration):
    dependencies = [
        ("membership", "00XX_drop_memberemail_is_primary"),  # replace with actual prior migration name
        ("account", "0001_initial"),  # allauth
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

Replace `00XX_drop_memberemail_is_primary` with the actual filename from Task 4.

- [ ] **Step 3: Run migrate on a fresh db**

```bash
python manage.py migrate
```
Expected: success.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "migration(membership): seed allauth EmailAddress from existing data

One-time promotion of Member._pre_signup_email and MemberEmail rows into
allauth.account.EmailAddress for every linked Member. Reverse is lossy.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 8: Themed `account_email` view + URL

**Files:**
- Create: `templates/account/email.html`
- Modify: `core/urls.py` (or wherever allauth urls are included) to ensure `account/email/` is reachable and uses our template.
- Test: `tests/membership/spec/views/account_email_spec.py`

- [ ] **Step 1: Locate the current allauth urls include**

Run: `grep -rn "allauth" core/urls.py plfog/urls.py`
Expected: find where `path("accounts/", include("allauth.urls"))` lives.

- [ ] **Step 2: Write the failing test**

Create `tests/membership/spec/views/account_email_spec.py`:

```python
"""The themed account_email view lets members manage their addresses.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""
from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tests.membership.factories import MemberFactory

User = get_user_model()


def describe_account_email_view():
    def it_requires_login(db):
        client = Client()
        response = client.get("/accounts/email/")
        assert response.status_code in (302, 401)

    def it_lists_the_users_email_addresses(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        EmailAddress.objects.create(user=user, email="primary@example.com", verified=True, primary=True)
        EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)
        MemberFactory(user=user, _pre_signup_email="primary@example.com")

        client = Client()
        client.force_login(user)
        response = client.get("/accounts/email/")

        assert response.status_code == 200
        assert b"primary@example.com" in response.content
        assert b"alias@example.com" in response.content

    def it_renders_our_themed_template(db):
        user = User.objects.create_user(username="u", email="primary@example.com")
        EmailAddress.objects.create(user=user, email="primary@example.com", verified=True, primary=True)
        MemberFactory(user=user, _pre_signup_email="primary@example.com")

        client = Client()
        client.force_login(user)
        response = client.get("/accounts/email/")

        # Our themed template extends the site base — check for a site-specific marker.
        assert b"past-lives" in response.content.lower() or b"plfog" in response.content.lower()
```

- [ ] **Step 3: Run test**

Run: `pytest tests/membership/spec/views/account_email_spec.py -v`
Expected: the first two tests may already pass (allauth ships the view and template); the third fails.

- [ ] **Step 4: Inspect the existing login/signup templates**

Run: `ls templates/account/`
Use the existing templates as a reference for the site base template and block structure. Note the name of the base template (e.g., `{% extends "base.html" %}`) and the block names.

- [ ] **Step 5: Create the themed template**

Create `templates/account/email.html` by copying the structure of one of the existing themed `templates/account/*.html` files and adapting it for email management. It should:

- `{% extends "<same base as other account templates>" %}`
- Include the same site-wide markers that the test asserts on
- Render the allauth context: `{{ form }}`, the list of emails from `emailaddresses` or by iterating `user.emailaddress_set.all()`
- Provide forms for: add email, resend confirmation, remove, make primary

Use allauth's default template (`allauth/templates/account/email.html` in the installed package) as the reference for the form field names and actions. Find it with:

```bash
python -c "import allauth, os; print(os.path.join(os.path.dirname(allauth.__file__), 'templates/account/email.html'))"
```

Read that file and port its form structure into a themed version that extends our base template.

- [ ] **Step 6: Run tests**

Run: `pytest tests/membership/spec/views/account_email_spec.py -v`
Expected: all PASS.

- [ ] **Step 7: Add a link from the member settings/profile page**

Find the member's profile or settings page template (grep for `{% url 'account_logout' %}` or similar):

```bash
grep -rn "account_logout\|profile" templates/ | head
```

Add a link `<a href="{% url 'account_email' %}">Manage email addresses</a>` in the appropriate settings section.

- [ ] **Step 8: Run the full suite**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(account): themed email management page

Uses allauth's built-in account_email view with a themed template so
members can add, verify, remove, and change their primary email
addresses themselves.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 9: Integration test — login via alias

**Files:**
- Create: `tests/membership/spec/integration/login_via_alias_spec.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end: a member can log in via a verified alias email.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""
from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

from tests.membership.factories import MemberFactory

User = get_user_model()


def describe_login_via_alias():
    def it_lets_the_user_log_in_with_a_verified_alias(db, settings):
        settings.ACCOUNT_LOGIN_BY_CODE_ENABLED = True
        user = User.objects.create_user(username="u", email="primary@example.com")
        EmailAddress.objects.create(user=user, email="primary@example.com", verified=True, primary=True)
        EmailAddress.objects.create(user=user, email="alias@example.com", verified=True, primary=False)
        MemberFactory(user=user, _pre_signup_email="primary@example.com")

        client = Client()
        # Request a login code to the alias address
        response = client.post("/accounts/login/code/", {"email": "alias@example.com"})
        assert response.status_code in (200, 302)

        # Allauth sent a code — extract it from the outbox
        assert len(mail.outbox) == 1
        sent = mail.outbox[0]
        assert "alias@example.com" in sent.to
        # Pull the 6-digit code out of the body
        import re
        match = re.search(r"\b(\d{6})\b", sent.body)
        assert match is not None, f"No 6-digit code in email: {sent.body}"
        code = match.group(1)

        # Submit the code
        response = client.post("/accounts/login/code/confirm/", {"code": code}, follow=True)
        assert response.status_code == 200
        # User is now authenticated
        assert response.wsgi_request.user.is_authenticated
        assert response.wsgi_request.user.pk == user.pk
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/membership/spec/integration/login_via_alias_spec.py -v`
Expected: PASS (allauth already supports this — the test verifies the integration).

If it fails because the allauth URL paths differ in this project's version, inspect the URLs with:
```bash
python manage.py show_urls | grep -i "login"
```
And update the POST paths in the test accordingly.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test(membership): end-to-end login via verified alias

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 10: Admin fix — `MemberEmailInline`

**Files:**
- Modify: `membership/admin.py`
- Test: `tests/membership/spec/admin/member_email_inline_spec.py`

- [ ] **Step 1: Write the test**

Create `tests/membership/spec/admin/member_email_inline_spec.py`:

```python
"""Admin inline behavior for the MemberEmail staging table.

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
"""
from __future__ import annotations

from django.contrib import admin

from membership.admin import MemberAdmin, MemberEmailInline
from membership.models import Member


def describe_MemberEmailInline():
    def it_does_not_expose_is_primary(db):
        assert "is_primary" not in list(MemberEmailInline.fields)

    def it_only_shows_email_field(db):
        assert list(MemberEmailInline.fields) == ["email"]


def describe_MemberAdmin_inline_visibility():
    def it_hides_staging_inline_for_linked_members(db, rf):
        from tests.membership.factories import MemberFactory
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="u", email="p@example.com")
        member = MemberFactory(user=user)

        request = rf.get("/")
        request.user = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        model_admin = MemberAdmin(Member, admin.site)

        instances = model_admin.get_inline_instances(request, obj=member)
        assert not any(isinstance(i, MemberEmailInline) for i in instances), (
            "MemberEmailInline should be hidden for linked members"
        )

    def it_shows_staging_inline_for_unlinked_members(db, rf):
        from tests.membership.factories import MemberFactory
        from django.contrib.auth import get_user_model

        User = get_user_model()
        member = MemberFactory(user=None)

        request = rf.get("/")
        request.user = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        model_admin = MemberAdmin(Member, admin.site)

        instances = model_admin.get_inline_instances(request, obj=member)
        assert any(isinstance(i, MemberEmailInline) for i in instances)
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/membership/spec/admin/member_email_inline_spec.py -v`
Expected: some may pass (the `is_primary` check will pass from Task 4), the visibility ones fail.

- [ ] **Step 3: Update `MemberEmailInline` and `MemberAdmin`**

In `membership/admin.py`, replace `MemberEmailInline` with:

```python
class MemberEmailInline(TabularInline):
    """Inline for the pre-signup staging table.

    THREE-EMAIL-STORE NOTE: This inline is ONLY shown for Members without a
    linked User. Once a User is linked, emails live in allauth.account.EmailAddress
    and this inline is hidden to avoid confusion. See
    docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
    """

    model = MemberEmail
    extra = 1
    fields = ["email"]
    verbose_name = "Staged email (pre-signup)"
    verbose_name_plural = "Staged emails (pre-signup)"
```

And add to `MemberAdmin`:

```python
def get_inline_instances(self, request, obj=None):
    """Hide the MemberEmail staging inline once the member has a linked user."""
    instances = super().get_inline_instances(request, obj)
    if obj is not None and obj.user_id is not None:
        instances = [i for i in instances if not isinstance(i, MemberEmailInline)]
    return instances
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/membership/spec/admin/member_email_inline_spec.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix(admin): clean up MemberEmail inline on Member change page

- Drop the meaningless is_primary toggle
- Hide the staging inline entirely for linked members, since their emails
  live in allauth.EmailAddress not MemberEmail
- Add docstrings explaining the three-email-store split

Fixes the jank toggle at /admin/membership/member/<id>/change/

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 11: Update `membership/CLAUDE.md`

**Files:**
- Modify: `membership/CLAUDE.md`

- [ ] **Step 1: Add an "Email model" section**

In `membership/CLAUDE.md`, add this section after the "Models" table:

```markdown
## Email Model — Three Stores (IMPORTANT)

This app has THREE places an email can live. Future agents MUST understand which
is authoritative in which situation. See
`docs/superpowers/specs/2026-04-07-user-email-aliases-design.md` for the full
history and rationale.

| Store | Role |
|---|---|
| `Member._pre_signup_email` | DB field. Source of truth ONLY when `Member.user` is None (unlinked Airtable-imported members). Still written to the `email` column in the DB (`db_column="email"`). |
| `allauth.account.EmailAddress` | Source of truth for any Member that has a linked User. Owns login, verification, primary flag. Allauth's built-in `account_email` view manages these. |
| `User.email` | Mirror kept in sync by allauth. Never read or write directly from app code. |

### Reading "the" email
- Use `member.primary_email` (property). It returns the live value: EmailAddress primary for linked members, `_pre_signup_email` otherwise.
- Exception: `airtable_sync/` intentionally reads `_pre_signup_email` directly because Airtable is the external source of truth for unlinked members.

### Writing
- New self-service UI: themed `templates/account/email.html` using allauth's built-in view.
- Admin: staging inline (`MemberEmailInline`) is ONLY shown for unlinked members; linked members manage emails via allauth, not the staging table.

### Login
- Works automatically for any verified `EmailAddress` row. Allauth does the lookup.
- Aliases imported pre-signup live in `MemberEmail` until the user signs up, then
  `MemberEmail.objects.migrate_to_user(user)` promotes them to `EmailAddress`. This
  happens in the `ensure_user_has_member` signal.
```

- [ ] **Step 2: Commit**

```bash
git add membership/CLAUDE.md
git commit -m "docs(membership): explain the three-email-store split in CLAUDE.md

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 12: Version bump and changelog

**Files:**
- Modify: `plfog/version.py`

- [ ] **Step 1: Bump version and add changelog entry**

Edit `plfog/version.py`: change `VERSION = "1.3.2"` to `VERSION = "1.4.0"`, and prepend this entry to the `CHANGELOG` list:

```python
{
    "version": "1.4.0",
    "date": "2026-04-07",
    "title": "Manage Multiple Email Addresses",
    "changes": [
        "You can now add extra email addresses to your account from your settings page",
        "Log in with any of your verified email addresses — handy if you have a personal and a work email",
        "Change which email is your primary at any time",
        "Cleaner admin: the old 'is primary' toggle on member email aliases has been removed",
    ],
},
```

- [ ] **Step 2: Run the full suite one more time**

Run: `pytest -x -q`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add plfog/version.py
git commit -m "chore: bump to 1.4.0 — user-managed email aliases

See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md"
```

---

## Task 13: Final verification

- [ ] **Step 1: Run linters**

```bash
ruff format .
ruff check --fix .
```
Expected: clean or only auto-fixes.

- [ ] **Step 2: Run full test suite**

```bash
pytest -q
```
Expected: all pass.

- [ ] **Step 3: Fresh-db migration test**

```bash
rm -f db.sqlite3
python manage.py migrate
```
Expected: all migrations apply cleanly on an empty database.

- [ ] **Step 4: Manual smoke test (local dev server)**

```bash
python manage.py runserver
```

In the browser:
1. Create a superuser, log in
2. Visit `/admin/membership/member/<id>/change/` for a linked member — confirm staging inline is hidden
3. Visit `/admin/membership/member/<id>/change/` for an unlinked member — confirm staging inline shows only the `email` field (no `is_primary`)
4. Visit `/accounts/email/` — confirm the themed page loads and shows the current addresses
5. Add a new email, confirm the verification code email lands in the console, enter it, confirm it appears as verified
6. Log out, log back in using the new alias via login-by-code — confirm it works
7. Make the alias the primary, log out, verify `User.email` is now the alias

- [ ] **Step 5: Push the branch**

```bash
git push -u origin feature/user-email-aliases
```

- [ ] **Step 6: Open a PR to main**

Use `gh pr create` with the spec linked in the body.

---

## Self-review notes (addressed inline)

- **Spec coverage:** every requirement in the spec has a corresponding task (data model changes → Tasks 1, 4; login integration → relies on allauth and is verified in Task 9; user-facing UI → Task 8; admin fix → Task 10; migrations → Tasks 1, 4, 7; docs → Task 11; version → Task 12).
- **Deviations from spec:** (1) `Member.email` is renamed at the Python field level but keeps `db_column="email"`, which is cleaner than a schema rename. (2) Airtable files DO get mechanical renames — otherwise the code wouldn't run. No behavior changes in Airtable sync. Both documented at the top of this plan.
- **Type/name consistency:** `_pre_signup_email`, `primary_email`, `migrate_to_user`, `MemberEmailInline` used consistently throughout.
