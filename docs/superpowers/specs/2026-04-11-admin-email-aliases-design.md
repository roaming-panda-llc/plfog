# Admin-Managed Email Aliases

**Date:** 2026-04-11
**Branch:** `feature/admin-email-aliases` (currently based on `feature/user-email-aliases` for the 1.4.0 allauth wiring; must be rebased onto `hotfixes/1.4.0` before implementation so the 1.4.1 changelog entry is in place to append bullets to)
**Target version:** `1.4.1` (same release as the contributor-count privacy hotfix — this is a gap-fill that should have shipped with 1.4.0)
**Relationship to other open PRs:**
- PR #66 (`feature/user-email-aliases`) — approved, not merged. Ships 1.4.0 allauth `EmailAddress` wiring that this feature depends on.
- PR #67 (`hotfixes/1.4.0`) — open, stacks on #66, bumps `plfog/version.py` to 1.4.1 and hides contributor counts on member-facing funding views. **This feature must stack on top of #67 and append bullets to the same 1.4.1 changelog entry — no new version bump.**

## Problem

1.4.0 gave members self-service email alias management at `/accounts/email/`. Admins got nothing. After shipping, the very first real use case exposed the gap:

> Add `writersguild@pastlives.space` to Penina's member account so she can sign in as that address.

That email is a shared guild mailbox. Penina cannot receive a verification code there without going through the guild's shared inbox, and nobody wants to coordinate that. The admin just needs to add the alias, mark it verified, and be done.

Currently:

- `membership/admin.py:114–117` hides `MemberEmailInline` the moment a member has a linked `User`, because that inline is pre-signup staging only (see `2026-04-07-user-email-aliases-design.md`).
- `membership/admin.py:342–343` globally unregisters both the stock `User` admin and the allauth `EmailAddress` admin.
- Net result: once a member logs in, there is **zero** admin UI anywhere in the app for touching their email aliases.

## Goal

A dedicated admin page reachable from the member change form that lets staff:

1. **Add** a new email alias to any linked member, auto-marked verified and non-primary.
2. **Remove** any email alias except the last one (removing the last would lock the user out).
3. **Set primary** on any verified alias. Demotes the current primary and syncs `User.email`.
4. **Toggle verified** on any alias. Allowed both directions with a warning on un-verifying the primary.

All four operations must be staff-only, POST-only, and redirect back to the same page with a flash message.

## Non-Goals

- Anything for unlinked members. The existing `MemberEmailInline` (staged emails on the member change page) already covers pre-signup staging; this spec does not touch it.
- Audit logging of who-added-what. Out of scope for v1; reconsider in a follow-up.
- Member-visible "this alias was added by an admin" indicator on `/accounts/email/`. Nice-to-have, not required.
- Bulk add (CSV or similar). YAGNI.
- A custom signal or hook for Airtable sync. Airtable is upstream for `Member` identity and downstream for votes/snapshots only — allauth `EmailAddress` changes stay app-side.
- Any change to `Member._pre_signup_email`. That field is read by `airtable_sync/` for unlinked members and is not relevant to linked-member alias management.

## Architecture

Follows the same pattern as the existing Snapshot Analyzer (`plfog/admin_views.py` + `templates/admin/snapshot_analyzer.html` + routes in `plfog/urls.py`). No inline formsets, no `change_form.html` overrides, no fighting unfold's admin styling.

```
MemberAdmin change page
    │
    │  (readonly "Manage email aliases →" link, rendered only for linked members)
    ▼
GET  /admin/members/<pk>/aliases/
    │
    │  renders list of EmailAddress rows + add form
    ▼
POST /admin/members/<pk>/aliases/add/                              → redirect to GET
POST /admin/members/<pk>/aliases/<email_pk>/remove/                → redirect to GET
POST /admin/members/<pk>/aliases/<email_pk>/set-primary/           → redirect to GET
POST /admin/members/<pk>/aliases/<email_pk>/toggle-verified/       → redirect to GET
```

Every endpoint is decorated `@staff_member_required` and, for POSTs, `@require_POST`.

## Components

### `plfog/admin_views.py`

Five new view functions appended to the existing file. They live alongside the existing snapshot_* views and follow the exact same conventions (thin view, redirect with flash, 404 via `get_object_or_404`).

```python
@staff_member_required
def member_aliases(request: HttpRequest, pk: int) -> HttpResponse:
    """GET — render the aliases page for a linked member."""

@require_POST
@staff_member_required
def member_aliases_add(request: HttpRequest, pk: int) -> HttpResponse:
    """POST — add a new verified, non-primary EmailAddress."""

@require_POST
@staff_member_required
def member_aliases_remove(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    """POST — delete an EmailAddress unless it's the last one."""

@require_POST
@staff_member_required
def member_aliases_set_primary(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    """POST — promote a verified alias to primary via allauth's set_as_primary()."""

@require_POST
@staff_member_required
def member_aliases_toggle_verified(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    """POST — flip the verified flag. Warns when un-verifying a primary."""
```

Each POST view looks up the member (`get_object_or_404(Member, pk=pk)`), then — for the per-email endpoints — looks up the email with `get_object_or_404(EmailAddress, pk=email_pk, user=member.user)`. That compound lookup is the 404 guard against admins fiddling with another user's email by hand-crafting a URL.

For unlinked members, `member_aliases` redirects to the member change page with an info flash: *"This member hasn't signed up yet. Use the Staged Emails section below to manage their pre-signup addresses."*

### Forms

`plfog/forms.py` (new file, or `membership/forms.py` if the existing module is the natural home — the implementation plan can decide):

```python
class AddEmailAliasForm(forms.Form):
    email = forms.EmailField()

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if EmailAddress.objects.filter(user=self.user, email__iexact=email).exists():
            raise ValidationError("This address is already on this member.")
        if EmailAddress.objects.filter(email__iexact=email).exclude(user=self.user).exists():
            raise ValidationError("This address is already tied to a different account.")
        return email
```

Per CLAUDE.md: validation lives in the form, never in the view.

### Template

`templates/admin/membership/member/aliases.html` extends the unfold admin base (`{% extends "admin/base.html" %}` with the same `{% block content %}` style used by `templates/admin/snapshot_analyzer.html`).

Layout:

```
Email aliases for Penina Sharon                         ← Back to member page
─────────────────────────────────────────────────────────────────────────────
Email                           Primary   Verified    Actions
peninasharon@gmail.com          ✓         ✓           [Toggle verified] [Remove]
writersguild@pastlives.space              ✓           [Set primary] [Toggle verified] [Remove]
─────────────────────────────────────────────────────────────────────────────

Add email alias
┌─────────────────────────────────┐
│  email input                     │  [Add]
└─────────────────────────────────┘
```

Each row action is a standalone `<form method="post" action="…">` with `{% csrf_token %}`. Destructive actions (`Remove`) use `onsubmit="return confirm(…)"`. `Set primary` is only rendered when the row is verified AND not already primary. `Toggle verified` label switches between "Mark verified" and "Unmark verified" based on current state.

### Entry point — `MemberAdmin`

A new readonly method field on `MemberAdmin` in `membership/admin.py`, placed alongside the existing `inlines` and following the `FundingSnapshotAdmin.analyzer_link` pattern at line 324:

```python
@admin.display(description="Email aliases")
def email_aliases_link(self, obj: Member) -> str:
    """Render the Manage Aliases link for linked members only."""
    if obj.user_id is None:
        return format_html(
            '<span class="text-muted">No linked user yet — use Staged Emails below.</span>'
        )
    url = reverse("admin_member_aliases", args=[obj.pk])
    return format_html('<a href="{}">Manage email aliases →</a>', url)
```

Added to `readonly_fields` and (via `get_fieldsets` if needed) surfaced on the change form in the same section as the rest of the member identity fields.

### URL routes — `plfog/urls.py`

Five new `path(...)` entries named `admin_member_aliases`, `admin_member_aliases_add`, `admin_member_aliases_remove`, `admin_member_aliases_set_primary`, `admin_member_aliases_toggle_verified`. All mounted under `admin/members/<int:pk>/aliases/`.

## Data flow

| Action | Success steps | Redirect |
|---|---|---|
| **GET page** | Load `Member`, 404 if missing. If `member.user` is None → redirect to member change page with info message. Else load `EmailAddress.objects.filter(user=member.user).order_by("-primary", "email")` and render template with an unbound `AddEmailAliasForm`. | n/a |
| **Add** | Bind `AddEmailAliasForm(request.POST, user=member.user)`. On invalid → re-render page with form errors. On valid → `EmailAddress.objects.create(user=member.user, email=form.cleaned_data["email"], verified=True, primary=False)`. Flash success. | Back to GET. |
| **Remove** | Load `EmailAddress(pk=email_pk, user=member.user)`. Refuse if it's the only `EmailAddress` for this user — flash error. Else `.delete()`. If the deleted row was primary and at least one verified `EmailAddress` remains, explicitly promote the lowest-`pk` verified row via `set_as_primary()`. If no verified rows remain, leave the user with no primary and flash a warning: *"This member has no verified emails left and cannot log in. Add and verify one immediately."* Flash success on the delete itself. | Back to GET. |
| **Set primary** | Load `EmailAddress(pk=email_pk, user=member.user)`. Refuse if `verified=False` — flash error. Else call `email.set_as_primary()` (allauth method; handles demoting the old primary and syncing `User.email` via `user.save()`). Flash success. | Back to GET. |
| **Toggle verified** | Load `EmailAddress(pk=email_pk, user=member.user)`. Flip `verified`, save. If we just un-verified the primary, also flash a warning: *"You've un-verified the primary email. Login will still work until another email is promoted."* | Back to GET. |

## Safety rules

Enforced in the views (fat models would also be reasonable; keep the rules adjacent to the HTTP boundary since they're admin-UX constraints, not domain invariants):

1. **Cannot remove the only email.** `EmailAddress.objects.filter(user=member.user).count() == 1` → refuse with flash error. Rationale: removing it would sever the user's last login path and leave an orphan `User` row.
2. **Warn on removing the last verified email.** If the removal would leave the user with zero verified emails, the view still proceeds but flashes a prominent warning (wording above in the Remove data-flow row). This is a soft guardrail — the admin may be mid-workflow about to add a replacement — but it must be loud enough to notice.
3. **Cannot set primary on unverified.** allauth's `set_as_primary` does not enforce this reliably across versions. Gate in the view.
4. **Duplicate on self** → friendly error via form validation.
5. **Duplicate on another user** → friendly error via form validation. allauth's unique-email handling is the ultimate guard; form-level validation just gives a nicer message.
6. **Unlinked member access** → redirect to the member change page with an info message pointing at `MemberEmailInline`.
7. **Cross-member URL crafting** → `get_object_or_404(EmailAddress, pk=email_pk, user=member.user)` is the only way the per-email views load the row. Hand-crafted URLs that mix another member's `pk` with another user's `email_pk` return 404.

## Error handling

- Uses Django's `messages` framework for all flash messaging (`messages.success`, `messages.error`, `messages.warning`, `messages.info`). No custom exception classes.
- `Member.DoesNotExist` and `EmailAddress.DoesNotExist` handled by `get_object_or_404` → 404 response.
- `IntegrityError` on `EmailAddress.objects.create` (race condition where another admin adds the same email concurrently) → catch, flash error, redirect to GET. This is the only try/except in the new code.

## Airtable interaction

None. `EmailAddress` is an allauth-owned table. `airtable_sync/` only reads `Member._pre_signup_email` for unlinked members and writes votes/snapshots outbound. Nothing in the new admin page touches Airtable-adjacent state. Call this out in docstrings so future agents don't panic.

## Testing

New spec file: `tests/plfog/member_aliases_spec.py`. BDD style with `describe_*` / `context_*` / `it_*`.

### Test matrix

| describe | Specs |
|---|---|
| `describe_member_aliases_page` | `it_requires_staff`, `it_returns_404_for_nonexistent_member`, `it_redirects_to_member_change_page_for_unlinked_member`, `it_lists_all_email_addresses_for_linked_member`, `it_orders_primary_first` |
| `describe_member_aliases_add` | `it_requires_staff`, `it_rejects_get`, `it_creates_verified_non_primary_email`, `it_rejects_duplicate_on_same_user`, `it_rejects_duplicate_on_other_user`, `it_leaves_existing_primary_untouched`, `it_404s_for_nonexistent_member` |
| `describe_member_aliases_remove` | `it_requires_staff`, `it_rejects_get`, `it_deletes_non_primary_email`, `it_refuses_when_only_email`, `it_promotes_lowest_pk_verified_to_primary_when_removing_primary`, `it_warns_when_removing_last_verified_email_but_proceeds`, `it_404s_for_email_belonging_to_another_user` |
| `describe_member_aliases_set_primary` | `it_requires_staff`, `it_rejects_get`, `it_demotes_old_primary_and_promotes_target`, `it_syncs_user_email_to_new_primary`, `it_refuses_unverified_email`, `it_404s_for_email_belonging_to_another_user` |
| `describe_member_aliases_toggle_verified` | `it_requires_staff`, `it_rejects_get`, `it_flips_verified_from_false_to_true`, `it_flips_verified_from_true_to_false`, `it_emits_warning_when_unverifying_primary`, `it_404s_for_email_belonging_to_another_user` |
| `describe_member_aliases_link_on_admin` | `it_renders_link_for_linked_member`, `it_renders_hint_for_unlinked_member` |
| `describe_end_to_end_login_via_admin_added_alias` | Admin adds `writersguild@pastlives.space` to a linked member → member requests login code at that address → member lands authenticated as the original `User`. |

100% branch coverage on the new code. No `@pytest.mark.skip`, no `# pragma: no cover`, no `# pragma: no mutate`.

### Fixtures

- Reuse `MemberFactory` from `tests/membership/factories.py`.
- Add a small helper in `tests/plfog/conftest.py` (or the spec file directly) that creates a `Member` with a linked `User` plus one `EmailAddress` row, since this setup recurs across every spec in the file.
- Use `respx` for any HTTP mocking if allauth's email-sending fires (it shouldn't on `verified=True` creations, but confirm during implementation).

## Permissions

- `@staff_member_required` on all views. Matches the rest of `plfog/admin_views.py`.
- No django-guardian object-level checks. Staff = allowed; non-staff = 302 to admin login. This is consistent with how the Snapshot Analyzer and Invite Member views are gated.

## Rollout / version

- **No new version bump.** `plfog/version.py` is already at `1.4.1` on `hotfixes/1.4.0` (PR #67). This feature appends member-friendly bullets to the existing 1.4.1 changelog entry — it does not create a new entry.
- Bullets to append (plain, member-friendly language):
  - *"Admins can now add email aliases directly from the member page — handy for shared addresses like guild mailboxes where the member can't easily receive a verification code."*
  - *"Admins can also remove aliases, change which one is primary, and toggle whether an alias is verified."*
- Per existing feedback (`feedback_version_changelog.md`): only touch `plfog/version.py` on the final merge-ready commit, not during PR work.

## Open questions

None at spec time. The implementation plan can resolve two small nits:

1. Exact home for `AddEmailAliasForm` — `plfog/forms.py` (new) vs. `membership/forms.py` (existing). Existing precedent says `membership/forms.py` if this is the only form; a new module only if we're adding a cluster of plfog-owned forms.
2. Whether to reorder existing `readonly_fields` on `MemberAdmin` to put `email_aliases_link` in a sensible position, or just append it. Append, unless the field layout clearly suffers.
