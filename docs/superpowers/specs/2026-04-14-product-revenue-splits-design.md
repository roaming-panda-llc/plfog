# Product Revenue Splits — Design

**Date:** 2026-04-14
**Status:** Draft, awaiting user review
**Scope:** Replace the Add Product modal with an inline form, drop the active/inactive flag, and replace the current single-recipient + admin-percent split system with a flexible N-recipient revenue split.

---

## Goals

- A product's revenue can be split across an arbitrary list of recipients, where each recipient is either **Admin** or a specific **Guild**, and the percentages must sum to exactly 100%.
- The Add Product UI is an inline form on the guild admin edit page, not a modal.
- Products are either present (active) or deleted (gone). No active/inactive flag.
- Reports continue to show recipient breakdowns per entry; a live preview on the form prevents user mistakes.

## Non-Goals

- No Stripe Connect / destination charges. All money still settles to the single platform Stripe account; splits are accounting-only and used for reporting and manual payout.
- No edit-in-place for existing products in v1. To change a product, delete it and re-add.
- No member-facing change to the My Tab or charge history pages. Members see totals, not splits.

## Decisions Locked During Brainstorming

| # | Question | Answer |
|---|---|---|
| 1 | Form location | Same guild admin edit page, inline form below product list, always visible (no modal) |
| 2 | Status field | Removed. Product exists = available. Delete = gone. No soft-delete. |
| 3 | Existing data | **B2 — wipe products and past tab entries/charges.** Clean slate. Operator backs up DB first. |
| 4 | Reports impact | Same row shape as today (one row per recipient), plus a live preview on the form. |
| Data model | Approach | **Approach 1 — related table.** Symmetrical: Admin is just a recipient row with `guild=NULL`. |

---

## Data Model

### `Product` (modified)

Drop fields:
- `admin_percent_override`
- `split_mode`
- `is_active`

Keep fields:
- `name` (CharField)
- `price` (Decimal(8,2), > 0)
- `guild` (FK Guild — the "owning" guild whose admin page hosts the product)
- `created_by` (FK User, nullable)
- `created_at` (auto)

Drop the `Product.SplitMode` `TextChoices` enum entirely.

### `ProductRevenueSplit` (new)

| field | type | notes |
|---|---|---|
| `product` | FK Product, on_delete=CASCADE | parent |
| `recipient_type` | CharField, TextChoices `ADMIN` / `GUILD` | which kind of recipient |
| `guild` | FK Guild, nullable, on_delete=PROTECT | required iff `recipient_type=GUILD`; must be NULL iff `ADMIN` |
| `percent` | Decimal(5,2) | DB CHECK: `percent > 0 AND percent <= 100` |

Constraints (Meta):
- Two partial unique constraints (Postgres treats NULLs as distinct in plain `UNIQUE`, so we need conditional uniqueness):
  - `UniqueConstraint(fields=["product"], condition=Q(recipient_type="ADMIN"), name="uq_productrevenuesplit_admin_per_product")` — at most one Admin row per product.
  - `UniqueConstraint(fields=["product", "guild"], condition=Q(recipient_type="GUILD"), name="uq_productrevenuesplit_guild_per_product")` — at most one row per (product, guild).
- `CheckConstraint` enforcing `(recipient_type='GUILD' AND guild IS NOT NULL) OR (recipient_type='ADMIN' AND guild IS NULL)`.
- Cross-row sum-to-100 is **not** a DB constraint (cross-row checks are not portable). Enforced in `ProductForm.clean()`.

### `TabEntry` (modified)

Drop snapshot fields:
- `admin_percent`
- `split_mode`
- `guild`
- `split_guild_ids`

Keep all other fields (`tab`, `amount`, `description`, `product`, `voided_at`, `voided_by`, `voided_reason`, `tab_charge`).

### `TabEntrySplit` (new) — frozen snapshot

| field | type | notes |
|---|---|---|
| `entry` | FK TabEntry, on_delete=CASCADE | parent |
| `recipient_type` | TextChoices `ADMIN` / `GUILD` | snapshot |
| `guild` | FK Guild, nullable, on_delete=PROTECT | snapshot — PROTECT prevents deleting a guild with historical splits |
| `percent` | Decimal(5,2) | snapshot of percent at entry creation |
| `amount` | Decimal(8,2) | computed dollar amount, see rounding rule |

Constraints: same Check (recipient_type ↔ guild presence) as ProductRevenueSplit. No uniqueness on `(entry, recipient_type, guild)` because the design tolerates duplicates if a product split was edited mid-life — though in practice with v1 (no edit-in-place) duplicates won't occur.

### Penny-rounding rule

Compute each split's amount as `quantize(entry.amount * percent / 100, '0.01', ROUND_HALF_UP)`. Then the row with the largest `percent` absorbs the ±1¢ remainder so that `sum(splits.amount) == entry.amount` exactly. Tie-break on largest percent: lowest `id` (deterministic).

This is implemented in `TabEntry.snapshot_splits(splits)` and asserted at the end of the method.

---

## Charge Flow

### Entry creation

`Tab.add_entry()` and the admin "Add tab item" view both:

1. Wrap in `transaction.atomic()` with `select_for_update()` on the tab (existing pattern).
2. Resolve the splits source:
   - If `entry.product` is set → splits = `list(product.splits.all())` (ordered by id).
   - If no product (custom/manual entry) → splits = the recipient/percent rows submitted on the form.
3. Call `entry.snapshot_splits(splits)`:
   - Computes per-row amount with the rounding rule above.
   - Bulk-creates `TabEntrySplit` rows.
   - Asserts `sum(amount) == entry.amount`.

### `compute_splits()` deletion

The old `TabEntry.compute_splits()` method, the `EntrySplit` dataclass, and any code that recomputes splits at read time are deleted. Reports SELECT directly from `TabEntrySplit`.

### Stripe charge — unchanged

`TabCharge.execute_stripe_charge()` continues to create one PaymentIntent for the full charge total on the platform Stripe account. No Stripe Connect, no per-recipient transfers. Splits are accounting-only.

### Voids — unchanged

`TabEntry.voided_at` is set on void. Reports filter out voided entries before aggregating splits (same behaviour as today).

---

## UI

### Layout (guild admin edit page)

The current Alpine modal is replaced by an always-visible inline form below the existing product table:

```
┌─ Products ──────────────────────────────────────────────┐
│ [existing product table — name | price | splits | del]  │
│                                                          │
│ ─── Add a product ───                                    │
│ Name:  [_____________]   Price: $[______]                │
│                                                          │
│ Revenue Split — must sum to 100%                         │
│ ┌─────────────────────────┬────────────┬───┐            │
│ │ Recipient               │ Percent    │   │            │
│ ├─────────────────────────┼────────────┼───┤            │
│ │ Admin             ▼     │ [  20  ] % │ ✕ │            │
│ │ Ceramics Guild    ▼     │ [  80  ] % │ ✕ │            │
│ └─────────────────────────┴────────────┴───┘            │
│ [+ Add recipient]                                        │
│                                                          │
│ Live preview: $10.00 → Admin $2.00, Ceramics $8.00       │
│ Total: 100% ✓                                            │
│                                                          │
│ [ Save Product ]   [ Cancel ]                            │
└──────────────────────────────────────────────────────────┘
```

### Defaults on a fresh form

- Two split rows: `Admin / 20%` and `<this guild> / 80%`
- Both removable; user can re-add Admin from the recipient dropdown if removed.

### Recipient dropdown

- Options: `Admin` plus every `Guild` row in the system.
- Already-picked recipients are disabled in other rows' dropdowns (prevents duplicates client-side; server validates too).

### Alpine.js behaviour

- `+ Add recipient` appends a row pre-selecting the first un-picked recipient.
- `✕` removes the row.
- Sum + live preview recompute on percent change (`x-effect` watching the splits array).
- Total badge: green `✓` at exactly 100%, red `✗` otherwise.
- Save button disabled unless: name filled, price > 0, total = 100%, ≥1 row.

### Cancel button

Clears the form back to defaults. No navigation.

### Existing product rows in the table

Show a compact split summary in the splits column (e.g. "Admin 20% · Ceramics 80%"). Delete is the only action in v1 — no inline edit.

### Server-side form

- `ProductForm` (ModelForm) for the product fields.
- `ProductRevenueSplitFormSet = inlineformset_factory(Product, ProductRevenueSplit, ...)` for the splits, `min_num=1`.
- `ProductForm.clean()` validates the formset together: ≥1 split, sum == 100, no duplicate recipients, recipient_type ↔ guild rules.
- Errors: form-level (sum, duplicates) at form bottom; field-level inline.

### Custom entries (admin "Add tab item" form)

- Same dynamic recipient/% rows.
- Default: `Admin 20% / <selected guild> 80%` if a guild context exists, else `Admin 100%`.

---

## Reports & Charge Views

### Reports page (`/billing/admin/...reports`)

- Same row shape as today: one row per `TabEntrySplit`.
- Columns: date, member, description, recipient (Admin or guild name), recipient %, recipient $, charge status.
- Payout summary at bottom: totals grouped by recipient (Admin row plus one row per guild).
- Filters: date range, recipient (replaces today's "guild" filter; Admin selectable), charge type, status.
- CSV export updated to match.

Implementation: replace `entry.compute_splits()` calls with `TabEntrySplit.objects.select_related('entry__tab__member', 'guild')` filtered by date/etc.

### My Tab (member-facing)

Unchanged. Members see entries with description and amount; no split breakdown.

### Charge history

Members: unchanged.
Admin charge detail (if present): add a "Where it went" block listing recipient breakdown for that charge (sum of all child entries' splits, grouped by recipient).

### Guild detail page (`/guilds/<pk>/`)

Product list shows each product with its split summary visible (e.g. "Ceramics Mug — $10 · Admin 20% / Ceramics 80%"). Lets members see how their purchase is divided.

---

## Validation Rules (Canonical List)

Applies to both `ProductRevenueSplitFormSet` (product form) and the equivalent splits formset on the custom-entry form:

1. ≥1 split row.
2. Sum of all `percent` values == 100 exactly (Decimal equality, no float).
3. Each `recipient_type=GUILD` row has a non-null guild.
4. Each `recipient_type=ADMIN` row has `guild=None`.
5. No duplicate `(recipient_type, guild)` tuples — at most one Admin row, at most one row per guild.
6. Each `percent` in the open-closed interval `(0, 100]`.

Form-level errors (sum, duplicates) render at the form bottom. Field-level errors (missing guild, bad percent) render inline next to the offending field.

---

## Migration & Data Wipe

One PR, one chain of migrations:

1. Create `ProductRevenueSplit` and `TabEntrySplit` tables.
2. Data migration: `Product.objects.all().delete()`, `TabEntry.objects.all().delete()`, `TabCharge.objects.all().delete()`. Reverse function: no-op with explicit comment that this migration is irreversible by design (data is gone). Migration docstring explicitly notes this is destructive and assumes operator has backed up the DB.
3. Drop fields: `Product.admin_percent_override`, `Product.split_mode`, `Product.is_active`, `TabEntry.admin_percent`, `TabEntry.split_mode`, `TabEntry.guild`, `TabEntry.split_guild_ids`.
4. Code deletion in the same PR: `Product.SplitMode` enum, `TabEntry.compute_splits()`, `EntrySplit` dataclass.

**Manual pre-deploy step:** back up the production database. Documented in the PR description.

**Stripe note:** wiping `TabCharge` rows removes the local bookkeeping only. Real Stripe charges that already settled remain settled in Stripe. Operator is aware (confirmed during brainstorming).

---

## Testing

BDD specs (pytest-describe), `*_spec.py` per project convention:

- `billing/spec/models/product_revenue_split_spec.py` — model invariants, the recipient_type ↔ guild check constraint, uniqueness constraint.
- `billing/spec/models/tab_entry_split_spec.py` — `snapshot_splits()` rounding rule. Cases: $0.01 split 50/50, $0.03 split three ways (1¢/1¢/1¢), $99.99 split 33/33/34, large $1000 split 20/30/50, single-recipient 100%. Sum-equals-amount invariant in every case.
- `billing/spec/forms/product_form_spec.py` — sum-to-100 (pass and fail), duplicate-recipient detection, default-row generation, recipient_type/guild combinations, empty-formset rejection.
- `billing/spec/views/guild_admin_product_form_spec.py` — inline form on guild edit page renders with defaults; valid POST creates product + splits in one transaction; invalid POST re-renders with errors and preserves user input.
- `billing/spec/reports_spec.py` — report rows match `TabEntrySplit` rows; payout summary aggregates correctly per recipient (Admin and per guild); voided entries excluded.
- `hub/spec/views/guild_detail_spec.py` — split summary visible on product cards.
- Update or delete every existing spec that references the dropped fields (`admin_percent`, `split_mode`, `EntrySplit`, `compute_splits`).

100% coverage maintained per `pyproject.toml` `fail_under = 100`.

---

## Version Bump & Changelog

Per `plfog/version.py` convention. Member-friendly changelog entry:

> "Products can now split revenue across multiple guilds and admin. Each product can be set up with any combination of recipients (for example: 20% admin, 60% Ceramics, 20% Art Framing) as long as the percentages add up to 100%. The Add Product form has been redesigned to make this easier to manage."

---

## Out of Scope (Future Work)

- Stripe Connect destination charges (automated payouts to guild accounts).
- Inline edit of existing products.
- Bulk import of products with splits.
- Per-member or per-event split overrides.
