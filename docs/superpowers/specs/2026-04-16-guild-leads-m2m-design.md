# Guild Leads M2M — Design Spec
**Version:** 1.6.3
**Date:** 2026-04-16

## Overview

Replace the single `Guild.guild_lead` ForeignKey with a many-to-many relationship so multiple members can lead the same guild. The assignment UI lives on the Member admin change page. The hub guild detail page is updated to display all leads.

---

## 1. Data Model

### Remove
`Guild.guild_lead = ForeignKey(Member, null=True, blank=True, on_delete=SET_NULL, related_name="led_guilds")`

### Add
```python
# On Member model
guild_leaderships = models.ManyToManyField(
    "Guild",
    blank=True,
    related_name="guild_leads",
    help_text="Guilds this member leads.",
)
```

Django auto-creates the junction table `membership_member_guild_leaderships (member_id, guild_id)`.

### Migration sequence (single migration file)
1. Add `Member.guild_leaderships` M2M field
2. Data migration: for each `Guild` where `guild_lead_id` is not null, insert a row into the new junction table
3. Remove `Guild.guild_lead` FK

### `can_edit_guild` update
```python
# Before
return self.is_fog_admin or self.is_guild_officer or guild.guild_lead_id == self.pk

# After
return self.is_fog_admin or self.is_guild_officer or self.guild_leaderships.filter(pk=guild.pk).exists()
```

---

## 2. Member Admin Change Page

Add a "Guild Leaderships" fieldset to `MemberAdmin` using Django's built-in `filter_horizontal` widget.

```python
class MemberAdmin(ModelAdmin):
    filter_horizontal = ["guild_leaderships"]

    def get_fieldsets(self, ...):
        # ... existing fieldsets ...
        # Append at the bottom:
        (
            "Guild Leaderships",
            {"fields": ["guild_leaderships"]},
        ),
```

No custom form code needed — `guild_leaderships` is a standard M2M on `Member` so Django admin renders it natively as a dual-list widget with search.

---

## 3. Hub Guild Detail Template

### View (`hub/views.py`)
Add `prefetch_related("guild_leads")` to the guild queryset in `guild_detail` to avoid N+1 queries.

### Template (`templates/hub/guild_detail.html`)
Replace single-lead block:
```django
{% if guild.guild_lead %} ... {{ guild.guild_lead.display_name }} ... {% endif %}
```

With a loop:
```django
{% with leads=guild.guild_leads.all %}
{% if leads %}
  <h3>Guild Lead{% if leads|length > 1 %}s{% endif %}</h3>
  {% for lead in leads %}
    {# existing profile card content, replacing guild.guild_lead with lead #}
  {% endfor %}
{% endif %}
{% endwith %}
```

---

## 4. Tests

All existing tests that use `GuildFactory(guild_lead=member)` must be updated:
- Replace with `guild = GuildFactory(); guild.guild_leads.add(member)`
- Or add a `guild_leads` post-generation hook to `GuildFactory`

`can_edit_guild` tests updated to use the new M2M approach.

New tests cover:
- A guild with zero leads shows no lead section
- A guild with one lead shows "Guild Lead"
- A guild with multiple leads shows "Guild Leads" (plural)
- `can_edit_guild` returns True when the member is in `guild_leaderships`
- Member admin fieldset renders `guild_leaderships`

---

## 5. Out of Scope

- GuildEditForm on the hub page (name/about/calendar) — no changes needed
- Airtable sync — `guild_lead` in `airtable_sync/config.py` refers to `member_type`, not the FK; no sync changes needed
- Guild admin (Guild is excluded from Django admin since v1.6.0)
