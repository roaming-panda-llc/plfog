# Admin Member Management Redesign

**Date:** 2026-03-30
**Status:** Approved

## Problem

Managing users and members requires shell access to the production database. The admin Members page doesn't support creating users, and the relationship between Users and Members is confusing. Employees with multiple email addresses (e.g., `lee@pastlives.space` and `leemendelsohn@gmail.com`) can't log in with all their emails.

## Design

### Admin "Members" Page

The existing Member admin page becomes the single user/member management interface. The Django User admin is hidden from the sidebar.

**List view:**

- **Toggle filter** at the top: "All Members" | "Users"
  - "Users" shows only members with a linked User (`user__isnull=False`)
  - Tooltip on "Users": *"Users are members who have logged into this web app"*
- **Columns:** Name, Primary Email, Member Type, FOG Role, Status, Last Login
- **Search:** by name or any email address
- **Filters:** status (default: active), member_type, fog_role

**Add Member form (no login):**

Creates a Member record only. The member gets a User automatically when they first log in.

- Full legal name (required)
- Primary email (required)
- Member type (default: standard)
- FOG role (superuser-only field, default: member)
- Status (default: active)
- Membership plan

**Add User + Member form:**

A checkbox "Create login immediately" on the add form. When checked, creates both a User and Member in one step. This is for cases like onboarding an employee who needs access right now.

**Edit form:**

- **Personal Info:** name, preferred name, pronouns, phone, billing name
- **Email Aliases (inline):** add/remove email addresses, mark one as primary. All addresses work for login. For members without a User, the primary email is stored on `Member.email`. For members with a User, emails sync to allauth's `EmailAddress` model.
- **Membership:** plan, status, member_type, fog_role (superuser-only), join_date, cancellation_date, committed_until
- **Emergency Contact:** name, phone, relationship
- **Notes**

### Email Alias Handling

allauth already has an `EmailAddress` model supporting multiple emails per user. We use this for members with Users.

For members without Users (no login yet), we store additional emails in a new `MemberEmail` model:

```python
class MemberEmail(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="emails")
    email = models.EmailField(unique=True, help_text="An email address for this member.")
    is_primary = models.BooleanField(default=False, help_text="Primary email shown in lists.")
```

When a User is created for a member (on first login or via admin), all `MemberEmail` records get migrated to allauth `EmailAddress` records.

### Login Flow Changes

The existing `AutoCreateUserLoginCodeForm` currently matches only on `Member.email`. Updated behavior:

1. User enters email on login page.
2. Check if a `User` exists with this email (via allauth `EmailAddress` table) → send login code.
3. If no User, check `MemberEmail` for a matching record → auto-create User, migrate all that member's emails to allauth `EmailAddress`, link Member → send login code.
4. Fallback: check `Member.email` directly (backwards compat during migration) → same auto-create flow.
5. No match anywhere → behavior depends on registration mode (open vs invite-only).

### Signal Changes

The `ensure_user_has_member` signal stays but is simplified:
- On User creation, check for a Member with matching email (via `MemberEmail` or `Member.email`).
- If found, link it. Migrate `MemberEmail` records to allauth `EmailAddress`.
- If not found, create a new Member (current behavior for open registration).

### Hidden Admin Pages

- Django's default `User` admin: **unregistered** from admin site.
- `EmailAddress` admin (allauth): **unregistered** — managed through Member edit inline instead.

## What This Does NOT Change

- The hub Member Directory page (`/members/`) — untouched.
- The hub profile settings page — untouched.
- Airtable sync — continues creating Member records without Users as before.
- Invite flow — continues working, invites create Members that get linked on first login.

## Models

**New model:** `MemberEmail` — stores email aliases for members who don't have Users yet. Once a User is created, these migrate to allauth's `EmailAddress`.

**Unchanged:** `Member.email` stays as the primary email field on the model. It's used everywhere (Airtable sync, display, search) and remains the source of truth for the member's main email. `MemberEmail` stores *additional* aliases only. Login and search check both `Member.email` and `MemberEmail.email`.

## Migration Plan

1. Create `MemberEmail` model.
2. For existing members with Users who have multiple allauth `EmailAddress` records — no migration needed, allauth already handles this.
3. No data backfill required. `MemberEmail` starts empty and gets populated as admins add aliases.

## Testing

- Admin list view: toggle between All Members and Users filter
- Add Member without user → verify no User created
- Add Member with "Create login immediately" → verify both created and linked
- Edit member: add/remove email aliases
- Login with primary email → works
- Login with alias email → works, same User
- Search members by alias email in admin
- Tooltip shows on Users filter
