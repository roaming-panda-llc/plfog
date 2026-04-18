# Guild Leads M2M Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `Guild.guild_lead` FK with a `Member.guild_leaderships` M2M so multiple members can lead the same guild, with assignment UI on the Member admin change page and all leads shown on the hub guild detail page.

**Architecture:** Add `guild_leaderships = ManyToManyField(Guild, ...)` on `Member`; remove `Guild.guild_lead` FK; migrate existing assignments into the junction table. Member admin gets a `filter_horizontal` widget. The hub template loops over `guild.guild_leads.all()` with per-lead modals keyed by `lead.pk`.

**Tech Stack:** Django ORM (ManyToManyField), Django admin `filter_horizontal`, Django migrations (3-op: AddField → RunPython → RemoveField), Django templates (Alpine.js modals), pytest-describe + factory-boy.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `membership/models.py` | Modify | Add `guild_leaderships` M2M on `Member`; remove `guild_lead` FK from `Guild`; update `can_edit_guild()` |
| `membership/migrations/0028_guild_leads_m2m.py` | Create | AddField → RunPython data copy → RemoveField |
| `membership/admin.py` | Modify | Add `filter_horizontal = ["guild_leaderships"]`; add "Guild Leaderships" fieldset |
| `hub/views.py` | Modify | Add `"guild_leads"` to `prefetch_related` in `guild_detail` |
| `templates/hub/guild_detail.html` | Modify | Replace single `guild_lead` block with `{% for lead in guild.guild_leads.all %}` loop and per-lead modals |
| `tests/membership/guild_spec.py` | Modify | Remove old FK tests; add M2M tests |
| `tests/membership/models_spec.py` | Modify | Update two `can_edit_guild` tests to use M2M |
| `tests/hub/guild_edit_spec.py` | Modify | Replace five `GuildFactory(guild_lead=...)` calls with M2M |
| `tests/hub/guild_pages_spec.py` | Modify | Add guild-leads section tests (no leads, singular, plural, all names) |
| `tests/membership/admin_spec.py` | Modify | Add `filter_horizontal` and fieldset tests |
| `scripts/generate_fixture.py` | Modify | Remove `"guild_lead": None` from guild fixture dict |
| `plfog/version.py` | Modify | Bump to 1.6.3; add changelog entry |

---

## Task 1: New M2M model tests (will fail), then model changes + migration

**Files:**
- Write tests: `tests/membership/guild_spec.py`
- Write tests: `tests/membership/models_spec.py`
- Modify: `membership/models.py`
- Create: `membership/migrations/0028_guild_leads_m2m.py`

- [ ] **Step 1: Add new M2M tests to guild_spec.py (these will fail)**

In `tests/membership/guild_spec.py`, add these two tests inside `describe_Guild()`, after the existing `it_has_created_at` test:

```python
def it_supports_multiple_guild_leads():
    member1 = MemberFactory()
    member2 = MemberFactory()
    guild = GuildFactory()
    guild.guild_leads.add(member1, member2)
    assert guild.guild_leads.count() == 2
    assert member1 in guild.guild_leads.all()
    assert member2 in guild.guild_leads.all()

def it_member_can_lead_multiple_guilds():
    member = MemberFactory()
    guild1 = GuildFactory()
    guild2 = GuildFactory()
    member.guild_leaderships.add(guild1, guild2)
    assert member.guild_leaderships.count() == 2
    assert guild1 in member.guild_leaderships.all()
    assert guild2 in member.guild_leaderships.all()
```

- [ ] **Step 2: Add new can_edit_guild tests to models_spec.py (these will fail)**

In `tests/membership/models_spec.py`, inside `describe_can_edit_guild()`, add these after the existing tests:

```python
def it_is_true_for_guild_lead_assigned_via_m2m():
    lead = MemberFactory(fog_role=Member.FogRole.MEMBER)
    guild = GuildFactory()
    guild.guild_leads.add(lead)
    assert lead.can_edit_guild(guild) is True

def it_is_false_when_member_not_in_guild_leads():
    member = MemberFactory(fog_role=Member.FogRole.MEMBER)
    guild = GuildFactory()
    assert member.can_edit_guild(guild) is False
```

- [ ] **Step 3: Run the four new tests to confirm they fail**

```
pytest tests/membership/guild_spec.py::describe_Guild::it_supports_multiple_guild_leads tests/membership/guild_spec.py::describe_Guild::it_member_can_lead_multiple_guilds tests/membership/models_spec.py -k "m2m or not_in_guild_leads" -v
```

Expected: FAIL with `AttributeError: type object 'Guild' has no attribute 'guild_leads'` or similar.

- [ ] **Step 4: Update membership/models.py — add M2M to Member**

In `membership/models.py`, in the `Member` class, add this field after the `leases` GenericRelation:

```python
guild_leaderships = models.ManyToManyField(
    "Guild",
    blank=True,
    related_name="guild_leads",
    help_text="Guilds this member leads.",
)
```

- [ ] **Step 5: Update membership/models.py — remove guild_lead FK from Guild**

In `membership/models.py`, in the `Guild` class, remove these lines entirely:

```python
guild_lead = models.ForeignKey(
    Member,
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="led_guilds",
)
```

- [ ] **Step 6: Update membership/models.py — fix can_edit_guild**

In `membership/models.py`, update `Member.can_edit_guild()`:

```python
def can_edit_guild(self, guild: Guild) -> bool:
    """True when this member may edit the given guild (admin, officer, or that guild's lead)."""
    return self.is_fog_admin or self.is_guild_officer or self.guild_leaderships.filter(pk=guild.pk).exists()
```

- [ ] **Step 7: Create migration 0028**

Create `membership/migrations/0028_guild_leads_m2m.py` with this exact content:

```python
from django.db import migrations, models


def _copy_fk_to_m2m(apps, schema_editor):
    """Copy Guild.guild_lead FK assignments into the new guild_leaderships M2M table."""
    Guild = apps.get_model("membership", "Guild")
    for guild in Guild.objects.exclude(guild_lead__isnull=True):
        guild.guild_leaderships.add(guild.guild_lead_id)


def _restore_fk_from_m2m(apps, schema_editor):
    """Restore Guild.guild_lead from the first entry in guild_leaderships (for reversal)."""
    Guild = apps.get_model("membership", "Guild")
    for guild in Guild.objects.all():
        first_lead = guild.guild_leaderships.first()
        if first_lead is not None:
            guild.guild_lead_id = first_lead.pk
            guild.save(update_fields=["guild_lead"])


class Migration(migrations.Migration):
    dependencies = [
        ("membership", "0027_calendarevent_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="guild_leaderships",
            field=models.ManyToManyField(
                blank=True,
                help_text="Guilds this member leads.",
                related_name="guild_leads",
                to="membership.guild",
            ),
        ),
        migrations.RunPython(
            _copy_fk_to_m2m,
            _restore_fk_from_m2m,
        ),
        migrations.RemoveField(
            model_name="guild",
            name="guild_lead",
        ),
    ]
```

- [ ] **Step 8: Run the four new tests to confirm they now pass**

```
pytest tests/membership/guild_spec.py::describe_Guild::it_supports_multiple_guild_leads tests/membership/guild_spec.py::describe_Guild::it_member_can_lead_multiple_guilds tests/membership/models_spec.py -k "m2m or not_in_guild_leads" -v
```

Expected: PASS for the four new tests. (Other tests using `guild_lead=` will fail — those are fixed in Task 2.)

- [ ] **Step 9: Commit**

```bash
git add membership/models.py membership/migrations/0028_guild_leads_m2m.py tests/membership/guild_spec.py tests/membership/models_spec.py
git commit -m "feat(membership): replace guild_lead FK with guild_leaderships M2M"
```

---

## Task 2: Fix all old tests that used guild_lead= API

**Files:**
- Modify: `tests/membership/guild_spec.py`
- Modify: `tests/membership/models_spec.py`
- Modify: `tests/hub/guild_edit_spec.py`

- [ ] **Step 1: Fix guild_spec.py — replace old FK tests with updated ones**

In `tests/membership/guild_spec.py`, inside `describe_Guild()`, replace:

```python
def it_can_have_guild_lead():
    member = MemberFactory()
    guild = GuildFactory(guild_lead=member)
    assert guild.guild_lead == member

def it_allows_null_guild_lead():
    guild = GuildFactory(guild_lead=None)
    assert guild.guild_lead is None
```

With:

```python
def it_has_no_guild_leads_by_default():
    guild = GuildFactory()
    assert guild.guild_leads.count() == 0
```

- [ ] **Step 2: Fix models_spec.py — update old can_edit_guild tests**

In `tests/membership/models_spec.py`, inside `describe_can_edit_guild()`, replace:

```python
def it_is_true_for_the_guilds_own_lead():
    lead = MemberFactory(fog_role=Member.FogRole.MEMBER)
    guild = GuildFactory(guild_lead=lead)
    assert lead.can_edit_guild(guild) is True

def it_is_false_for_regular_members_other_guilds():
    member = MemberFactory(fog_role=Member.FogRole.MEMBER)
    other_lead = MemberFactory(fog_role=Member.FogRole.MEMBER)
    guild = GuildFactory(guild_lead=other_lead)
    assert member.can_edit_guild(guild) is False
```

With:

```python
def it_is_true_for_the_guilds_own_lead():
    lead = MemberFactory(fog_role=Member.FogRole.MEMBER)
    guild = GuildFactory()
    guild.guild_leads.add(lead)
    assert lead.can_edit_guild(guild) is True

def it_is_false_for_regular_members_other_guilds():
    member = MemberFactory(fog_role=Member.FogRole.MEMBER)
    other_lead = MemberFactory(fog_role=Member.FogRole.MEMBER)
    guild = GuildFactory()
    guild.guild_leads.add(other_lead)
    assert member.can_edit_guild(guild) is False
```

- [ ] **Step 3: Fix guild_edit_spec.py — replace 5 GuildFactory(guild_lead=...) calls**

In `tests/hub/guild_edit_spec.py`, replace each occurrence of `GuildFactory(guild_lead=user.member)` followed by usage. There are 5 tests to update:

**Test: `it_guild_lead_can_create_a_product_for_their_guild`** — replace:
```python
guild = GuildFactory(guild_lead=user.member)
```
with:
```python
guild = GuildFactory()
guild.guild_leads.add(user.member)
```

**Test: `it_allows_the_guild_lead_to_update`** — replace:
```python
guild = GuildFactory(guild_lead=user.member)
```
with:
```python
guild = GuildFactory()
guild.guild_leads.add(user.member)
```

**Test: `it_guild_lead_can_delete_their_products`** — replace:
```python
guild = GuildFactory(guild_lead=user.member)
```
with:
```python
guild = GuildFactory()
guild.guild_leads.add(user.member)
```

**Test: `it_guild_lead_can_edit_their_guild`** — replace:
```python
guild = GuildFactory(guild_lead=user.member, name="Old")
```
with:
```python
guild = GuildFactory(name="Old")
guild.guild_leads.add(user.member)
```

**Test: `it_shows_edit_buttons_for_guild_lead`** — replace:
```python
guild = GuildFactory(guild_lead=user.member)
```
with:
```python
guild = GuildFactory()
guild.guild_leads.add(user.member)
```

- [ ] **Step 4: Run full test suite to confirm clean**

```
pytest tests/membership/ tests/hub/ -v --tb=short -q
```

Expected: All tests pass. Zero failures.

- [ ] **Step 5: Commit**

```bash
git add tests/membership/guild_spec.py tests/membership/models_spec.py tests/hub/guild_edit_spec.py
git commit -m "test(membership): migrate guild_lead= tests to M2M guild_leads"
```

---

## Task 3: Admin widget — filter_horizontal + Guild Leaderships fieldset

**Files:**
- Write test: `tests/membership/admin_spec.py`
- Modify: `membership/admin.py`

- [ ] **Step 1: Write failing admin tests**

In `tests/membership/admin_spec.py`, add these two tests inside `describe_MemberAdmin()`:

```python
def it_includes_guild_leaderships_in_filter_horizontal():
    member_admin = admin.site._registry[Member]
    assert "guild_leaderships" in member_admin.filter_horizontal

@pytest.mark.django_db
def it_shows_guild_leaderships_fieldset_on_edit_form():
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.get("/admin/membership/member/1/change/")
    request.user = User(is_staff=True, is_superuser=True)
    member = MemberFactory()
    member_admin = admin.site._registry[Member]
    fieldsets = member_admin.get_fieldsets(request, obj=member)
    fieldset_titles = [fs[0] for fs in fieldsets]
    assert "Guild Leaderships" in fieldset_titles
```

- [ ] **Step 2: Run the new admin tests to confirm they fail**

```
pytest tests/membership/admin_spec.py -k "guild_leaderships" -v
```

Expected: FAIL — `filter_horizontal` doesn't contain `"guild_leaderships"` yet.

- [ ] **Step 3: Update membership/admin.py — add filter_horizontal**

In `membership/admin.py`, in the `MemberAdmin` class, add after the `readonly_fields` line:

```python
filter_horizontal = ["guild_leaderships"]
```

- [ ] **Step 4: Update membership/admin.py — add Guild Leaderships fieldset**

In `membership/admin.py`, in `MemberAdmin.get_fieldsets()`, the current return statement ends with the `"Notes"` fieldset. Append the new fieldset so the full return reads:

```python
return [
    (
        "Personal Info",
        {
            "fields": personal_fields,
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
    (
        "Guild Leaderships",
        {
            "fields": ["guild_leaderships"],
        },
    ),
]
```

- [ ] **Step 5: Run the new admin tests to confirm they pass**

```
pytest tests/membership/admin_spec.py -k "guild_leaderships" -v
```

Expected: PASS.

- [ ] **Step 6: Run the full admin spec to confirm nothing broke**

```
pytest tests/membership/admin_spec.py -v --tb=short
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add membership/admin.py tests/membership/admin_spec.py
git commit -m "feat(admin): add Guild Leaderships filter_horizontal widget to Member admin"
```

---

## Task 4: Hub template — prefetch + loop over guild leads

**Files:**
- Write tests: `tests/hub/guild_pages_spec.py`
- Modify: `hub/views.py`
- Modify: `templates/hub/guild_detail.html`

- [ ] **Step 1: Write failing hub template tests**

In `tests/hub/guild_pages_spec.py`, add a new `describe_guild_leads_section()` block inside `describe_guild_detail()`:

```python
def describe_guild_leads_section():
    def it_hides_leads_section_when_no_leads(client: Client):
        User.objects.create_user(username="v_nolead", password="pass")
        guild = GuildFactory()
        client.login(username="v_nolead", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert response.status_code == 200
        assert b'hub-detail-label">Guild Lead' not in response.content

    def it_shows_singular_heading_with_one_lead(client: Client):
        MembershipPlanFactory()
        lead_user = User.objects.create_user(username="lead_sing", password="pass")
        lead_user.member.preferred_name = "Solo Lead"
        lead_user.member.save(update_fields=["preferred_name"])
        guild = GuildFactory()
        guild.guild_leads.add(lead_user.member)
        User.objects.create_user(username="viewer_sing", password="pass")
        client.login(username="viewer_sing", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Guild Lead</h3>" in response.content
        assert b"Guild Leads</h3>" not in response.content
        assert b"Solo Lead" in response.content

    def it_shows_plural_heading_with_multiple_leads(client: Client):
        MembershipPlanFactory()
        lead1 = User.objects.create_user(username="lead_pl1", password="pass")
        lead2 = User.objects.create_user(username="lead_pl2", password="pass")
        guild = GuildFactory()
        guild.guild_leads.add(lead1.member, lead2.member)
        User.objects.create_user(username="viewer_pl", password="pass")
        client.login(username="viewer_pl", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Guild Leads</h3>" in response.content

    def it_shows_all_lead_names_in_the_section(client: Client):
        MembershipPlanFactory()
        lead1 = User.objects.create_user(username="lead_names1", password="pass")
        lead1.member.preferred_name = "Alice"
        lead1.member.save(update_fields=["preferred_name"])
        lead2 = User.objects.create_user(username="lead_names2", password="pass")
        lead2.member.preferred_name = "Bob"
        lead2.member.save(update_fields=["preferred_name"])
        guild = GuildFactory()
        guild.guild_leads.add(lead1.member, lead2.member)
        User.objects.create_user(username="viewer_names", password="pass")
        client.login(username="viewer_names", password="pass")
        response = client.get(f"/guilds/{guild.pk}/")
        assert b"Alice" in response.content
        assert b"Bob" in response.content
```

- [ ] **Step 2: Run these tests to confirm they fail**

```
pytest tests/hub/guild_pages_spec.py -k "guild_leads_section" -v
```

Expected: FAIL — the template still uses `guild.guild_lead` (singular FK), which no longer exists, so the `{% if guild.guild_lead %}` block is always falsy and tests expecting "Guild Lead" headings fail.

- [ ] **Step 3: Update hub/views.py — add guild_leads prefetch**

In `hub/views.py`, in the `guild_detail` view, change:

```python
guild = get_object_or_404(
    Guild.objects.prefetch_related("products__splits__guild"),
    pk=pk,
)
```

to:

```python
guild = get_object_or_404(
    Guild.objects.prefetch_related("products__splits__guild", "guild_leads"),
    pk=pk,
)
```

- [ ] **Step 4: Replace the guild lead block in templates/hub/guild_detail.html**

In `templates/hub/guild_detail.html`, replace lines 30–107 (the entire `{% if guild.guild_lead %}...{% endif %}` block — from `{% if guild.guild_lead %}` through the closing `{% endif %}` before `</div>`):

```django
    {% with leads=guild.guild_leads.all %}
    {% if leads %}
    <div class="hub-detail-section">
        <h3 class="hub-detail-label">Guild Lead{% if leads|length > 1 %}s{% endif %}</h3>
        {% for lead in leads %}
        <div class="hub-member-row" style="cursor:pointer;" @click="$dispatch('open-modal', 'guild-lead-profile-{{ lead.pk }}')">
            <div class="hub-member-avatar">
                {{ lead.display_name|make_list|first|upper }}
            </div>
            <div class="hub-member-info">
                <span class="hub-member-name">{{ lead.display_name }}</span>
                <span class="hub-badge">Lead</span>
            </div>
        </div>
        {% endfor %}
    </div>

    {% for lead in leads %}
    <div x-data="{ open: false }"
         x-show="open"
         x-transition:enter="modal-enter"
         x-transition:leave="modal-leave"
         @open-modal.window="if ($event.detail === 'guild-lead-profile-{{ lead.pk }}') open = true"
         @close-modal.window="if ($event.detail === 'guild-lead-profile-{{ lead.pk }}') open = false"
         @keydown.escape.window="open = false"
         class="pl-modal-backdrop"
         style="display: none;"
         role="dialog"
         aria-modal="true">
        <div class="pl-modal pl-modal--sm" @click.outside="open = false">
            <div class="pl-modal__header">
                <h2 class="pl-modal__title">{{ lead.display_name }}</h2>
                <button type="button" @click="open = false" class="pl-modal__close" aria-label="Close">&times;</button>
            </div>
            <div class="pl-modal__body">
                {% if lead.show_in_directory %}
                <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1.25rem;">
                    <div class="hub-member-avatar" style="width:48px;height:48px;font-size:1.25rem;">
                        {{ lead.display_name|make_list|first|upper }}
                    </div>
                    <div>
                        <div style="font-weight:600;color:var(--hub-text, #F4EFDD);">{{ lead.display_name }}</div>
                        {% if lead.pronouns and lead.pronouns != "prefer not to share" %}
                        <div style="font-size:0.8125rem;color:var(--hub-text-muted, #96ACBB);">{{ lead.pronouns }}</div>
                        {% endif %}
                    </div>
                </div>
                {% if lead.about_me %}
                <p style="font-size:0.875rem;color:var(--hub-text, #F4EFDD);margin:0 0 1rem;">{{ lead.about_me }}</p>
                {% endif %}
                {% if lead.primary_email or lead.phone or lead.discord_handle %}
                <div style="display:flex;flex-direction:column;gap:0.5rem;">
                    {% if lead.primary_email %}
                    <div style="display:flex;gap:0.5rem;font-size:0.875rem;">
                        <span style="color:var(--hub-text-muted, #96ACBB);min-width:60px;">Email</span>
                        <a href="mailto:{{ lead.primary_email }}" style="color:var(--color-tuscan-yellow, #EEB44B);">{{ lead.primary_email }}</a>
                    </div>
                    {% endif %}
                    {% if lead.phone %}
                    <div style="display:flex;gap:0.5rem;font-size:0.875rem;">
                        <span style="color:var(--hub-text-muted, #96ACBB);min-width:60px;">Phone</span>
                        <span style="color:var(--hub-text, #F4EFDD);">{{ lead.phone }}</span>
                    </div>
                    {% endif %}
                    {% if lead.discord_handle %}
                    <div style="display:flex;gap:0.5rem;font-size:0.875rem;">
                        <span style="color:var(--hub-text-muted, #96ACBB);min-width:60px;">Discord</span>
                        <span style="color:var(--hub-text, #F4EFDD);">{{ lead.discord_handle }}</span>
                    </div>
                    {% endif %}
                </div>
                {% endif %}
                {% else %}
                <p style="font-size:0.875rem;color:var(--hub-text-muted, #96ACBB);margin:0;">
                    This member has chosen to keep their profile private. Their information is not listed in the member directory.
                </p>
                {% endif %}
            </div>
        </div>
    </div>
    {% endfor %}
    {% endif %}
    {% endwith %}
```

- [ ] **Step 5: Run the new hub tests to confirm they pass**

```
pytest tests/hub/guild_pages_spec.py -k "guild_leads_section" -v
```

Expected: PASS.

- [ ] **Step 6: Run the full hub test suite**

```
pytest tests/hub/ -v --tb=short -q
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add hub/views.py templates/hub/guild_detail.html tests/hub/guild_pages_spec.py
git commit -m "feat(hub): show all guild leads on guild detail page"
```

---

## Task 5: Script cleanup + version bump

**Files:**
- Modify: `scripts/generate_fixture.py`
- Modify: `plfog/version.py`

- [ ] **Step 1: Remove guild_lead from fixture script**

In `scripts/generate_fixture.py`, at line ~652, inside the guild fixture `"fields"` dict, remove the `"guild_lead": None,` line. The guild fields dict should become:

```python
"fields": {
    "name": guild_name,
    "notes": "",
    "created_at": CREATED_AT,
},
```

- [ ] **Step 2: Bump version and add changelog entry**

In `plfog/version.py`, change `VERSION = "1.6.2"` to `VERSION = "1.6.3"` and prepend a new entry to the `CHANGELOG` list:

```python
{
    "version": "1.6.3",
    "date": "2026-04-16",
    "title": "Multiple Guild Leads",
    "changes": [
        "Guilds can now have multiple leads — if your guild has more than one person running it, they all show up on the guild page",
        "Admins can assign guild leads directly from the member record in the admin panel — just search for guilds in the new Guild Leaderships section",
        "The guild page now shows a card for each lead, with their name, pronouns, and contact info if they've made their profile public",
    ],
},
```

- [ ] **Step 3: Run the full test suite one final time**

```
pytest --tb=short -q
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_fixture.py plfog/version.py
git commit -m "release: 1.6.3 — multiple guild leads"
```
