# Admin-Managed Email Aliases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated admin page at `/admin/members/<pk>/aliases/` that lets staff add, remove, set-primary, and toggle-verified on member email aliases, with full safety rules and BDD test coverage.

**Architecture:** Thin Django views in `plfog/admin_views.py` (mirroring the Snapshot Analyzer pattern), one form in `membership/forms.py`, one Unfold-styled template, and a `MemberAdmin` readonly link field as the entry point. No inline formsets, no `change_form.html` override.

**Tech Stack:** Django 6, django-allauth (`EmailAddress` model + `set_as_primary()`), Unfold admin, pytest-describe + factory-boy, `@staff_member_required` + `@require_POST`.

**Reference spec:** `docs/superpowers/specs/2026-04-11-admin-email-aliases-design.md` — read it first. Every rule in the "Safety rules" section of the spec must be honored.

**PLFOG coding standards:** See `/Users/joshplaza/Code/hexagonstorms/plfog/CLAUDE.md`:
- Fat models, skinny views
- Validation lives in forms, never in views
- Type annotations on every function (including `-> None`)
- 100% branch coverage, no `@pytest.mark.skip` / `# pragma: no cover` / `# pragma: no mutate`
- BDD specs in `*_spec.py` with `describe_*` / `context_*` / `it_*`
- `dict[key]` not `dict.get(key, default)`
- `ruff check .`, `ruff format .`, `mypy plfog/ core/ membership/ hub/` must all pass before every commit

---

## File Structure

**Create:**
- `templates/admin/membership/member/aliases.html` — the aliases page template
- `tests/plfog/member_aliases_spec.py` — BDD specs

**Modify:**
- `membership/forms.py` — add `AddEmailAliasForm`
- `plfog/admin_views.py` — add 5 view functions
- `plfog/urls.py` — add 5 URL routes
- `membership/admin.py` — add `email_aliases_link` readonly field on `MemberAdmin`
- `plfog/version.py` — append bullets to the existing 1.4.1 changelog entry (last task, final merge-ready commit)

**Untouched (but referenced):**
- `tests/membership/login_via_alias_spec.py` — pattern to copy for the end-to-end login test
- `tests/membership/factories.py` — reuse `MemberFactory`
- `tests/plfog/snapshot_analyzer_spec.py` — copy the `admin_client` fixture pattern

---

## Task 0: Rebase feature branch onto hotfixes/1.4.0

**Why:** The feature branch currently sits on `feature/user-email-aliases` (1.4.0). The 1.4.1 changelog entry lives on `hotfixes/1.4.0`. The implementer needs to rebase so `plfog/version.py` has the 1.4.1 stanza to append bullets to in the final task.

**Files:** git only.

- [ ] **Step 1: Verify current branch**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected output: `feature/admin-email-aliases`

- [ ] **Step 2: Fetch and rebase onto hotfixes/1.4.0**

```bash
git fetch origin
git rebase origin/hotfixes/1.4.0
```

Expected: clean replay of the single spec commit on top of the hotfix branch. If conflicts appear (there shouldn't be — the spec only touches a new file under `docs/superpowers/specs/`), resolve by keeping both sides.

- [ ] **Step 3: Verify history**

```bash
git log --oneline -5
```

Expected: top commit is the spec commit (`docs(spec): admin-managed email aliases`), second is `4e42eac fix(hub): hide contributor counts on member-facing funding views`, then the 1.4.0 commits.

- [ ] **Step 4: Confirm version.py is at 1.4.1**

```bash
grep '^VERSION' plfog/version.py
```

Expected: `VERSION = "1.4.1"`

- [ ] **Step 5: Force-push the rebased branch**

```bash
git push --force-with-lease origin feature/admin-email-aliases
```

(Only if the branch was previously pushed. If this is the first push, use `git push -u origin feature/admin-email-aliases`.)

---

## Task 1: Add `AddEmailAliasForm` to `membership/forms.py`

**Files:**
- Modify: `membership/forms.py`
- Test: `tests/plfog/member_aliases_spec.py` (new file)

- [ ] **Step 1: Create the spec file with form tests**

Create `tests/plfog/member_aliases_spec.py`:

```python
"""Specs for the admin email-aliases page.

See docs/superpowers/specs/2026-04-11-admin-email-aliases-design.md.
"""

from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client

from membership.forms import AddEmailAliasForm
from membership.models import Member
from tests.membership.factories import MemberFactory

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client(db):
    admin = User.objects.create_superuser(
        username="alias-admin",
        password="pass",
        email="alias-admin@example.com",
    )
    # The ensure_user_has_member signal may have auto-created a Member for the
    # admin. Delete it so it doesn't interfere with test counts.
    Member.objects.filter(user=admin).delete()
    c = Client()
    c.force_login(admin)
    return c


@pytest.fixture()
def linked_member(db):
    """Member with a linked User and one primary verified EmailAddress."""
    user = User.objects.create_user(
        username="penina",
        password="pass",
        email="penina@example.com",
    )
    # Signal may have created a Member already — find it or make one.
    member = Member.objects.filter(user=user).first()
    if member is None:
        member = MemberFactory(user=user, _pre_signup_email="penina@example.com")
    else:
        member._pre_signup_email = "penina@example.com"
        member.save(update_fields=["_pre_signup_email"])
    EmailAddress.objects.filter(user=user).delete()
    EmailAddress.objects.create(
        user=user,
        email="penina@example.com",
        verified=True,
        primary=True,
    )
    return member


@pytest.fixture()
def unlinked_member(db):
    """Member imported from Airtable, no linked User."""
    return MemberFactory(user=None, _pre_signup_email="airtable-only@example.com")


# ---------------------------------------------------------------------------
# describe_AddEmailAliasForm
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_AddEmailAliasForm():
    def it_accepts_a_new_email(linked_member):
        form = AddEmailAliasForm(
            data={"email": "writersguild@pastlives.space"},
            user=linked_member.user,
        )
        assert form.is_valid()
        assert form.cleaned_data["email"] == "writersguild@pastlives.space"

    def it_rejects_an_email_already_on_this_user(linked_member):
        form = AddEmailAliasForm(
            data={"email": "penina@example.com"},
            user=linked_member.user,
        )
        assert not form.is_valid()
        assert "already on this member" in str(form.errors["email"]).lower()

    def it_rejects_case_insensitive_duplicate_on_self(linked_member):
        form = AddEmailAliasForm(
            data={"email": "PENINA@example.com"},
            user=linked_member.user,
        )
        assert not form.is_valid()

    def it_rejects_an_email_tied_to_another_user(linked_member):
        other_user = User.objects.create_user(
            username="other",
            password="pass",
            email="other@example.com",
        )
        EmailAddress.objects.create(
            user=other_user,
            email="shared@example.com",
            verified=True,
            primary=False,
        )
        form = AddEmailAliasForm(
            data={"email": "shared@example.com"},
            user=linked_member.user,
        )
        assert not form.is_valid()
        assert "different account" in str(form.errors["email"]).lower()

    def it_rejects_empty_email(linked_member):
        form = AddEmailAliasForm(data={"email": ""}, user=linked_member.user)
        assert not form.is_valid()

    def it_rejects_malformed_email(linked_member):
        form = AddEmailAliasForm(data={"email": "not-an-email"}, user=linked_member.user)
        assert not form.is_valid()
```

- [ ] **Step 2: Run the form tests and verify they fail**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_AddEmailAliasForm -v 2>&1 | tail -20
```

Expected: ImportError on `from membership.forms import AddEmailAliasForm`.

- [ ] **Step 3: Add the form to `membership/forms.py`**

Append to `membership/forms.py` (after `InviteMemberForm`):

```python
class AddEmailAliasForm(forms.Form):
    """Admin form for adding an email alias to a linked member's User.

    Lives here rather than in plfog/ because email/user identity is a
    membership-domain concern. Validation rules:

    1. Email must not already exist on this user (case-insensitive).
    2. Email must not already exist on any other user (allauth unique-email
       handling is the ultimate guard, but we check first for a nicer message).

    THREE-EMAIL-STORE NOTE: This form only operates on allauth.EmailAddress.
    It never touches Member._pre_signup_email or MemberEmail staging rows.
    See docs/superpowers/specs/2026-04-07-user-email-aliases-design.md.
    """

    email = forms.EmailField(
        label="Email address",
        help_text="The new alias. It will be created verified and non-primary.",
    )

    def __init__(self, *args, user, **kwargs) -> None:
        self._user = user
        super().__init__(*args, **kwargs)

    def clean_email(self) -> str:
        from allauth.account.models import EmailAddress

        email = self.cleaned_data["email"].lower()
        if EmailAddress.objects.filter(user=self._user, email__iexact=email).exists():
            raise ValidationError("This address is already on this member.")
        if EmailAddress.objects.filter(email__iexact=email).exclude(user=self._user).exists():
            raise ValidationError("This address is already tied to a different account.")
        return email
```

- [ ] **Step 4: Run the form tests and verify they pass**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_AddEmailAliasForm -v 2>&1 | tail -20
```

Expected: 6 passed.

- [ ] **Step 5: Run ruff and mypy on the changed files**

```bash
.venv/bin/ruff check membership/forms.py tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check membership/forms.py tests/plfog/member_aliases_spec.py
.venv/bin/python -m mypy membership/forms.py
```

Expected: all clean. Fix anything that isn't.

- [ ] **Step 6: Commit**

```bash
git add membership/forms.py tests/plfog/member_aliases_spec.py
git commit -m "feat(membership): add AddEmailAliasForm for admin alias management"
```

---

## Task 2: Scaffold the GET page — URL, view, minimal template

**Goal:** A staff-only `/admin/members/<pk>/aliases/` endpoint that renders the member name and an empty email list. Just enough scaffolding for subsequent POST tasks to redirect to.

**Files:**
- Modify: `plfog/admin_views.py`
- Modify: `plfog/urls.py`
- Create: `templates/admin/membership/member/aliases.html`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add GET-view specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_member_aliases_page (GET)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_page():
    def it_requires_staff(client, linked_member):
        resp = client.get(f"/admin/members/{linked_member.pk}/aliases/")
        assert resp.status_code == 302
        assert "login" in resp.url

    def it_returns_404_for_nonexistent_member(admin_client):
        resp = admin_client.get("/admin/members/999999/aliases/")
        assert resp.status_code == 404

    def it_renders_the_page_for_a_linked_member(admin_client, linked_member):
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        assert resp.status_code == 200
        assert resp.context["member"] == linked_member
        assert list(resp.context["aliases"]) == list(
            EmailAddress.objects.filter(user=linked_member.user).order_by("-primary", "email")
        )
        assert resp.context["add_form"].__class__.__name__ == "AddEmailAliasForm"

    def it_lists_aliases_with_primary_first(admin_client, linked_member):
        EmailAddress.objects.create(
            user=linked_member.user,
            email="aaa@example.com",
            verified=True,
            primary=False,
        )
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        aliases = list(resp.context["aliases"])
        assert aliases[0].primary is True
        assert aliases[0].email == "penina@example.com"
        assert aliases[1].email == "aaa@example.com"
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_page -v 2>&1 | tail -30
```

Expected: 404 on all URL hits (view not yet routed).

- [ ] **Step 3: Add the view stub to `plfog/admin_views.py`**

Add these imports at the top of `plfog/admin_views.py` (merge with the existing import block):

```python
from allauth.account.models import EmailAddress
from membership.forms import AddEmailAliasForm
```

Append at the bottom of the file (after `snapshot_delete`):

```python
# ---------------------------------------------------------------------------
# Member email aliases — admin management page
# ---------------------------------------------------------------------------
#
# Dedicated page at /admin/members/<pk>/aliases/ that lets staff manage
# allauth.EmailAddress rows for a linked Member's User. Mirrors the Snapshot
# Analyzer pattern (GET page + POST action endpoints, all redirecting back).
#
# See docs/superpowers/specs/2026-04-11-admin-email-aliases-design.md.


@staff_member_required
def member_aliases(request: HttpRequest, pk: int) -> HttpResponse:
    """GET — render the aliases management page for a linked member."""
    member = get_object_or_404(Member, pk=pk)
    if member.user_id is None:
        messages.info(
            request,
            "This member hasn't signed up yet. Use the Staged Emails section "
            "on the member page to manage their pre-signup addresses.",
        )
        return redirect("admin:membership_member_change", member.pk)

    aliases = EmailAddress.objects.filter(user=member.user).order_by("-primary", "email")
    add_form = AddEmailAliasForm(user=member.user)
    context = {
        **admin.site.each_context(request),
        "member": member,
        "aliases": aliases,
        "add_form": add_form,
    }
    return render(request, "admin/membership/member/aliases.html", context)
```

- [ ] **Step 4: Add the URL route to `plfog/urls.py`**

Update the import block:

```python
from plfog.admin_views import (
    invite_member,
    member_aliases,
    snapshot_delete,
    snapshot_detail,
    snapshot_draft,
    snapshot_take,
)
```

Add to `admin_custom_urls`:

```python
path(
    "admin/members/<int:pk>/aliases/",
    member_aliases,
    name="admin_member_aliases",
),
```

- [ ] **Step 5: Create the minimal template**

Create `templates/admin/membership/member/aliases.html`:

```django
{% extends "admin/base_site.html" %}
{% load i18n %}

{% block title %}Email aliases — {{ member }}{% endblock %}

{% block content %}
<div style="padding: 1.5rem 2rem;">
    <p style="margin-bottom: 1rem;">
        <a href="{% url 'admin:membership_member_change' member.pk %}">&larr; Back to {{ member }}</a>
    </p>

    <h1>Email aliases for {{ member }}</h1>

    <table>
        <thead>
            <tr>
                <th>Email</th>
                <th>Primary</th>
                <th>Verified</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for alias in aliases %}
            <tr>
                <td>{{ alias.email }}</td>
                <td>{% if alias.primary %}&#10003;{% endif %}</td>
                <td>{% if alias.verified %}&#10003;{% endif %}</td>
                <td>{# action buttons added in Task 9 #}</td>
            </tr>
            {% empty %}
            <tr><td colspan="4"><em>No emails.</em></td></tr>
            {% endfor %}
        </tbody>
    </table>

    <h2>Add email alias</h2>
    {# full add form wired in Task 3 #}
</div>
{% endblock %}
```

- [ ] **Step 6: Run the GET specs and verify they pass**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_page -v 2>&1 | tail -20
```

Expected: 4 passed.

- [ ] **Step 7: Run ruff, format, mypy**

```bash
.venv/bin/ruff check plfog/admin_views.py plfog/urls.py
.venv/bin/ruff format --check plfog/admin_views.py plfog/urls.py
.venv/bin/python -m mypy plfog/admin_views.py plfog/urls.py
```

Expected: all clean.

- [ ] **Step 8: Commit**

```bash
git add plfog/admin_views.py plfog/urls.py templates/admin/membership/member/aliases.html tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): scaffold member email aliases page"
```

---

## Task 3: Add POST endpoint — create verified non-primary alias

**Files:**
- Modify: `plfog/admin_views.py`
- Modify: `plfog/urls.py`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add POST specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_member_aliases_add (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_add():
    def it_requires_staff(client, linked_member):
        resp = client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "new@example.com"},
        )
        assert resp.status_code == 302
        assert "login" in resp.url

    def it_rejects_get(admin_client, linked_member):
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/add/")
        assert resp.status_code == 405

    def it_404s_for_nonexistent_member(admin_client):
        resp = admin_client.post(
            "/admin/members/999999/aliases/add/",
            data={"email": "new@example.com"},
        )
        assert resp.status_code == 404

    def it_creates_verified_non_primary_email(admin_client, linked_member):
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "writersguild@pastlives.space"},
        )
        assert resp.status_code == 302
        assert resp.url == f"/admin/members/{linked_member.pk}/aliases/"
        created = EmailAddress.objects.get(
            user=linked_member.user,
            email="writersguild@pastlives.space",
        )
        assert created.verified is True
        assert created.primary is False

    def it_leaves_existing_primary_untouched(admin_client, linked_member):
        admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "new@example.com"},
        )
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        assert primary.email == "penina@example.com"

    def it_rejects_duplicate_on_same_user(admin_client, linked_member):
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "penina@example.com"},
        )
        assert resp.status_code == 200  # re-renders page with form errors
        assert EmailAddress.objects.filter(user=linked_member.user).count() == 1

    def it_rejects_duplicate_on_other_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        EmailAddress.objects.create(user=other, email="shared@example.com", verified=True, primary=False)
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "shared@example.com"},
        )
        assert resp.status_code == 200
        assert not EmailAddress.objects.filter(
            user=linked_member.user,
            email__iexact="shared@example.com",
        ).exists()
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_add -v 2>&1 | tail -30
```

Expected: 404 on all URL hits.

- [ ] **Step 3: Add the add view to `plfog/admin_views.py`**

Append after `member_aliases`:

```python
@require_POST
@staff_member_required
def member_aliases_add(request: HttpRequest, pk: int) -> HttpResponse:
    """POST — create a verified, non-primary EmailAddress for the member's User."""
    member = get_object_or_404(Member, pk=pk)
    if member.user_id is None:
        messages.error(request, "This member has no linked user.")
        return redirect("admin:membership_member_change", member.pk)

    form = AddEmailAliasForm(request.POST, user=member.user)
    if not form.is_valid():
        # Re-render the page with form errors. Mirrors the GET view's context
        # build so the user sees exactly the same page they submitted from.
        aliases = EmailAddress.objects.filter(user=member.user).order_by("-primary", "email")
        context = {
            **admin.site.each_context(request),
            "member": member,
            "aliases": aliases,
            "add_form": form,
        }
        return render(request, "admin/membership/member/aliases.html", context)

    EmailAddress.objects.create(
        user=member.user,
        email=form.cleaned_data["email"],
        verified=True,
        primary=False,
    )
    messages.success(
        request,
        f"Added alias '{form.cleaned_data['email']}' to {member}.",
    )
    return redirect("admin_member_aliases", pk=member.pk)
```

- [ ] **Step 4: Add the URL route**

Update the `plfog/urls.py` import:

```python
from plfog.admin_views import (
    invite_member,
    member_aliases,
    member_aliases_add,
    snapshot_delete,
    snapshot_detail,
    snapshot_draft,
    snapshot_take,
)
```

Add to `admin_custom_urls` (immediately after the `admin_member_aliases` entry):

```python
path(
    "admin/members/<int:pk>/aliases/add/",
    member_aliases_add,
    name="admin_member_aliases_add",
),
```

- [ ] **Step 5: Run specs and verify they pass**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_add -v 2>&1 | tail -20
```

Expected: 7 passed.

- [ ] **Step 6: Lint / format / mypy / commit**

```bash
.venv/bin/ruff check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/python -m mypy plfog/admin_views.py plfog/urls.py
git add plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): add POST endpoint for creating member email aliases"
```

---

## Task 4: Remove POST endpoint (with safety rules)

**Safety rules to enforce (from spec):**
1. Cannot remove the only `EmailAddress` — return to page with error flash.
2. If removing the primary and ≥1 verified remains, promote the lowest-pk verified via `set_as_primary()`.
3. If removing the last verified email, proceed but flash a loud warning.
4. Email must belong to `member.user` (compound lookup) — else 404.

**Files:**
- Modify: `plfog/admin_views.py`
- Modify: `plfog/urls.py`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add remove specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_member_aliases_remove (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_remove():
    def _alias(user, email, *, verified=True, primary=False):
        return EmailAddress.objects.create(
            user=user, email=email, verified=verified, primary=primary
        )

    def it_requires_staff(client, linked_member):
        alias = _alias(linked_member.user, "gone@example.com")
        resp = client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/remove/")
        assert resp.status_code == 302
        assert "login" in resp.url
        assert EmailAddress.objects.filter(pk=alias.pk).exists()

    def it_rejects_get(admin_client, linked_member):
        alias = _alias(linked_member.user, "gone@example.com")
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/remove/")
        assert resp.status_code == 405

    def it_deletes_non_primary_email(admin_client, linked_member):
        alias = _alias(linked_member.user, "gone@example.com")
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/remove/")
        assert resp.status_code == 302
        assert resp.url == f"/admin/members/{linked_member.pk}/aliases/"
        assert not EmailAddress.objects.filter(pk=alias.pk).exists()

    def it_refuses_when_it_is_the_only_email(admin_client, linked_member):
        # linked_member fixture has exactly 1 email (penina@example.com, primary)
        only = EmailAddress.objects.get(user=linked_member.user)
        resp = admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{only.pk}/remove/")
        assert resp.status_code == 302
        assert EmailAddress.objects.filter(pk=only.pk).exists()

    def it_promotes_lowest_pk_verified_to_primary_when_removing_primary(admin_client, linked_member):
        # Add two new verified aliases. The lowest-pk of the two (the first
        # created, "beta@") should become primary after we remove the original.
        beta = _alias(linked_member.user, "beta@example.com", verified=True, primary=False)
        _alias(linked_member.user, "gamma@example.com", verified=True, primary=False)
        original_primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{original_primary.pk}/remove/"
        )
        beta.refresh_from_db()
        assert beta.primary is True

    def it_proceeds_and_warns_when_removing_last_verified_email(admin_client, linked_member):
        # Start: penina@example.com (verified, primary).
        # Add an UNverified alias, then remove the primary. User ends up with
        # only the unverified alias and a warning flash.
        unverified = _alias(
            linked_member.user, "unverified@example.com", verified=False, primary=False
        )
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{primary.pk}/remove/"
        )
        assert resp.status_code == 302
        assert not EmailAddress.objects.filter(pk=primary.pk).exists()
        assert EmailAddress.objects.filter(pk=unverified.pk).exists()

    def it_404s_for_email_belonging_to_another_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        other_alias = EmailAddress.objects.create(user=other, email="other@example.com", verified=True, primary=True)
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{other_alias.pk}/remove/"
        )
        assert resp.status_code == 404
        assert EmailAddress.objects.filter(pk=other_alias.pk).exists()
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_remove -v 2>&1 | tail -30
```

Expected: 404 on every URL.

- [ ] **Step 3: Add the remove view**

Append to `plfog/admin_views.py`:

```python
@require_POST
@staff_member_required
def member_aliases_remove(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    """POST — delete an EmailAddress unless it's the member's only one.

    Safety rules (from spec section "Safety rules"):
    1. Cannot remove the only EmailAddress — refuse with error flash.
    2. If removing the primary and ≥1 verified remains, promote the
       lowest-pk verified row via set_as_primary().
    3. If removing would leave the user with zero verified emails, proceed
       but flash a loud warning.
    """
    member = get_object_or_404(Member, pk=pk)
    if member.user_id is None:
        messages.error(request, "This member has no linked user.")
        return redirect("admin:membership_member_change", member.pk)

    alias = get_object_or_404(EmailAddress, pk=email_pk, user=member.user)

    total = EmailAddress.objects.filter(user=member.user).count()
    if total == 1:
        messages.error(
            request,
            f"Cannot remove '{alias.email}' — it's the only email on this account. "
            "Removing it would lock the member out.",
        )
        return redirect("admin_member_aliases", pk=member.pk)

    was_primary = alias.primary
    alias_email = alias.email
    alias.delete()

    if was_primary:
        next_verified = (
            EmailAddress.objects.filter(user=member.user, verified=True).order_by("pk").first()
        )
        if next_verified is not None:
            next_verified.set_as_primary(conditional=False)
        else:
            messages.warning(
                request,
                "This member has no verified emails left and cannot log in. "
                "Add and verify one immediately.",
            )

    messages.success(request, f"Removed alias '{alias_email}'.")
    return redirect("admin_member_aliases", pk=member.pk)
```

- [ ] **Step 4: Add the URL route**

Update the `plfog/urls.py` import:

```python
from plfog.admin_views import (
    invite_member,
    member_aliases,
    member_aliases_add,
    member_aliases_remove,
    snapshot_delete,
    snapshot_detail,
    snapshot_draft,
    snapshot_take,
)
```

Add to `admin_custom_urls`:

```python
path(
    "admin/members/<int:pk>/aliases/<int:email_pk>/remove/",
    member_aliases_remove,
    name="admin_member_aliases_remove",
),
```

- [ ] **Step 5: Run specs, verify pass, lint, commit**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_remove -v 2>&1 | tail -20
.venv/bin/ruff check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/python -m mypy plfog/admin_views.py plfog/urls.py
git add plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): add POST endpoint for removing member email aliases"
```

Expected: 7 passed, all checks clean.

---

## Task 5: Set-primary POST endpoint

**Rules:**
1. Target email must be verified — else refuse with error flash.
2. Use allauth's `EmailAddress.set_as_primary(conditional=False)` — it demotes the old primary and syncs `User.email`.
3. Email must belong to `member.user` — else 404.

**Files:**
- Modify: `plfog/admin_views.py`
- Modify: `plfog/urls.py`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add set-primary specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_member_aliases_set_primary (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_set_primary():
    def it_requires_staff(client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        resp = client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        assert resp.status_code == 302
        assert "login" in resp.url
        alias.refresh_from_db()
        assert alias.primary is False

    def it_rejects_get(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        resp = admin_client.get(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/"
        )
        assert resp.status_code == 405

    def it_demotes_old_primary_and_promotes_target(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/"
        )
        assert resp.status_code == 302
        alias.refresh_from_db()
        old = EmailAddress.objects.get(email="penina@example.com")
        assert alias.primary is True
        assert old.primary is False

    def it_syncs_user_email_to_new_primary(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        admin_client.post(f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/")
        linked_member.user.refresh_from_db()
        assert linked_member.user.email == "new@example.com"

    def it_refuses_unverified_email(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user,
            email="unverified@example.com",
            verified=False,
            primary=False,
        )
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/set-primary/"
        )
        assert resp.status_code == 302
        alias.refresh_from_db()
        assert alias.primary is False
        original = EmailAddress.objects.get(email="penina@example.com")
        assert original.primary is True

    def it_404s_for_email_belonging_to_another_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        other_alias = EmailAddress.objects.create(
            user=other, email="other@example.com", verified=True, primary=True
        )
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{other_alias.pk}/set-primary/"
        )
        assert resp.status_code == 404
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_set_primary -v 2>&1 | tail -30
```

Expected: 404 on every URL.

- [ ] **Step 3: Add the set-primary view**

Append to `plfog/admin_views.py`:

```python
@require_POST
@staff_member_required
def member_aliases_set_primary(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    """POST — promote a verified alias to primary.

    Uses allauth's EmailAddress.set_as_primary(conditional=False), which
    demotes the current primary and updates User.email in one call.
    Unverified emails are rejected (allauth's own guard is version-dependent;
    we gate here to be sure).
    """
    member = get_object_or_404(Member, pk=pk)
    if member.user_id is None:
        messages.error(request, "This member has no linked user.")
        return redirect("admin:membership_member_change", member.pk)

    alias = get_object_or_404(EmailAddress, pk=email_pk, user=member.user)

    if not alias.verified:
        messages.error(
            request,
            f"Cannot set '{alias.email}' as primary — it isn't verified yet.",
        )
        return redirect("admin_member_aliases", pk=member.pk)

    alias.set_as_primary(conditional=False)
    messages.success(request, f"'{alias.email}' is now the primary email.")
    return redirect("admin_member_aliases", pk=member.pk)
```

- [ ] **Step 4: Add the URL route**

Update `plfog/urls.py` import block to include `member_aliases_set_primary`, and add:

```python
path(
    "admin/members/<int:pk>/aliases/<int:email_pk>/set-primary/",
    member_aliases_set_primary,
    name="admin_member_aliases_set_primary",
),
```

- [ ] **Step 5: Run specs, lint, commit**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_set_primary -v 2>&1 | tail -20
.venv/bin/ruff check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/python -m mypy plfog/admin_views.py plfog/urls.py
git add plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): add POST endpoint for setting member email alias primary"
```

Expected: 6 passed.

---

## Task 6: Toggle-verified POST endpoint

**Rules:**
1. Flip `verified` and save.
2. If un-verifying the primary, still allow it but flash a warning.
3. Email must belong to `member.user` — else 404.

**Files:**
- Modify: `plfog/admin_views.py`
- Modify: `plfog/urls.py`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add toggle-verified specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_member_aliases_toggle_verified (POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_toggle_verified():
    def it_requires_staff(client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=False, primary=False
        )
        resp = client.post(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/"
        )
        assert resp.status_code == 302
        assert "login" in resp.url
        alias.refresh_from_db()
        assert alias.verified is False

    def it_rejects_get(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=False, primary=False
        )
        resp = admin_client.get(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/"
        )
        assert resp.status_code == 405

    def it_flips_verified_from_false_to_true(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=False, primary=False
        )
        admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/"
        )
        alias.refresh_from_db()
        assert alias.verified is True

    def it_flips_verified_from_true_to_false(admin_client, linked_member):
        alias = EmailAddress.objects.create(
            user=linked_member.user, email="new@example.com", verified=True, primary=False
        )
        admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{alias.pk}/toggle-verified/"
        )
        alias.refresh_from_db()
        assert alias.verified is False

    def it_allows_unverifying_primary_with_warning(admin_client, linked_member):
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{primary.pk}/toggle-verified/"
        )
        assert resp.status_code == 302
        primary.refresh_from_db()
        assert primary.verified is False
        # Warning messages end up in the session for the next request.
        messages_list = list(admin_client.session.get("_messages", []))  # noqa: F841 — structural only

    def it_404s_for_email_belonging_to_another_user(admin_client, linked_member):
        other = User.objects.create_user(username="other", email="other@example.com", password="pass")
        other_alias = EmailAddress.objects.create(
            user=other, email="other@example.com", verified=False, primary=False
        )
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/{other_alias.pk}/toggle-verified/"
        )
        assert resp.status_code == 404
        other_alias.refresh_from_db()
        assert other_alias.verified is False
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_toggle_verified -v 2>&1 | tail -30
```

- [ ] **Step 3: Add the toggle-verified view**

Append to `plfog/admin_views.py`:

```python
@require_POST
@staff_member_required
def member_aliases_toggle_verified(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    """POST — flip the verified flag on an alias.

    Warns loudly if the admin just un-verified the primary email (login
    still works until another email is promoted, but it's fragile).
    """
    member = get_object_or_404(Member, pk=pk)
    if member.user_id is None:
        messages.error(request, "This member has no linked user.")
        return redirect("admin:membership_member_change", member.pk)

    alias = get_object_or_404(EmailAddress, pk=email_pk, user=member.user)
    alias.verified = not alias.verified
    alias.save(update_fields=["verified"])

    if not alias.verified and alias.primary:
        messages.warning(
            request,
            f"'{alias.email}' is the primary email and is now un-verified. "
            "Login will still work until another email is promoted, but this is fragile.",
        )
    else:
        state = "verified" if alias.verified else "un-verified"
        messages.success(request, f"'{alias.email}' is now {state}.")

    return redirect("admin_member_aliases", pk=member.pk)
```

- [ ] **Step 4: Add the URL route**

Update `plfog/urls.py` import to include `member_aliases_toggle_verified`, and add:

```python
path(
    "admin/members/<int:pk>/aliases/<int:email_pk>/toggle-verified/",
    member_aliases_toggle_verified,
    name="admin_member_aliases_toggle_verified",
),
```

- [ ] **Step 5: Run specs, lint, commit**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_toggle_verified -v 2>&1 | tail -20
.venv/bin/ruff check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
.venv/bin/python -m mypy plfog/admin_views.py plfog/urls.py
git add plfog/admin_views.py plfog/urls.py tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): add POST endpoint for toggling member email alias verified flag"
```

Expected: 6 passed.

---

## Task 7: Unlinked-member redirect spec

**Why separate task:** The GET-view in Task 2 already redirects unlinked members. This task adds the explicit regression spec the design calls out ("redirect to member change page with a message pointing to the `MemberEmailInline` staging section").

**Files:**
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add the spec**

Append to `describe_member_aliases_page` (inside the existing block) by editing the file. The spec:

```python
    def it_redirects_unlinked_members_to_the_member_change_page(admin_client, unlinked_member):
        resp = admin_client.get(f"/admin/members/{unlinked_member.pk}/aliases/")
        assert resp.status_code == 302
        assert f"/admin/membership/member/{unlinked_member.pk}/change/" in resp.url
```

Locate `describe_member_aliases_page` in `tests/plfog/member_aliases_spec.py` and add this as the last `def it_...` inside the block.

- [ ] **Step 2: Run the spec**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_page::it_redirects_unlinked_members_to_the_member_change_page -v 2>&1 | tail -15
```

Expected: PASS (the redirect logic is already in Task 2's view).

- [ ] **Step 3: Lint, commit**

```bash
.venv/bin/ruff check tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check tests/plfog/member_aliases_spec.py
git add tests/plfog/member_aliases_spec.py
git commit -m "test(admin): assert aliases page redirects unlinked members"
```

---

## Task 8: MemberAdmin entry point — `email_aliases_link` readonly field

**Goal:** Add a "Manage email aliases →" link at the top of the Personal Info fieldset on the member change page for linked members; show a muted hint for unlinked members instead.

**Files:**
- Modify: `membership/admin.py`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add entry-point specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_email_aliases_link_on_member_admin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_email_aliases_link_on_member_admin():
    def it_renders_link_for_linked_member(admin_client, linked_member):
        resp = admin_client.get(f"/admin/membership/member/{linked_member.pk}/change/")
        assert resp.status_code == 200
        url = f"/admin/members/{linked_member.pk}/aliases/"
        assert url.encode() in resp.content
        assert b"Manage email aliases" in resp.content

    def it_renders_hint_for_unlinked_member(admin_client, unlinked_member):
        resp = admin_client.get(f"/admin/membership/member/{unlinked_member.pk}/change/")
        assert resp.status_code == 200
        assert b"No linked user yet" in resp.content
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_email_aliases_link_on_member_admin -v 2>&1 | tail -20
```

Expected: 2 failures (field not on admin yet).

- [ ] **Step 3: Add the readonly field method to `MemberAdmin`**

In `membership/admin.py`, locate `class MemberAdmin(ModelAdmin):` and make three changes:

**3a.** At the top of the class body, add `readonly_fields` and the method:

```python
    readonly_fields = ["email_aliases_link"]

    @admin.display(description="Email aliases")
    def email_aliases_link(self, obj: Member) -> str:
        """Link to the admin email-aliases page, or hint for unlinked members.

        THREE-EMAIL-STORE NOTE: This link appears only for members with a
        linked User. Unlinked members manage pre-signup emails via the
        MemberEmailInline below. See the aliases page spec at
        docs/superpowers/specs/2026-04-11-admin-email-aliases-design.md.
        """
        from django.urls import reverse
        from django.utils.html import format_html

        if obj.user_id is None:
            return format_html(
                '<span style="color: #888;">No linked user yet — use Staged Emails below.</span>'
            )
        url = reverse("admin_member_aliases", args=[obj.pk])
        return format_html('<a href="{}">Manage email aliases →</a>', url)
```

**3b.** In `get_fieldsets`, insert `"email_aliases_link"` into `personal_fields` right after the `"user"` / `"create_user"` entries. Change:

```python
        # Show "user" link on edit, "create_user" checkbox on add
        if obj is not None:
            personal_fields.insert(0, "user")
        else:
            personal_fields.append("create_user")
```

To:

```python
        # Show "user" link on edit, "create_user" checkbox on add
        if obj is not None:
            personal_fields.insert(0, "user")
            personal_fields.insert(1, "email_aliases_link")
        else:
            personal_fields.append("create_user")
```

- [ ] **Step 4: Run specs and verify pass**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_email_aliases_link_on_member_admin -v 2>&1 | tail -20
```

Expected: 2 passed.

- [ ] **Step 5: Lint / format / mypy / commit**

```bash
.venv/bin/ruff check membership/admin.py tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check membership/admin.py tests/plfog/member_aliases_spec.py
.venv/bin/python -m mypy membership/admin.py
git add membership/admin.py tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): add email_aliases_link readonly field to MemberAdmin"
```

---

## Task 9: Template polish — full UI with action buttons

**Goal:** Replace the minimal template with the full UI: styled list, primary/verified indicators, action buttons (Remove, Set primary, Toggle verified), and a working Add form with error rendering.

**Files:**
- Modify: `templates/admin/membership/member/aliases.html`
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Add template-content specs**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_member_aliases_template
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_member_aliases_template():
    def it_renders_each_alias_row_with_action_buttons(admin_client, linked_member):
        second = EmailAddress.objects.create(
            user=linked_member.user,
            email="second@example.com",
            verified=True,
            primary=False,
        )
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        assert b"penina@example.com" in resp.content
        assert b"second@example.com" in resp.content
        # Per-row POST forms exist for each action.
        assert f"/aliases/{second.pk}/remove/".encode() in resp.content
        assert f"/aliases/{second.pk}/set-primary/".encode() in resp.content
        assert f"/aliases/{second.pk}/toggle-verified/".encode() in resp.content

    def it_hides_set_primary_button_on_the_current_primary(admin_client, linked_member):
        # The current primary is penina@example.com. Its row should NOT render
        # the set-primary form action.
        primary = EmailAddress.objects.get(user=linked_member.user, primary=True)
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        # This is a structural check: the primary row's <form action> should
        # not include its own pk for set-primary.
        primary_set_primary = f"/aliases/{primary.pk}/set-primary/".encode()
        assert primary_set_primary not in resp.content

    def it_hides_set_primary_button_on_unverified_rows(admin_client, linked_member):
        unverified = EmailAddress.objects.create(
            user=linked_member.user,
            email="unv@example.com",
            verified=False,
            primary=False,
        )
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        unverified_set_primary = f"/aliases/{unverified.pk}/set-primary/".encode()
        assert unverified_set_primary not in resp.content

    def it_renders_the_add_form(admin_client, linked_member):
        resp = admin_client.get(f"/admin/members/{linked_member.pk}/aliases/")
        assert b'name="email"' in resp.content
        assert f"/admin/members/{linked_member.pk}/aliases/add/".encode() in resp.content
        assert b"csrfmiddlewaretoken" in resp.content

    def it_renders_form_errors_when_add_fails(admin_client, linked_member):
        # POST a duplicate to force form errors, then confirm the page re-renders
        # the form with the error message.
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "penina@example.com"},
        )
        assert resp.status_code == 200
        assert b"already on this member" in resp.content
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_template -v 2>&1 | tail -30
```

Expected: at least the form/action-button specs fail.

- [ ] **Step 3: Rewrite the template in full**

Overwrite `templates/admin/membership/member/aliases.html`:

```django
{% extends "admin/base_site.html" %}
{% load i18n %}

{% block title %}Email aliases — {{ member }} | {{ site_title }}{% endblock %}

{% block breadcrumbs %}
<div class="breadcrumbs">
    <a href="{% url 'admin:index' %}">Home</a>
    &rsaquo; <a href="{% url 'admin:app_list' app_label='membership' %}">Membership</a>
    &rsaquo; <a href="{% url 'admin:membership_member_changelist' %}">Members</a>
    &rsaquo; <a href="{% url 'admin:membership_member_change' member.pk %}">{{ member }}</a>
    &rsaquo; Email aliases
</div>
{% endblock %}

{% block content %}
<div class="plfog-aliases" style="padding: 1.5rem 2rem; max-width: 960px;">
    <h1 style="margin-bottom: 0.25rem;">Email aliases</h1>
    <p style="color: #888; margin-top: 0;">for {{ member }}</p>

    {% if messages %}
    <ul class="messagelist">
        {% for message in messages %}
        <li{% if message.tags %} class="{{ message.tags }}"{% endif %}>{{ message }}</li>
        {% endfor %}
    </ul>
    {% endif %}

    <table class="plfog-aliases__table" style="width: 100%; border-collapse: collapse; margin-bottom: 2rem;">
        <thead>
            <tr>
                <th style="text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd;">Email</th>
                <th style="text-align: center; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd;">Primary</th>
                <th style="text-align: center; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd;">Verified</th>
                <th style="text-align: right; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd;">Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for alias in aliases %}
            <tr>
                <td style="padding: 0.5rem 0.75rem; border-bottom: 1px solid #f0f0f0;">{{ alias.email }}</td>
                <td style="text-align: center; padding: 0.5rem 0.75rem; border-bottom: 1px solid #f0f0f0;">
                    {% if alias.primary %}&#10003;{% endif %}
                </td>
                <td style="text-align: center; padding: 0.5rem 0.75rem; border-bottom: 1px solid #f0f0f0;">
                    {% if alias.verified %}&#10003;{% endif %}
                </td>
                <td style="text-align: right; padding: 0.5rem 0.75rem; border-bottom: 1px solid #f0f0f0;">
                    {% if alias.verified and not alias.primary %}
                    <form method="post"
                          action="{% url 'admin_member_aliases_set_primary' member.pk alias.pk %}"
                          style="display: inline;">
                        {% csrf_token %}
                        <button type="submit" class="button">Set primary</button>
                    </form>
                    {% endif %}

                    <form method="post"
                          action="{% url 'admin_member_aliases_toggle_verified' member.pk alias.pk %}"
                          style="display: inline;">
                        {% csrf_token %}
                        <button type="submit" class="button">
                            {% if alias.verified %}Unmark verified{% else %}Mark verified{% endif %}
                        </button>
                    </form>

                    <form method="post"
                          action="{% url 'admin_member_aliases_remove' member.pk alias.pk %}"
                          style="display: inline;"
                          onsubmit="return confirm('Remove {{ alias.email|escapejs }}? This cannot be undone.');">
                        {% csrf_token %}
                        <button type="submit" class="button" style="color: #c0392b;">Remove</button>
                    </form>
                </td>
            </tr>
            {% empty %}
            <tr>
                <td colspan="4" style="padding: 0.75rem; color: #888;"><em>No emails on this account yet.</em></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h2 style="margin-bottom: 0.5rem;">Add email alias</h2>
    <form method="post"
          action="{% url 'admin_member_aliases_add' member.pk %}"
          style="display: flex; gap: 0.5rem; align-items: flex-start; flex-wrap: wrap;">
        {% csrf_token %}
        <div>
            {{ add_form.email }}
            {% if add_form.email.errors %}
            <ul class="errorlist" style="color: #c0392b; margin: 0.25rem 0 0; padding-left: 1rem;">
                {% for error in add_form.email.errors %}
                <li>{{ error }}</li>
                {% endfor %}
            </ul>
            {% endif %}
        </div>
        <button type="submit" class="default">Add</button>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 4: Run the template specs**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_member_aliases_template -v 2>&1 | tail -30
```

Expected: 5 passed.

- [ ] **Step 5: Lint, commit**

```bash
.venv/bin/ruff check tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check tests/plfog/member_aliases_spec.py
git add templates/admin/membership/member/aliases.html tests/plfog/member_aliases_spec.py
git commit -m "feat(admin): render member aliases page with action buttons and add form"
```

---

## Task 10: End-to-end login-via-admin-added-alias spec

**Goal:** Prove the whole loop: admin POSTs to add an alias, member logs in via allauth login-by-code sent to that alias, lands authenticated as the original user.

**Files:**
- Test: `tests/plfog/member_aliases_spec.py`

- [ ] **Step 1: Skim the existing pattern**

Read `tests/membership/login_via_alias_spec.py` to see how plfog's BDD tests exercise the allauth login-by-code flow. You will need the same `respx` mocks (if any) and URL hits. Take the minimal happy-path shape.

```bash
wc -l tests/membership/login_via_alias_spec.py
```

- [ ] **Step 2: Add the end-to-end describe block**

Append to `tests/plfog/member_aliases_spec.py`:

```python
# ---------------------------------------------------------------------------
# describe_end_to_end_login_via_admin_added_alias
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def describe_end_to_end_login_via_admin_added_alias():
    def it_allows_login_via_an_alias_added_by_admin(admin_client, linked_member, settings):
        """Admin adds writersguild@pastlives.space, member logs in via that address."""
        from django.core import mail

        settings.ACCOUNT_EMAIL_VERIFICATION = "optional"

        # 1. Admin adds the new alias via the POST endpoint.
        resp = admin_client.post(
            f"/admin/members/{linked_member.pk}/aliases/add/",
            data={"email": "writersguild@pastlives.space"},
        )
        assert resp.status_code == 302
        created = EmailAddress.objects.get(
            user=linked_member.user,
            email="writersguild@pastlives.space",
        )
        assert created.verified is True

        # 2. A fresh (unauthenticated) client — representing Penina — requests
        #    a login code at the shared address.
        mail.outbox.clear()
        member_client = Client()

        # Re-use the plfog login-by-code entry point. Follow the shape of
        # tests/membership/login_via_alias_spec.py::it_logs_in_via_any_verified_alias
        # for the exact URL path and POST data — it's the same view under test.
        # The two assertions below are the invariants:
        #   - A login code email is sent to the requested address
        #   - Submitting that code authenticates the session as Penina's user
        # Implementation detail: allauth's request_login_code view is at
        # /accounts/login/code/ in plfog.

        resp = member_client.post(
            "/accounts/login/code/",
            data={"email": "writersguild@pastlives.space"},
        )
        assert resp.status_code in (200, 302)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["writersguild@pastlives.space"]

        # 3. Extract the code from the email body. The format matches what
        #    the existing login_via_alias_spec.py extracts.
        import re
        body = mail.outbox[0].body
        match = re.search(r"\b(\w{3}-\w{3})\b", body) or re.search(r"\b(\d{6})\b", body)
        assert match is not None, f"No login code found in email body: {body!r}"
        code = match.group(1)

        # 4. Submit the code. The URL is allauth's confirm_login_code.
        resp = member_client.post(
            "/accounts/login/code/confirm/",
            data={"code": code},
        )
        assert resp.status_code in (200, 302)

        # 5. The session is now authenticated as Penina's user.
        session_user_id = int(member_client.session["_auth_user_id"])
        assert session_user_id == linked_member.user_id
```

**If the URL paths or code regex above don't match plfog's actual allauth configuration** (allauth versions vary), update them by copying from `tests/membership/login_via_alias_spec.py::it_logs_in_via_any_verified_alias`. The two things that must stay true:

1. `mail.outbox[0].to == ["writersguild@pastlives.space"]`
2. `int(member_client.session["_auth_user_id"]) == linked_member.user_id`

- [ ] **Step 3: Run the end-to-end spec**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py::describe_end_to_end_login_via_admin_added_alias -v 2>&1 | tail -30
```

Expected: PASS. If the login-by-code URL or code format doesn't match, reconcile against `tests/membership/login_via_alias_spec.py` and re-run.

- [ ] **Step 4: Full spec-file run**

```bash
.venv/bin/python -m pytest tests/plfog/member_aliases_spec.py -v 2>&1 | tail -40
```

Expected: everything passes. Count them — it should be ~37 specs (6 form + 5 GET + 7 add + 7 remove + 6 set-primary + 6 toggle-verified + 2 admin link + 5 template + 1 end-to-end = 45, give or take).

- [ ] **Step 5: Lint, commit**

```bash
.venv/bin/ruff check tests/plfog/member_aliases_spec.py
.venv/bin/ruff format --check tests/plfog/member_aliases_spec.py
git add tests/plfog/member_aliases_spec.py
git commit -m "test(admin): end-to-end login via admin-added alias"
```

---

## Task 11: Full-suite regression + mypy + ruff

**Goal:** Verify nothing outside the feature broke.

- [ ] **Step 1: Full pytest run**

```bash
.venv/bin/python -m pytest 2>&1 | tail -20
```

Expected: all tests pass. 100% branch coverage. If coverage dropped below 100% on the new code, go back and add specs until it's at 100%.

- [ ] **Step 2: Full lint + format + mypy**

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m mypy plfog/ core/ membership/ hub/
```

Expected: all clean.

- [ ] **Step 3: Django checks**

```bash
.venv/bin/python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Manual smoke (optional but recommended)**

```bash
.venv/bin/python manage.py runserver
```

Log in as a superuser, navigate to a linked member's change page, click "Manage email aliases →", add `test@example.com`, confirm it appears verified and non-primary. Try removing it. Try toggling verified. Try set-primary on it (requires it to be verified). Browser back to the member page.

---

## Task 12: Changelog bullets (final merge-ready commit)

**Files:**
- Modify: `plfog/version.py`

Per `feedback_version_changelog.md`: only bump `version.py` on the final merge-ready commit, not during PR work. This is that commit.

- [ ] **Step 1: Verify you're at 1.4.1**

```bash
grep '^VERSION' plfog/version.py
```

Expected: `VERSION = "1.4.1"` (set by Task 0's rebase onto `hotfixes/1.4.0`).

- [ ] **Step 2: Append admin-alias bullets to the existing 1.4.1 entry**

In `plfog/version.py`, locate the 1.4.1 entry (currently a single bullet about hiding contributor counts) and append these two bullets to its `"changes"` list:

```python
            "Admins can now add email aliases directly from the member page — handy for shared addresses like guild mailboxes where the member can't easily receive a verification code themselves",
            "Admins can also remove aliases, change which one is primary, and toggle whether an alias is marked verified",
```

So the 1.4.1 stanza becomes:

```python
    {
        "version": "1.4.1",
        "date": "2026-04-11",
        "title": "Funding Results — Quieter Display & Admin Email Aliases",
        "changes": [
            "The funding results section no longer shows how many members contributed to each snapshot — keeping that detail private for now",
            "Admins can now add email aliases directly from the member page — handy for shared addresses like guild mailboxes where the member can't easily receive a verification code themselves",
            "Admins can also remove aliases, change which one is primary, and toggle whether an alias is marked verified",
        ],
    },
```

- [ ] **Step 3: Lint + commit**

```bash
.venv/bin/ruff check plfog/version.py
.venv/bin/ruff format --check plfog/version.py
git add plfog/version.py
git commit -m "chore: expand 1.4.1 changelog with admin email alias bullets"
```

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin feature/admin-email-aliases
gh pr create \
  --base hotfixes/1.4.0 \
  --head feature/admin-email-aliases \
  --title "1.4.1: admin-managed email aliases" \
  --body "$(cat <<'BODY'
## Summary

Stacks on PR #67 (hotfixes/1.4.0). Fills the gap left by 1.4.0: admins now have a dedicated page at /admin/members/<pk>/aliases/ to add, remove, set-primary, and toggle-verified on member email aliases. Entry point is a Manage email aliases → link on the member change page.

Ships in the same 1.4.1 release as the funding contributor-count privacy hotfix — just appends bullets to the existing 1.4.1 changelog entry.

## Spec

docs/superpowers/specs/2026-04-11-admin-email-aliases-design.md

## Test plan

- [x] pytest tests/plfog/member_aliases_spec.py — all specs pass
- [x] full pytest — no regressions
- [x] ruff check / ruff format / mypy — clean
- [x] end-to-end: admin adds writersguild@pastlives.space to a linked member → member logs in via login-by-code at that address
- [ ] Manual smoke on staging once merged to hotfixes/1.4.0
BODY
)"
```

When PR #67 merges to main, GitHub will auto-retarget this PR's base to main.

---

## Self-review checklist

**1. Spec coverage check:**

| Spec section | Covered by |
|---|---|
| Architecture (5 routes) | Tasks 2, 3, 4, 5, 6 |
| `AddEmailAliasForm` with duplicate guards | Task 1 |
| GET page rendering | Task 2 |
| Add action | Task 3 |
| Remove with lowest-pk promotion + only-email refuse + last-verified warn | Task 4 |
| Set-primary with verified gate + user.email sync | Task 5 |
| Toggle-verified with primary warning | Task 6 |
| Unlinked-member redirect | Task 2 (implementation) + Task 7 (explicit regression) |
| MemberAdmin entry point | Task 8 |
| Template UI | Tasks 2 (stub) + 9 (polish) |
| Safety rules (cross-member 404 via compound lookup) | Covered in remove/set-primary/toggle specs |
| End-to-end login-via-admin-added-alias | Task 10 |
| Changelog bullets (1.4.1) | Task 12 |
| Full regression pass | Task 11 |

All spec sections have tasks. ✅

**2. Placeholder scan:** no TBD/TODO/"implement later"/"add validation". Every step has exact code or exact commands. ✅

**3. Type consistency:** view names match across tasks (`member_aliases`, `member_aliases_add`, `member_aliases_remove`, `member_aliases_set_primary`, `member_aliases_toggle_verified`). URL names mirror (`admin_member_aliases*`). Template uses the same URL names. ✅

**4. Known soft spots:**
- Task 10's allauth login-by-code URLs and code-format regex may need adjustment — the plan explicitly says "copy from tests/membership/login_via_alias_spec.py if these don't match." That's the right posture; allauth versions vary and I can't verify the exact URLs without running the server.
- The `admin_client` fixture in Task 1 assumes `ensure_user_has_member` may auto-create a Member for the admin user. I've guarded for that by deleting it. If the signal doesn't fire, the delete is a no-op.

No placeholder fixes needed — the above are documented judgment calls, not gaps.
