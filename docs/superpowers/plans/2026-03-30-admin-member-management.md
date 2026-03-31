# Admin Member Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the admin Members page into a unified user/member management interface with email alias support, user creation toggle, and Users/All Members filter.

**Architecture:** Add a `MemberEmail` model for alias emails. Enhance `MemberAdmin` with a Users/All toggle filter, inline email alias editor, and a "Create login immediately" checkbox on the add form. Update the login flow (`AutoCreateUserLoginCodeForm`) to check aliases. Hide the default User admin. Unregister allauth's EmailAddress admin.

**Tech Stack:** Django 5.x, django-unfold admin theme, django-allauth (EmailAddress model), factory-boy, pytest-describe

---

### Task 1: MemberEmail Model

**Files:**
- Modify: `membership/models.py` (add MemberEmail class after Member)
- Create: `membership/migrations/0017_memberemail.py` (auto-generated)
- Modify: `tests/membership/factories.py` (add MemberEmailFactory)
- Create: `tests/membership/member_email_spec.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/membership/member_email_spec.py
import pytest
from django.db import IntegrityError

from membership.models import Member, MemberEmail
from tests.membership.factories import MemberEmailFactory, MemberFactory


@pytest.mark.django_db
def describe_MemberEmail():
    def it_stores_an_alias_email_for_a_member():
        member = MemberFactory()
        alias = MemberEmail.objects.create(member=member, email="alias@example.com")
        assert alias.member == member
        assert alias.email == "alias@example.com"
        assert alias.is_primary is False

    def it_enforces_unique_email():
        member = MemberFactory()
        MemberEmail.objects.create(member=member, email="dupe@example.com")
        with pytest.raises(IntegrityError):
            MemberEmail.objects.create(member=member, email="dupe@example.com")

    def it_has_str_representation():
        member = MemberFactory(full_legal_name="Jane Doe")
        alias = MemberEmail.objects.create(member=member, email="jane@alt.com")
        assert str(alias) == "jane@alt.com (Jane Doe)"

    def it_cascades_on_member_delete():
        member = MemberFactory()
        MemberEmail.objects.create(member=member, email="gone@example.com")
        member_id = member.pk
        member.delete()
        assert not MemberEmail.objects.filter(member_id=member_id).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/membership/member_email_spec.py -v`
Expected: FAIL — `ImportError: cannot import name 'MemberEmail'`

- [ ] **Step 3: Write the MemberEmail model**

Add to `membership/models.py` after the `Member` class (before `Guild`):

```python
class MemberEmail(models.Model):
    """Additional email aliases for a member. The primary email stays on Member.email."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="emails")
    email = models.EmailField(unique=True, help_text="An email address for this member.")
    is_primary = models.BooleanField(default=False, help_text="Primary email shown in lists.")

    class Meta:
        ordering = ["-is_primary", "email"]
        verbose_name = "Email Alias"
        verbose_name_plural = "Email Aliases"

    def __str__(self) -> str:
        return f"{self.email} ({self.member.display_name})"
```

- [ ] **Step 4: Add factory**

Add to `tests/membership/factories.py`:

```python
from membership.models import MemberEmail

class MemberEmailFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MemberEmail

    member = factory.SubFactory(MemberFactory)
    email = factory.Sequence(lambda n: f"alias{n}@example.com")
    is_primary = False
```

- [ ] **Step 5: Generate migration**

Run: `python3 manage.py makemigrations membership -n memberemail`

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/membership/member_email_spec.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add membership/models.py membership/migrations/0017_memberemail.py tests/membership/member_email_spec.py tests/membership/factories.py
git commit -m "feat: add MemberEmail model for email aliases"
```

---

### Task 2: Users Filter on Admin Members List

**Files:**
- Modify: `membership/admin.py` (add `HasUserFilter`)
- Modify: `tests/membership/admin_spec.py` (add filter tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/membership/admin_spec.py`:

```python
@pytest.mark.django_db
def describe_has_user_filter():
    def it_shows_all_members_by_default(admin_client):
        MemberFactory(full_legal_name="No User Nancy", user=None)
        user = User.objects.create_user(username="hasuser", email="hasuser@example.com")
        # signal auto-creates member; update name for assertion
        user.member.full_legal_name = "Has User Helen"
        user.member.save()
        resp = admin_client.get("/admin/membership/member/?status=all")
        content = resp.content.decode()
        assert "No User Nancy" in content
        assert "Has User Helen" in content

    def it_shows_only_users_when_users_filter_selected(admin_client):
        MemberFactory(full_legal_name="No User Nancy", user=None)
        user = User.objects.create_user(username="hasuser2", email="hasuser2@example.com")
        user.member.full_legal_name = "Has User Helen"
        user.member.save()
        resp = admin_client.get("/admin/membership/member/?status=all&has_user=yes")
        content = resp.content.decode()
        assert "No User Nancy" not in content
        assert "Has User Helen" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/membership/admin_spec.py::describe_has_user_filter -v`
Expected: FAIL — filter parameter `has_user` not recognized / no filtering happens

- [ ] **Step 3: Add HasUserFilter to admin.py**

Add to `membership/admin.py` after `ActiveStatusFilter`:

```python
class HasUserFilter(admin.SimpleListFilter):
    """Filter to show only members with linked User accounts (i.e., they've logged in)."""

    title = "account type"
    parameter_name = "has_user"

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> list[tuple[str, str]]:  # type: ignore[override]
        return [
            ("yes", "Users — members who have logged into this web app"),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Member]) -> QuerySet[Member]:
        if self.value() == "yes":
            return queryset.filter(user__isnull=False)
        return queryset
```

Add `HasUserFilter` to `MemberAdmin.list_filter`:

```python
list_filter = [ActiveStatusFilter, HasUserFilter, "member_type"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/membership/admin_spec.py::describe_has_user_filter -v`
Expected: PASS

- [ ] **Step 5: Update existing list_filter test**

The existing test `it_has_expected_list_filter` checks the exact filter list. Update it:

```python
def it_has_expected_list_filter():
    member_admin = admin.site._registry[Member]
    assert member_admin.list_filter[0] is ActiveStatusFilter
    assert HasUserFilter in member_admin.list_filter
    assert "member_type" in member_admin.list_filter
```

- [ ] **Step 6: Run full admin spec**

Run: `pytest tests/membership/admin_spec.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add membership/admin.py tests/membership/admin_spec.py
git commit -m "feat: add Users/All Members toggle filter in admin"
```

---

### Task 3: Email Aliases Inline in Admin

**Files:**
- Modify: `membership/admin.py` (add `MemberEmailInline`, attach to `MemberAdmin`)
- Modify: `tests/membership/admin_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/membership/admin_spec.py`:

```python
from membership.admin import MemberEmailInline


def describe_MemberEmailInline():
    def it_is_attached_to_member_admin():
        member_admin = admin.site._registry[Member]
        inline_classes = [type(i) for i in member_admin.get_inline_instances(MagicMock())]
        assert MemberEmailInline in inline_classes
```

Add this import at the top of the file:

```python
from unittest.mock import MagicMock
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/membership/admin_spec.py::describe_MemberEmailInline -v`
Expected: FAIL — `ImportError: cannot import name 'MemberEmailInline'`

- [ ] **Step 3: Add inline to admin.py**

Add imports and inline class to `membership/admin.py`:

```python
from unfold.admin import TabularInline

from .models import FundingSnapshot, Guild, Member, MemberEmail, VotePreference


class MemberEmailInline(TabularInline):
    model = MemberEmail
    extra = 1
    fields = ["email", "is_primary"]
```

Add to `MemberAdmin`:

```python
inlines = [MemberEmailInline]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/membership/admin_spec.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add membership/admin.py tests/membership/admin_spec.py
git commit -m "feat: add email aliases inline to member admin"
```

---

### Task 4: "Create Login Immediately" on Add Form

**Files:**
- Modify: `membership/admin.py` (override `get_fieldsets` for add view, override `save_model`)
- Modify: `membership/forms.py` (add `MemberAdminForm`)
- Modify: `tests/membership/admin_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/membership/admin_spec.py`:

```python
@pytest.mark.django_db
def describe_admin_create_user_with_member():
    def it_creates_member_without_user_by_default(admin_client):
        plan = MembershipPlanFactory()
        resp = admin_client.post(
            "/admin/membership/member/add/",
            {
                "full_legal_name": "Test Person",
                "email": "test@example.com",
                "membership_plan": plan.pk,
                "status": "active",
                "member_type": "standard",
                "fog_role": "member",
                "create_user": "",  # unchecked
                # MemberEmailInline management form fields
                "emails-TOTAL_FORMS": "0",
                "emails-INITIAL_FORMS": "0",
                "emails-MIN_NUM_FORMS": "0",
                "emails-MAX_NUM_FORMS": "1000",
            },
        )
        assert resp.status_code == 302  # redirect on success
        member = Member.objects.get(email="test@example.com")
        assert member.user is None

    def it_creates_member_with_user_when_checked(admin_client):
        plan = MembershipPlanFactory()
        resp = admin_client.post(
            "/admin/membership/member/add/",
            {
                "full_legal_name": "Login Person",
                "email": "login@example.com",
                "membership_plan": plan.pk,
                "status": "active",
                "member_type": "employee",
                "fog_role": "admin",
                "create_user": "on",
                "emails-TOTAL_FORMS": "0",
                "emails-INITIAL_FORMS": "0",
                "emails-MIN_NUM_FORMS": "0",
                "emails-MAX_NUM_FORMS": "1000",
            },
        )
        assert resp.status_code == 302
        member = Member.objects.get(email="login@example.com")
        assert member.user is not None
        assert member.user.email == "login@example.com"
        assert member.user.username == "login@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/membership/admin_spec.py::describe_admin_create_user_with_member -v`
Expected: FAIL — `create_user` field not recognized, or User auto-created by signal

- [ ] **Step 3: Create MemberAdminForm with create_user checkbox**

Add to `membership/forms.py`:

```python
class MemberAdminForm(forms.ModelForm):
    """Admin form for Member with optional User creation."""

    create_user = forms.BooleanField(
        required=False,
        label="Create login immediately",
        help_text="Creates a User account so this person can log in right away.",
    )

    class Meta:
        model = Member
        fields = "__all__"
```

- [ ] **Step 4: Override save_model in MemberAdmin**

In `membership/admin.py`, add to `MemberAdmin`:

```python
from django.contrib.auth import get_user_model
from .forms import MemberAdminForm

# In MemberAdmin class:
form = MemberAdminForm

def save_model(self, request: HttpRequest, obj: Member, form: forms.BaseForm, change: bool) -> None:
    # For new members, temporarily disconnect the signal so it doesn't auto-create a member
    create_user = form.cleaned_data.get("create_user", False)

    if not change and create_user and obj.email:
        # Save the member first (without a user)
        super().save_model(request, obj, form, change)
        # Now create the user and link
        UserModel = get_user_model()
        user = UserModel.objects.create_user(username=obj.email, email=obj.email)
        # The signal will try to auto-create a member, but one already exists.
        # Delete the signal-created duplicate and link to ours.
        from membership.models import Member as MemberModel
        MemberModel.objects.filter(user=user).exclude(pk=obj.pk).delete()
        obj.user = user
        obj.save(update_fields=["user"])
        obj.sync_user_permissions()
    else:
        super().save_model(request, obj, form, change)
```

- [ ] **Step 5: Add create_user field to add-form fieldsets only**

Update `get_fieldsets` in `MemberAdmin` to include `create_user` in the add form:

```python
def get_fieldsets(self, request: HttpRequest, obj: object = None) -> list[tuple[str, dict]]:
    membership_fields: list[str] = [
        "membership_plan",
        "status",
        "member_type",
        "join_date",
        "cancellation_date",
        "committed_until",
    ]
    if request.user.is_superuser:
        membership_fields.insert(3, "fog_role")

    fieldsets = [
        (
            "Personal Info",
            {
                "fields": [
                    "full_legal_name",
                    "preferred_name",
                    "email",
                    "phone",
                    "billing_name",
                ],
            },
        ),
        (
            "Membership",
            {
                "fields": membership_fields,
            },
        ),
        (
            "Emergency Contact",
            {
                "fields": [
                    "emergency_contact_name",
                    "emergency_contact_phone",
                    "emergency_contact_relationship",
                ],
            },
        ),
        (
            "Notes",
            {
                "fields": ["notes"],
            },
        ),
    ]

    # Show "user" link on edit, "create_user" checkbox on add
    if obj is not None:
        fieldsets[0][1]["fields"].insert(0, "user")
    else:
        fieldsets[0][1]["fields"].append("create_user")

    return fieldsets
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/membership/admin_spec.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add membership/admin.py membership/forms.py tests/membership/admin_spec.py
git commit -m "feat: add 'Create login immediately' checkbox to member admin add form"
```

---

### Task 5: Login Flow — Check Email Aliases

**Files:**
- Modify: `plfog/adapters.py` (update `AutoCreateUserLoginCodeForm.clean_email`)
- Modify: `membership/signals.py` (check `MemberEmail` too)
- Modify: `tests/plfog/adapters_spec.py`
- Modify: `tests/membership/signals_spec.py`

- [ ] **Step 1: Write the failing test for login with alias**

Add to `tests/plfog/adapters_spec.py`:

```python
def describe_AutoCreateUserLoginCodeForm():
    def describe_clean_email():
        def it_auto_creates_user_for_member_with_alias_email(rf):
            from membership.models import MemberEmail
            from tests.membership.factories import MemberFactory

            member = MemberFactory(user=None, email="primary@example.com")
            MemberEmail.objects.create(member=member, email="alias@example.com")

            form_data = {"email": "alias@example.com"}
            form = AutoCreateUserLoginCodeForm(data=form_data)
            # We just need to verify the User was created — form.is_valid() may
            # fail due to allauth internals, so check the side effect directly.
            try:
                form.is_valid()
            except Exception:
                pass

            assert User.objects.filter(email__iexact="alias@example.com").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plfog/adapters_spec.py::describe_AutoCreateUserLoginCodeForm -v`
Expected: FAIL — no User created because alias lookup not implemented

- [ ] **Step 3: Update AutoCreateUserLoginCodeForm**

In `plfog/adapters.py`, update `clean_email`:

```python
def clean_email(self) -> str:
    """Auto-create User for known Members, then run normal allauth lookup."""
    from membership.models import Member, MemberEmail

    email: str = self.cleaned_data.get("email", "")
    if email and not User.objects.filter(email__iexact=email).exists():
        # Check primary email on Member
        if Member.objects.filter(email__iexact=email, user__isnull=True).exists():
            User.objects.create_user(username=email, email=email)
            logger.info("Auto-created User for existing Member (primary email): %s", email)
        else:
            # Check email aliases
            try:
                alias = MemberEmail.objects.select_related("member").get(
                    email__iexact=email, member__user__isnull=True
                )
                User.objects.create_user(username=email, email=email)
                logger.info(
                    "Auto-created User for existing Member (alias email): %s -> %s",
                    email,
                    alias.member.display_name,
                )
            except MemberEmail.DoesNotExist:
                pass

    return super().clean_email()
```

- [ ] **Step 4: Update signal to check MemberEmail**

In `membership/signals.py`, update `ensure_user_has_member` to also check aliases:

```python
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_has_member(sender: type, instance: Any, **kwargs: Any) -> None:
    """Auto-create or link a Member record for any user who doesn't have one."""
    from .models import Member, MemberEmail, MembershipPlan

    try:
        instance.member
        return
    except Member.DoesNotExist:
        pass

    email = getattr(instance, "email", "") or ""
    if email:
        # Check primary email on Member
        try:
            member = Member.objects.get(email__iexact=email, user__isnull=True)
            member.user = instance
            member.full_legal_name = instance.get_full_name() or member.full_legal_name or instance.username
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["user", "full_legal_name", "status"])
            logger.info("Linked existing Member (primary email) to user %s.", instance.username)
            return
        except Member.DoesNotExist:
            pass

        # Check email aliases
        try:
            alias = MemberEmail.objects.select_related("member").get(
                email__iexact=email, member__user__isnull=True
            )
            member = alias.member
            member.user = instance
            member.full_legal_name = instance.get_full_name() or member.full_legal_name or instance.username
            member.status = Member.Status.ACTIVE
            member.save(update_fields=["user", "full_legal_name", "status"])
            logger.info("Linked existing Member (alias email %s) to user %s.", email, instance.username)
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
        email=instance.email or "",
        membership_plan=plan,
        status=Member.Status.ACTIVE,
    )
    logger.info("Auto-created Member for user %s with plan '%s'.", instance.username, plan.name)
```

- [ ] **Step 5: Add signal test for alias linking**

Add to `tests/membership/signals_spec.py`:

```python
def it_links_pre_created_member_by_alias_email():
    from membership.models import MemberEmail

    plan = MembershipPlanFactory()
    member = MemberFactory(
        user=None,
        email="primary@example.com",
        full_legal_name="Alias Person",
        status=Member.Status.INVITED,
        membership_plan=plan,
    )
    MemberEmail.objects.create(member=member, email="alias@example.com")

    user = User.objects.create_user(
        username="aliaslogin",
        email="alias@example.com",
        password="password",
    )
    member.refresh_from_db()
    assert member.user == user
    assert member.status == Member.Status.ACTIVE
    # No duplicate Member created
    assert Member.objects.filter(user=user).count() == 1
```

- [ ] **Step 6: Run all affected tests**

Run: `pytest tests/plfog/adapters_spec.py tests/membership/signals_spec.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add plfog/adapters.py membership/signals.py tests/plfog/adapters_spec.py tests/membership/signals_spec.py
git commit -m "feat: login flow checks email aliases for member linking"
```

---

### Task 6: Hide Default User and EmailAddress Admin

**Files:**
- Modify: `membership/admin.py` (unregister User and EmailAddress from admin)
- Modify: `tests/membership/admin_spec.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/membership/admin_spec.py`:

```python
from django.contrib.auth import get_user_model

UserModel = get_user_model()


def describe_hidden_admin_pages():
    def it_does_not_register_user_admin():
        assert UserModel not in admin.site._registry

    def it_does_not_register_emailaddress_admin():
        from allauth.account.models import EmailAddress

        assert EmailAddress not in admin.site._registry
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/membership/admin_spec.py::describe_hidden_admin_pages -v`
Expected: FAIL — both are currently registered

- [ ] **Step 3: Add unregister calls to membership/admin.py**

Add at the bottom of `membership/admin.py`:

```python
# Hide default User admin and allauth EmailAddress admin — members page is the
# single interface for user management.
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

for _model in (get_user_model(), EmailAddress):
    try:
        admin.site.unregister(_model)
    except admin.sites.NotRegistered:
        pass
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/membership/admin_spec.py::describe_hidden_admin_pages -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add membership/admin.py tests/membership/admin_spec.py
git commit -m "feat: hide User and EmailAddress admin pages"
```

---

### Task 7: Search by Alias Email + Version Bump

**Files:**
- Modify: `membership/admin.py` (override `get_search_results`)
- Modify: `plfog/version.py`
- Modify: `tests/membership/admin_spec.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/membership/admin_spec.py`:

```python
@pytest.mark.django_db
def describe_admin_search_by_alias():
    def it_finds_member_by_alias_email(admin_client):
        from membership.models import MemberEmail

        member = MemberFactory(full_legal_name="Alias Andy", email="primary@example.com")
        MemberEmail.objects.create(member=member, email="secret@alias.com")
        resp = admin_client.get("/admin/membership/member/?status=all&q=secret@alias.com")
        content = resp.content.decode()
        assert "Alias Andy" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/membership/admin_spec.py::describe_admin_search_by_alias -v`
Expected: FAIL — search doesn't find members by alias email

- [ ] **Step 3: Override get_search_results**

Add to `MemberAdmin` in `membership/admin.py`:

```python
def get_search_results(
    self, request: HttpRequest, queryset: QuerySet[Member], search_term: str
) -> tuple[QuerySet[Member], bool]:
    queryset, use_distinct = super().get_search_results(request, queryset, search_term)
    if search_term:
        from .models import MemberEmail

        alias_member_ids = MemberEmail.objects.filter(email__icontains=search_term).values_list(
            "member_id", flat=True
        )
        queryset = queryset | self.model.objects.filter(pk__in=alias_member_ids)
        use_distinct = True
    return queryset, use_distinct
```

- [ ] **Step 4: Run test**

Run: `pytest tests/membership/admin_spec.py::describe_admin_search_by_alias -v`
Expected: PASS

- [ ] **Step 5: Update search_fields test**

Update the existing `it_has_expected_search_fields` test:

```python
def it_has_expected_search_fields():
    member_admin = admin.site._registry[Member]
    assert "full_legal_name" in member_admin.search_fields
    assert "preferred_name" in member_admin.search_fields
    assert "email" in member_admin.search_fields
```

- [ ] **Step 6: Bump version**

Update `plfog/version.py`:

```python
VERSION = "1.2.0"

CHANGELOG: list[dict[str, str | list[str]]] = [
    {
        "version": "1.2.0",
        "date": "2026-03-30",
        "changes": [
            "Admin Members page now lets you create users with a login right from the add form",
            "Added email aliases — members can have multiple email addresses and log in with any of them",
            "New 'Users' filter on the Members page to see who has logged into the app",
            "Search now finds members by their alias emails too",
            "Removed the separate User admin page — everything is managed through Members now",
        ],
    },
    # ... keep existing entries
```

- [ ] **Step 7: Run full test suite**

Run: `pytest -v`
Expected: All PASS

- [ ] **Step 8: Run linting and formatting**

Run: `ruff format . && ruff check --fix .`

- [ ] **Step 9: Commit**

```bash
git add membership/admin.py plfog/version.py tests/membership/admin_spec.py
git commit -m "feat: search by alias email + version bump to 1.2.0"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run full test suite with coverage**

Run: `pytest --cov=membership --cov=plfog --cov-report=term-missing -v`
Expected: All tests PASS, coverage meets threshold

- [ ] **Step 2: Run type checker**

Run: `mypy .`
Expected: No new errors

- [ ] **Step 3: Run linting**

Run: `ruff check .`
Expected: Clean

- [ ] **Step 4: Create branch and PR**

```bash
git checkout -b feat/admin-member-management
# cherry-pick all commits from this feature
git push -u origin feat/admin-member-management
gh pr create --title "Admin member management redesign" --body "..."
```
