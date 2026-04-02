# Payments Dashboard Redesign

**Date:** 2026-04-02
**Status:** Approved

## Problem

The existing Payments Dashboard (`/admin/billing/dashboard/`) has two bugs and a structural problem:

- **White-on-white cards** — stat cards use `var(--body-bg, #fff)` as background with no explicit text color, making them unreadable.
- **No header padding** — the page hits the top of the viewport with no breathing room.
- **Fragmented navigation** — billing data is spread across six separate sidebar links (Payments Dashboard, Tabs, Tab Entries, Tab Charges, Billing Settings, Stripe Accounts, Products). There is no unified place to manage billing.

## Solution

Replace the single-page dashboard with a **five-tab dashboard** at the same URL. All billing administration lives in one page. Styled identically to the Voting Dashboard (`#092E4C` cards, `#EEB44B` accent, `pl-*` CSS classes).

Tab state is persisted in the URL hash (`#overview`, `#open-tabs`, `#history`, `#settings`, `#stripe`) so page refreshes preserve the active tab.

---

## Tab 1 — Overview

**Purpose:** At-a-glance billing health. Landing tab.

**Stats row** (four `.pl-stat` cards):
- Total Outstanding — sum of all pending tab entry amounts
- Collected This Month — sum of succeeded `TabCharge` amounts since month start
- Failed Charges — count of `TabCharge` records with `status=failed`
- Locked Tabs — count of `Tab` records with `is_locked=True`

**Outstanding Tabs table** (`.pl-table`): Member name (links to Tab Detail Modal), Balance, Payment Method indicator, Locked status. Only tabs with `current_balance > 0`.

**Failed Charges table** (`.pl-table`): Member name, Amount, Failure reason (truncated), Retry count, Date. Last 20 failed charges.

**Actions:**
- `+ Add Charge` button — opens the Add Charge modal (inline, does not navigate away).

---

## Tab 2 — Open Tabs

**Purpose:** View and act on member tabs. Look up any member's current tab state.

**Toolbar:**
- Filter chips: **Outstanding** (balance > $0, default), **All Members**, **Failed Charges** (tabs with ≥1 failed charge)
- Member search input — filters the table client-side by member name

**Table columns:** Member, Balance, Limit, Payment Method, Status badge (Active / No Payment Method / Locked)

**Tab Detail Modal** (opens on row click):
- Header: member name + guild
- Three stat pills: Outstanding balance, Tab limit, Payment method (card brand + last 4)
- **Pending Entries** table: Description, Guild, Date, Amount. Voided entries shown struck-through.
- **Charge History** table: Billing run label, Amount, Status (succeeded/failed), Date
- Footer actions: `+ Add Charge`, `Lock Tab` / `Unlock Tab` (toggled based on current state)

---

## Tab 3 — History

**Purpose:** Cross-member view of all `TabCharge` records. Identify failures, track billing runs, access receipts.

**Stats row** (three cards, scoped to current calendar month):
- Collected This Month
- Failed This Month
- Success Rate %

**Toolbar:**
- Filter chips: **All** (default), **Succeeded**, **Failed**, **Needs Retry**
- Member search input

**Table columns:** Member (clicking opens Tab Detail Modal), Amount, Guild / Stripe Account, Status badge, Retry count, Date, Action (Receipt link → Stripe-hosted URL for succeeded; Retry button for failed/needs-retry)

**Retry action:** POSTs to a new `billing_admin_retry_charge` view. On success, updates the row status in place.

---

## Tab 4 — Settings

**Purpose:** Edit `BillingSettings` (the singleton) inline without leaving the dashboard.

**Form fields:**
- Charge Frequency — select: Daily / Weekly / Monthly / Off
- Charge Time — time input (Pacific)
- Day of Week — shown only when Frequency = Weekly (0=Monday … 6=Sunday)
- Day of Month — shown only when Frequency = Monthly (1–28)
- Default Tab Limit — decimal input ($)
- Max Retry Attempts — integer input
- Retry Interval Hours — integer input

**Behavior:** Save button POSTs to `billing_admin_save_settings`. On success, Django messages framework shows a success notice; page stays on Settings tab (redirect to `#settings`). Conditional field visibility handled with vanilla JS (show/hide Day of Week and Day of Month based on selected frequency).

---

## Tab 5 — Stripe

**Purpose:** Manage Stripe Connect accounts and the product catalog.

**Section 1 — Connected Accounts:**
Table of `StripeAccount` records: Display Name, Guild, Stripe Account ID (truncated), Platform Fee %, Active status, Connected date.
- `Connect Stripe Account` button → triggers existing `initiate_connect` OAuth flow.
- Row links to standard Django admin change page for editing.

**Section 2 — Products:**
Table of `Product` records: Name, Guild, Price, Active status.
- `+ Add Product` button → opens an Add Product modal with fields: Name, Guild (select), Price, Active toggle.
- Row links to standard Django admin change page for editing.

---

## Add Charge Modal

Shared modal used from Overview and Open Tabs. Contains the existing `AdminAddTabEntryForm`: Member (select, active only), Product (optional select — auto-fills description and amount), Description, Amount. Submits to `billing_admin_add_entry` via POST; on success, closes modal and refreshes the current tab's data.

---

## Sidebar Changes

The Unfold sidebar **Billing** section keeps `Payments Dashboard` as the primary link. Individual model links (Tabs, Tab Entries, Tab Charges, Billing Settings, Stripe Accounts, Products) remain in the sidebar as fallbacks for direct model access but are not removed.

---

## Implementation Scope

### New / changed files

| File | Change |
|------|--------|
| `templates/billing/admin_dashboard.html` | Full replacement — implements the five-tab layout |
| `billing/views.py` | Expand `admin_tab_dashboard` context; add `billing_admin_save_settings`; add `billing_admin_retry_charge` |
| `billing/urls.py` | Add two new URL patterns: `admin/save-settings/` and `admin/retry-charge/<pk>/` |

### No changes needed

- Models — no new fields or migrations
- `billing/forms.py` — `AdminAddTabEntryForm` reused as-is
- `billing/admin.py` — unchanged
- Sidebar settings in `plfog/settings.py` — unchanged

### Data sourced in one view call

`admin_tab_dashboard` computes all context in a single view:
- Overview stats (4 aggregates)
- Outstanding tabs queryset
- Failed charges queryset (last 20)
- All tabs queryset (for Open Tabs, pre-filtered server-side based on `?filter=` query param)
- History charges queryset (all `TabCharge` records, filtered by `?status=`)
- `BillingSettings` singleton (for Settings tab form)
- `StripeAccount` queryset
- `Product` queryset

Tab filtering (Outstanding / All Members / Failed Charges on Open Tabs; All / Succeeded / Failed / Needs Retry on History) is handled server-side via query parameters, not client-side JavaScript, so the page works without JS for the core filtering. Tab switching itself uses JS for the hash-based navigation.

---

## Visual Style

All components follow the Voting Dashboard pattern:

| Token | Value |
|-------|-------|
| Card background | `#092E4C` |
| Accent / stat values | `#EEB44B` |
| Body text | `#F4EFDD` |
| Muted text | `#96ACBB` |
| Row separator | `rgba(255,255,255,0.04)` |
| Section border | `rgba(255,255,255,0.08)` |

CSS class prefix: `pl-` (reuses existing classes from `admin/index.html` where possible, adds billing-specific variants).
