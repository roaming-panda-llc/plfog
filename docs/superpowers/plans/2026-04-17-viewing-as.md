# "Viewing as" (role preview) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal topbar popover that lets an admin or guild officer toggle which of their roles the hub UI treats them as for the current session — without any schema changes.

**Architecture:** A single helper module (`hub/view_as.py`) exposes a `ViewAs` wrapper class and a `ViewAsMiddleware`. The middleware reads `member.fog_role` + a session list of hidden roles and attaches `request.view_as` to every request. A JSON toggle endpoint writes to the session. The hub `base.html` renders a popover with one checkbox per role the user actually holds, and the existing "Admin View" button is re-gated on `request.view_as.is_admin`. No new models, migrations, or fields.

**Tech Stack:** Django middleware, Django sessions, Alpine.js (already loaded in `base.html`), pytest-describe + factory-boy, existing `.pl-view-switcher` styles in `static/css/hub.css`.

**Coordination note:** The 1.6.3 slot is currently planned for the "Guild leads M2M" work (`docs/superpowers/plans/2026-04-16-guild-leads-m2m.md`). Whichever lands first takes 1.6.3; the other bumps to 1.6.4. This plan assumes 1.6.3 — if M2M lands first, bump this to 1.6.4 in Task 6.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `hub/view_as.py` | Create | `ViewAs` wrapper class, `compute_actual_roles()`, `ViewAsMiddleware`, constants |
| `hub/views.py` | Modify | Add `view_as_toggle` JSON view |
| `hub/urls.py` | Modify | Add `view-as/toggle/` route |
| `plfog/settings.py` | Modify | Register `hub.view_as.ViewAsMiddleware` in `MIDDLEWARE` |
| `templates/hub/base.html` | Modify | Add popover markup + Alpine component; re-gate Admin View button on `request.view_as.is_admin` |
| `static/css/hub.css` | Modify | Add `.pl-view-as-popover` styles (popover menu, rows) |
| `tests/hub/view_as_spec.py` | Create | BDD specs for `compute_actual_roles`, `ViewAs`, middleware, and the toggle endpoint |
| `plfog/version.py` | Modify | Bump version, add changelog entry |

---

## Design Summary (read this before starting any task)

**Role hierarchy (derived purely from `member.fog_role`):**
- `fog_role == "admin"` → actual roles `{admin, guild_officer, member}`
- `fog_role == "guild_officer"` → actual roles `{guild_officer, member}`
- `fog_role == "member"` → actual roles `{member}`
- Django `is_superuser` (no Member record or any `fog_role`) → actual roles `{admin, guild_officer, member}`
- Unauthenticated or no Member → actual roles `{}`

**Session key:** `"view_as_hidden_roles"` → `list[str]` of role names to hide.

**Effective roles:** `actual - hidden`.

**Popover visibility:** only when the user has more than `{member}` actual roles.

**The popover never lets you gain a role you don't have.** It only hides ones you do have. Unknown role names in the session are ignored. Toggling a role you don't hold is rejected server-side (403).

---

## Task 1: `hub/view_as.py` — core logic (no middleware yet)

**Files:**
- Create: `tests/hub/view_as_spec.py`
- Create: `hub/view_as.py`

- [ ] **Step 1.1: Write the failing specs for `compute_actual_roles`**

Create `tests/hub/view_as_spec.py`:

```python
"""BDD specs for the Viewing-as helper."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser, User

from hub.view_as import ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER, ViewAs, compute_actual_roles
from membership.models import Member
from tests.membership.factories import MemberFactory


@pytest.mark.django_db
def describe_compute_actual_roles():
    def it_returns_empty_frozenset_for_anonymous_user():
        assert compute_actual_roles(AnonymousUser()) == frozenset()

    def it_returns_empty_frozenset_when_user_has_no_member():
        user = User.objects.create_user(username="u", password="p")
        Member.objects.filter(user=user).delete()
        assert compute_actual_roles(user) == frozenset()

    def it_returns_admin_guild_officer_and_member_for_fog_admin():
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        roles = compute_actual_roles(member.user)
        assert roles == frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})

    def it_returns_guild_officer_and_member_for_fog_officer():
        member = MemberFactory(fog_role=Member.FogRole.GUILD_OFFICER)
        roles = compute_actual_roles(member.user)
        assert roles == frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER})

    def it_returns_only_member_for_regular_members():
        member = MemberFactory(fog_role=Member.FogRole.MEMBER)
        assert compute_actual_roles(member.user) == frozenset({ROLE_MEMBER})

    def it_treats_django_superuser_without_member_as_admin():
        user = User.objects.create_superuser(username="root", email="r@x.com", password="p")
        Member.objects.filter(user=user).delete()
        roles = compute_actual_roles(user)
        assert roles == frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
```

- [ ] **Step 1.2: Run specs to confirm they fail with ImportError**

Run: `pytest tests/hub/view_as_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hub.view_as'`.

- [ ] **Step 1.3: Write the minimal `hub/view_as.py`**

Create `hub/view_as.py`:

```python
"""Session-backed "Viewing as" role preview for the hub.

A Member's *actual* roles are derived from ``member.fog_role``. Any subset
can be *hidden* for the current session via the topbar popover — hidden role
names are stored in ``request.session["view_as_hidden_roles"]``.

*Effective* roles = actual − hidden. Every hub-side UI gate and convenience
check should read ``request.view_as`` (attached by ``ViewAsMiddleware``) so
the session override is respected uniformly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest

ROLE_MEMBER = "member"
ROLE_GUILD_OFFICER = "guild_officer"
ROLE_ADMIN = "admin"

ALL_ROLES: frozenset[str] = frozenset({ROLE_MEMBER, ROLE_GUILD_OFFICER, ROLE_ADMIN})

ROLE_LABELS: tuple[tuple[str, str], ...] = (
    (ROLE_MEMBER, "Member"),
    (ROLE_GUILD_OFFICER, "Guild Officer"),
    (ROLE_ADMIN, "Admin"),
)

SESSION_HIDDEN_KEY = "view_as_hidden_roles"


def compute_actual_roles(user: "AbstractBaseUser | AnonymousUser | None") -> frozenset[str]:
    """Derive the set of roles a user actually holds.

    Superusers without a linked Member still get the full set so emergency
    access is never dependent on Member data being correct.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()

    member = getattr(user, "member", None)

    if member is None:
        if getattr(user, "is_superuser", False):
            return ALL_ROLES
        return frozenset()

    from membership.models import Member as MemberModel

    if member.fog_role == MemberModel.FogRole.ADMIN:
        return frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})
    if member.fog_role == MemberModel.FogRole.GUILD_OFFICER:
        return frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER})
    return frozenset({ROLE_MEMBER})


def _read_hidden(session) -> frozenset[str]:  # noqa: ANN001 — Django session is untyped
    raw = session.get(SESSION_HIDDEN_KEY, []) if session is not None else []
    return frozenset(name for name in raw if name in ALL_ROLES)


class ViewAs:
    """Effective-roles wrapper attached to every request by the middleware."""

    def __init__(self, actual: frozenset[str], hidden: frozenset[str]) -> None:
        self.actual = actual
        self.hidden = hidden
        self.effective = actual - hidden

    def has(self, role: str) -> bool:
        return role in self.effective

    def has_actual(self, role: str) -> bool:
        """Check the *actual* set, ignoring session overrides — used by the popover."""
        return role in self.actual

    @property
    def is_admin(self) -> bool:
        return self.has(ROLE_ADMIN)

    @property
    def is_guild_officer(self) -> bool:
        return self.has(ROLE_GUILD_OFFICER)

    @property
    def is_member(self) -> bool:
        return self.has(ROLE_MEMBER)

    @property
    def show_popover(self) -> bool:
        """Only users with more than the base ``member`` role see the popover."""
        return len(self.actual - {ROLE_MEMBER}) > 0

    @property
    def popover_rows(self) -> list[dict[str, object]]:
        """Ordered ``{name, label, active}`` dicts for the popover UI."""
        return [
            {"name": name, "label": label, "active": name not in self.hidden}
            for name, label in ROLE_LABELS
            if name in self.actual
        ]

    @classmethod
    def for_request(cls, request: "HttpRequest") -> "ViewAs":
        actual = compute_actual_roles(request.user)
        hidden = _read_hidden(getattr(request, "session", None))
        return cls(actual=actual, hidden=hidden)
```

- [ ] **Step 1.4: Run specs to confirm they pass**

Run: `pytest tests/hub/view_as_spec.py::describe_compute_actual_roles -v`
Expected: all pass.

- [ ] **Step 1.5: Add `ViewAs` wrapper specs**

Append to `tests/hub/view_as_spec.py`:

```python
def describe_ViewAs():
    def it_marks_has_true_only_for_effective_roles():
        v = ViewAs(actual=frozenset({ROLE_ADMIN, ROLE_MEMBER}), hidden=frozenset({ROLE_ADMIN}))
        assert v.has(ROLE_ADMIN) is False
        assert v.has(ROLE_MEMBER) is True

    def it_has_actual_ignores_hidden():
        v = ViewAs(actual=frozenset({ROLE_ADMIN}), hidden=frozenset({ROLE_ADMIN}))
        assert v.has_actual(ROLE_ADMIN) is True
        assert v.has(ROLE_ADMIN) is False

    def it_exposes_convenience_properties():
        v = ViewAs(
            actual=frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER}),
            hidden=frozenset({ROLE_ADMIN}),
        )
        assert v.is_admin is False
        assert v.is_guild_officer is True
        assert v.is_member is True

    def describe_show_popover():
        def it_is_true_for_admins():
            v = ViewAs(actual=frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER}), hidden=frozenset())
            assert v.show_popover is True

        def it_is_true_for_guild_officers():
            v = ViewAs(actual=frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER}), hidden=frozenset())
            assert v.show_popover is True

        def it_is_false_for_plain_members():
            v = ViewAs(actual=frozenset({ROLE_MEMBER}), hidden=frozenset())
            assert v.show_popover is False

        def it_is_false_for_unauthenticated():
            v = ViewAs(actual=frozenset(), hidden=frozenset())
            assert v.show_popover is False

    def describe_popover_rows():
        def it_lists_rows_in_display_order_with_active_flags():
            v = ViewAs(
                actual=frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER}),
                hidden=frozenset({ROLE_ADMIN}),
            )
            assert v.popover_rows == [
                {"name": ROLE_MEMBER, "label": "Member", "active": True},
                {"name": ROLE_GUILD_OFFICER, "label": "Guild Officer", "active": True},
                {"name": ROLE_ADMIN, "label": "Admin", "active": False},
            ]

        def it_skips_roles_not_actually_held():
            v = ViewAs(actual=frozenset({ROLE_GUILD_OFFICER, ROLE_MEMBER}), hidden=frozenset())
            names = [row["name"] for row in v.popover_rows]
            assert names == [ROLE_MEMBER, ROLE_GUILD_OFFICER]
```

- [ ] **Step 1.6: Run and confirm pass**

Run: `pytest tests/hub/view_as_spec.py -v`
Expected: all pass.

- [ ] **Step 1.7: Commit**

```bash
git add hub/view_as.py tests/hub/view_as_spec.py
git commit -m "feat(hub): add view_as role-preview helper module"
```

---

## Task 2: `ViewAsMiddleware` — attach `request.view_as`

**Files:**
- Modify: `hub/view_as.py` (append `ViewAsMiddleware`)
- Modify: `plfog/settings.py` (register middleware)
- Modify: `tests/hub/view_as_spec.py` (add middleware specs)

- [ ] **Step 2.1: Write the failing middleware spec**

Append to `tests/hub/view_as_spec.py`:

```python
from django.test import RequestFactory

from hub.view_as import ViewAsMiddleware


@pytest.mark.django_db
def describe_ViewAsMiddleware():
    def it_attaches_view_as_to_request(rf: RequestFactory):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        request = rf.get("/")
        request.user = member.user
        request.session = {}

        captured: dict[str, object] = {}

        def get_response(req):
            captured["view_as"] = req.view_as
            return "ok"

        ViewAsMiddleware(get_response)(request)

        assert captured["view_as"].is_admin is True
        assert captured["view_as"].actual == frozenset({ROLE_ADMIN, ROLE_GUILD_OFFICER, ROLE_MEMBER})

    def it_respects_hidden_roles_in_session(rf: RequestFactory):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        request = rf.get("/")
        request.user = member.user
        request.session = {"view_as_hidden_roles": ["admin"]}

        captured: dict[str, object] = {}

        def get_response(req):
            captured["view_as"] = req.view_as
            return "ok"

        ViewAsMiddleware(get_response)(request)

        assert captured["view_as"].is_admin is False
        assert captured["view_as"].is_guild_officer is True
```

Add this fixture to the top of the file (after imports):

```python
@pytest.fixture
def rf() -> RequestFactory:
    return RequestFactory()
```

- [ ] **Step 2.2: Run and confirm ImportError**

Run: `pytest tests/hub/view_as_spec.py::describe_ViewAsMiddleware -v`
Expected: FAIL with `ImportError: cannot import name 'ViewAsMiddleware'`.

- [ ] **Step 2.3: Implement the middleware**

Append to `hub/view_as.py`:

```python
class ViewAsMiddleware:
    """Attach ``request.view_as`` to every request.

    Must run after ``AuthenticationMiddleware`` (needs ``request.user``)
    and ``SessionMiddleware`` (needs ``request.session``).
    """

    def __init__(self, get_response) -> None:  # noqa: ANN001
        self.get_response = get_response

    def __call__(self, request: "HttpRequest"):
        request.view_as = ViewAs.for_request(request)
        return self.get_response(request)
```

- [ ] **Step 2.4: Run and confirm pass**

Run: `pytest tests/hub/view_as_spec.py -v`
Expected: all pass.

- [ ] **Step 2.5: Register middleware in settings**

In `plfog/settings.py`, add `"hub.view_as.ViewAsMiddleware"` to `MIDDLEWARE` immediately after `"allauth.account.middleware.AccountMiddleware"`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "hub.view_as.ViewAsMiddleware",
    "plfog.service_worker_middleware.ServiceWorkerAllowedMiddleware",
]
```

- [ ] **Step 2.6: Smoke-test through a real view**

Run: `pytest tests/hub/ -v -k "views_spec"`
Expected: existing hub view specs all still pass (middleware must not break them).

- [ ] **Step 2.7: Commit**

```bash
git add hub/view_as.py plfog/settings.py tests/hub/view_as_spec.py
git commit -m "feat(hub): wire ViewAsMiddleware and attach request.view_as"
```

---

## Task 3: Toggle endpoint

**Files:**
- Modify: `hub/urls.py`
- Modify: `hub/views.py`
- Modify: `tests/hub/view_as_spec.py`

- [ ] **Step 3.1: Write the failing endpoint specs**

Append to `tests/hub/view_as_spec.py`:

```python
import json

from django.test import Client


@pytest.mark.django_db
def describe_view_as_toggle_endpoint():
    def it_adds_role_to_hidden_set(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {"hidden": ["admin"]}
        assert client.session["view_as_hidden_roles"] == ["admin"]

    def it_removes_role_when_hidden_is_false(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")
        session = client.session
        session["view_as_hidden_roles"] = ["admin", "guild_officer"]
        session.save()

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": False}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {"hidden": ["guild_officer"]}

    def it_rejects_unknown_role_names(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "wizard", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code == 400

    def it_rejects_toggling_a_role_the_user_does_not_hold(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.MEMBER)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")

        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code == 403

    def it_rejects_malformed_json(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")

        response = client.post("/view-as/toggle/", data=b"not json", content_type="application/json")

        assert response.status_code == 400

    def it_requires_login(client: Client):
        response = client.post(
            "/view-as/toggle/",
            data=json.dumps({"role": "admin", "hidden": True}),
            content_type="application/json",
        )

        assert response.status_code in (302, 401, 403)  # redirect to login or deny
```

- [ ] **Step 3.2: Run and confirm fail**

Run: `pytest tests/hub/view_as_spec.py::describe_view_as_toggle_endpoint -v`
Expected: FAIL with 404 from the URL resolver.

- [ ] **Step 3.3: Add the toggle view**

Append to `hub/views.py` (below the existing imports and other views):

```python
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from hub.view_as import ALL_ROLES, SESSION_HIDDEN_KEY


@require_POST
@login_required
def view_as_toggle(request: HttpRequest) -> JsonResponse:
    """Add or remove a role from the session-hidden set.

    Body: ``{"role": "admin", "hidden": true}``. Unknown role names and
    roles the user does not actually hold are rejected so the session
    can never carry junk or grant privileges.
    """
    try:
        payload = json.loads(request.body or b"{}")
        role = payload["role"]
        hidden = bool(payload["hidden"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"error": "Invalid request"}, status=400)

    if role not in ALL_ROLES:
        return JsonResponse({"error": f"Unknown role '{role}'"}, status=400)

    if not request.view_as.has_actual(role):
        return JsonResponse({"error": "Cannot toggle a role you don't have"}, status=403)

    current = set(request.session.get(SESSION_HIDDEN_KEY, []))
    if hidden:
        current.add(role)
    else:
        current.discard(role)
    request.session[SESSION_HIDDEN_KEY] = sorted(current)

    return JsonResponse({"hidden": sorted(current)})
```

(If `json` and the other imports are already present at the top of `hub/views.py`, don't duplicate them — move them up with the existing imports instead.)

- [ ] **Step 3.4: Add the URL route**

In `hub/urls.py`, add to `urlpatterns`:

```python
path("view-as/toggle/", views.view_as_toggle, name="hub_view_as_toggle"),
```

- [ ] **Step 3.5: Run and confirm pass**

Run: `pytest tests/hub/view_as_spec.py -v`
Expected: all pass.

- [ ] **Step 3.6: Commit**

```bash
git add hub/views.py hub/urls.py tests/hub/view_as_spec.py
git commit -m "feat(hub): add view-as toggle endpoint"
```

---

## Task 4: Topbar popover UI

**Files:**
- Modify: `templates/hub/base.html`
- Modify: `static/css/hub.css`

- [ ] **Step 4.1: Add the popover markup**

In `templates/hub/base.html`, locate the topbar block that contains the current `{% if user.is_staff %}` Admin View button (around line 165–172 on main). Replace that block with:

```html
{% if request.view_as.is_admin %}
<span class="pl-topbar__divider"></span>
<a href="{% url 'admin:index' %}" class="pl-view-switcher" hx-boost="false" title="Switch to Admin View">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
    Admin View
</a>
{% endif %}
{% if request.view_as.show_popover %}
<span class="pl-topbar__divider"></span>
<div class="pl-view-as-popover"
     x-data="viewAsPopover()"
     @keydown.escape.window="if (open) { open = false; $el.querySelector('button').focus() }">
    <button type="button" class="pl-view-switcher" @click="open = !open" :aria-expanded="open" title="Viewing as">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
        </svg>
        Viewing as
    </button>
    <div class="pl-view-as-popover__menu" x-show="open" x-transition @click.away="open = false" role="menu">
        <div class="pl-view-as-popover__header">Show controls for</div>
        {% for row in request.view_as.popover_rows %}
        <label class="pl-view-as-popover__row">
            <input type="checkbox"
                   value="{{ row.name }}"
                   {% if row.active %}checked{% endif %}
                   @change="toggle($event.target.value, !$event.target.checked)">
            <span>{{ row.label }}</span>
        </label>
        {% endfor %}
        <div class="pl-view-as-popover__hint">Unchecking hides that role's UI for this session.</div>
    </div>
</div>
{% endif %}
```

Note the old `{% if user.is_staff %}` guard is now `{% if request.view_as.is_admin %}` — this gates the Admin View button on the toggle.

- [ ] **Step 4.2: Add the Alpine component**

Still in `templates/hub/base.html`, find the existing inline `<script>` block that registers other Alpine components (near the bottom of the file). If one exists, append the function below inside it. Otherwise add a new `<script>` block just before `</body>`:

```html
<script>
    function viewAsPopover() {
        return {
            open: false,
            async toggle(role, hidden) {
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
                    || document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.split('=')[1];
                const response = await fetch("{% url 'hub_view_as_toggle' %}", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken || "",
                    },
                    body: JSON.stringify({ role, hidden }),
                });
                if (response.ok) {
                    window.location.reload();
                }
            },
        };
    }
</script>
```

A full reload keeps the implementation trivial — no need to surgically re-render every gated region.

- [ ] **Step 4.3: Add popover styles**

Append to `static/css/hub.css`:

```css
/* Viewing-as popover */
.pl-view-as-popover {
    position: relative;
}

.pl-view-as-popover__menu {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    min-width: 200px;
    background: var(--pl-surface-1, #0f1a2a);
    border: 1px solid var(--pl-border, rgba(255, 255, 255, 0.08));
    border-radius: 8px;
    padding: 8px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    z-index: 50;
}

.pl-view-as-popover__header {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.6;
    padding: 4px 8px 8px;
}

.pl-view-as-popover__row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
}

.pl-view-as-popover__row:hover {
    background: rgba(255, 255, 255, 0.05);
}

.pl-view-as-popover__hint {
    font-size: 11px;
    opacity: 0.55;
    padding: 8px;
    border-top: 1px solid var(--pl-border, rgba(255, 255, 255, 0.08));
    margin-top: 4px;
}
```

If the codebase has newer design tokens in `hub.css`, swap `var(--pl-surface-1, ...)` / `var(--pl-border, ...)` to match. The fallback values in the `var(...)` calls keep it working either way.

- [ ] **Step 4.4: Write a template-integration spec**

Append to `tests/hub/view_as_spec.py`:

```python
@pytest.mark.django_db
def describe_popover_in_hub_template():
    def it_renders_popover_for_admins(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")

        response = client.get("/guilds/voting/")

        assert response.status_code == 200
        assert b"pl-view-as-popover" in response.content
        assert b"Viewing as" in response.content

    def it_hides_popover_for_plain_members(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.MEMBER)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")

        response = client.get("/guilds/voting/")

        assert response.status_code == 200
        assert b"pl-view-as-popover" not in response.content

    def it_hides_admin_view_button_when_admin_role_is_hidden(client: Client):
        member = MemberFactory(fog_role=Member.FogRole.ADMIN)
        member.user.set_password("p")
        member.user.save()
        client.login(username=member.user.username, password="p")
        session = client.session
        session["view_as_hidden_roles"] = ["admin"]
        session.save()

        response = client.get("/guilds/voting/")

        assert b"Admin View" not in response.content
```

- [ ] **Step 4.5: Run all view_as specs**

Run: `pytest tests/hub/view_as_spec.py -v`
Expected: all pass.

- [ ] **Step 4.6: Manual smoke-test**

Run: `python manage.py runserver` and log in as an admin. Confirm:
- "Viewing as" button appears in the topbar next to "Admin View".
- Clicking it opens a popover with three checkboxes (Admin, Guild Officer, Member).
- Unchecking "Admin" reloads the page and the "Admin View" button disappears.
- Re-checking "Admin" brings it back.

Log in as a plain member and confirm no popover appears.

- [ ] **Step 4.7: Commit**

```bash
git add templates/hub/base.html static/css/hub.css tests/hub/view_as_spec.py
git commit -m "feat(hub): add Viewing-as popover in topbar"
```

---

## Task 5: Version bump + changelog

**Files:**
- Modify: `plfog/version.py`

- [ ] **Step 5.1: Bump version and prepend changelog entry**

In `plfog/version.py`, change `VERSION = "1.6.2"` to `VERSION = "1.6.3"` (or `"1.6.4"` if the guild-leads M2M already landed on main at 1.6.3 — check `git log` first).

Prepend to the `CHANGELOG` list:

```python
{
    "version": "1.6.3",
    "date": "2026-04-17",
    "title": "Admin role preview in the hub",
    "changes": [
        "Admins and guild officers now have a new \"Viewing as\" button in the topbar — use it to preview the hub the way a plain member or guild officer would see it, without logging out. Unchecking a role hides that role's UI for the current session only.",
    ],
},
```

- [ ] **Step 5.2: Run the full test suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 5.3: Lint + format**

Run: `ruff format . && ruff check --fix .`
Expected: clean output.

- [ ] **Step 5.4: Commit**

```bash
git add plfog/version.py
git commit -m "chore: bump to 1.6.3 (Viewing-as feature)"
```

---

## Out of scope (intentional)

These are *not* part of this plan — keep them for follow-ups so the change stays tight:

- Re-gating guild edit affordances (the edit button on `guild_detail.html`) on `request.view_as.is_guild_officer`. Requires threading `view_as` into `Member.can_edit_guild()` or doing the check inline in the template. Add in a follow-up PR once the popover scaffolding lands.
- A Django template tag (`{% if view_as.is_admin %}` sugar). The `request.view_as.*` access in templates is fine — no sugar needed yet.
- Per-guild scoping. If guild officers end up needing a separate "view as officer of guild X" mode, that's a separate design — current plan treats guild_officer as a global flag, matching `fog_role`.
- Animations / transitions beyond Alpine's default `x-transition`.

---

## Self-review checklist

- [x] Every role name used in specs (`admin`, `guild_officer`, `member`) matches `ROLE_*` constants in `hub/view_as.py`.
- [x] Every URL used in specs (`/view-as/toggle/`) matches the route added in Task 3.
- [x] Every template class name (`pl-view-as-popover`, `pl-view-as-popover__menu`, etc.) matches the CSS added in Task 4.3.
- [x] Session key `view_as_hidden_roles` is used consistently in the module, tests, and template checks.
- [x] Middleware is registered after `AuthenticationMiddleware` and `SessionMiddleware`, and before the service-worker middleware.
- [x] Version bump + changelog entry uses member-friendly language (no PR numbers, no commit hashes).
- [x] No placeholders, no "TBD", no "implement error handling" — every step has the full code.
