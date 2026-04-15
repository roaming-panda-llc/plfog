# Product Revenue Splits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-recipient + admin-percent product split with a flexible N-recipient split (Admin + any combination of Guilds, must sum to 100%), and convert the Add Product modal into an inline form on the guild admin edit page.

**Architecture:** New `ProductRevenueSplit` table holds the split rows for each product; new `TabEntrySplit` table holds the frozen snapshot at entry-creation time. Reports SELECT from `TabEntrySplit` directly. The form uses Django `inlineformset_factory` server-side and Alpine.js client-side for dynamic add/remove/preview. All Stripe behaviour is unchanged — splits are accounting-only.

**Tech Stack:** Django 5, pytest + pytest-describe (BDD specs in `*_spec.py`), Alpine.js, factory-boy, ruff. Database: PostgreSQL (local + prod via `DATABASE_URL`).

**Spec:** [docs/superpowers/specs/2026-04-14-product-revenue-splits-design.md](../specs/2026-04-14-product-revenue-splits-design.md)

**Git workflow note:** Project rule — Josh handles `git add`, `git commit`, `git push`. Each task ends with a suggested commit message; the executor should announce when ready and let Josh run the commit.

---

## File Map

**Created:**
- `billing/migrations/0009_product_revenue_split_tabentry_split.py` — schema
- `billing/migrations/0010_wipe_and_drop_legacy_split_fields.py` — data wipe + field drops
- `billing/spec/models/product_revenue_split_spec.py`
- `billing/spec/models/tab_entry_split_spec.py`
- `billing/spec/forms/product_form_spec.py`
- `billing/spec/views/guild_admin_product_form_spec.py`

**Modified:**
- `billing/models.py` — Product/TabEntry field changes; new `ProductRevenueSplit` + `TabEntrySplit` classes; rewrite `Tab.add_entry()`; add `TabEntry.snapshot_splits()`; delete `EntrySplit` dataclass + `compute_splits()`
- `billing/admin.py` — `ProductAdmin` cleanup
- `billing/forms.py` — `ProductForm` + `ProductRevenueSplitFormSet` (new), `TabItemForm` rewritten to take splits formset
- `billing/views.py` — `admin_add_tab_entry` accepts splits formset
- `billing/reports.py` — `build_report` switched to `TabEntrySplit` queries; `ReportRow` reshape
- `billing/stripe_utils.py` — no behaviour change (verify nothing references dropped fields)
- `membership/admin.py` — `GuildProductInline` swapped for the new form integration
- `templates/admin/membership/guild_product_inline.html` — modal removed; always-visible inline form with Alpine dynamic split rows
- `templates/billing/admin_reports.html` — "Recipient" column replaces "Guild"; payout summary includes Admin row
- `templates/hub/guild_detail.html` — split summary on each product card
- `tests/billing/factories.py` — add `ProductRevenueSplitFactory`, `TabEntrySplitFactory`; rewrite `ProductFactory` and `TabEntryFactory`
- `billing/CLAUDE.md` — documentation update
- `plfog/version.py` — version bump + changelog entry

**Deleted (after extraction):**
- `tests/billing/models/compute_splits_spec.py`
- Any test referencing dropped fields (see Task 12 for the exact list)

---

## Pre-flight (do once, not a task)

The executor must verify:

```bash
.venv/bin/python --version    # 3.13.x
docker ps | grep plfog-db-1   # Postgres running
.venv/bin/pytest --collect-only -q | tail -5  # baseline test count
git status -s                  # clean working tree
```

If anything fails, fix before starting Task 1.

---

## Task 1: Add `ProductRevenueSplit` and `TabEntrySplit` tables (schema only)

**Files:**
- Create: `billing/migrations/0009_product_revenue_split_tabentry_split.py`
- Modify: `billing/models.py` (append new classes; do **not** touch Product or TabEntry yet)
- Create: `billing/spec/models/product_revenue_split_spec.py`

- [ ] **Step 1: Write the failing test for `ProductRevenueSplit` constraints**

Create `billing/spec/models/product_revenue_split_spec.py`:

```python
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from billing.models import ProductRevenueSplit
from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory


def describe_ProductRevenueSplit():
    def describe_constraints():
        def it_allows_an_admin_row_with_no_guild(db):
            product = ProductFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                guild=None,
                percent=Decimal("20"),
            )
            assert product.splits.count() == 1

        def it_allows_a_guild_row_with_a_guild(db):
            product = ProductFactory()
            guild = GuildFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("80"),
            )
            assert product.splits.count() == 1

        def it_rejects_an_admin_row_that_has_a_guild(db):
            product = ProductFactory()
            guild = GuildFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=guild,
                    percent=Decimal("20"),
                )

        def it_rejects_a_guild_row_with_no_guild(db):
            product = ProductFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                    guild=None,
                    percent=Decimal("80"),
                )

        def it_rejects_a_zero_percent(db):
            product = ProductFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("0"),
                )

        def it_rejects_a_percent_over_100(db):
            product = ProductFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("100.01"),
                )

    def describe_uniqueness():
        def it_rejects_two_admin_rows_on_the_same_product(db):
            product = ProductFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                guild=None,
                percent=Decimal("20"),
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
                    guild=None,
                    percent=Decimal("10"),
                )

        def it_rejects_the_same_guild_twice_on_one_product(db):
            product = ProductFactory()
            guild = GuildFactory()
            ProductRevenueSplit.objects.create(
                product=product,
                recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild,
                percent=Decimal("50"),
            )
            with pytest.raises(IntegrityError), transaction.atomic():
                ProductRevenueSplit.objects.create(
                    product=product,
                    recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                    guild=guild,
                    percent=Decimal("30"),
                )

        def it_allows_the_same_guild_on_different_products(db):
            guild = GuildFactory()
            p1 = ProductFactory()
            p2 = ProductFactory()
            ProductRevenueSplit.objects.create(
                product=p1, recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild, percent=Decimal("100"),
            )
            ProductRevenueSplit.objects.create(
                product=p2, recipient_type=ProductRevenueSplit.RecipientType.GUILD,
                guild=guild, percent=Decimal("100"),
            )
            assert ProductRevenueSplit.objects.filter(guild=guild).count() == 2
```

- [ ] **Step 2: Run test to verify it fails (model doesn't exist)**

Run: `.venv/bin/pytest billing/spec/models/product_revenue_split_spec.py -v`
Expected: ImportError on `ProductRevenueSplit`.

- [ ] **Step 3: Add the model classes to `billing/models.py`**

Append at the bottom of `billing/models.py`, after `TabCharge`:

```python
# ---------------------------------------------------------------------------
# Revenue splits — flexible N-recipient model (replaces SplitMode)
# ---------------------------------------------------------------------------


class ProductRevenueSplit(models.Model):
    """One recipient row in a Product's revenue split.

    A product's splits collectively must sum to 100% — enforced in
    ``ProductForm.clean()`` (cross-row, not portable as a DB constraint).
    """

    class RecipientType(models.TextChoices):
        ADMIN = "admin", "Admin"
        GUILD = "guild", "Guild"

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="splits",
        help_text="The product this split row belongs to.",
    )
    recipient_type = models.CharField(
        max_length=10,
        choices=RecipientType.choices,
        help_text="Whether this row pays the admin or a specific guild.",
    )
    guild = models.ForeignKey(
        "membership.Guild",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="product_revenue_splits",
        help_text="The guild this row pays. Required for GUILD rows, must be NULL for ADMIN rows.",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage of the product price this recipient receives. 0 < percent <= 100.",
    )

    class Meta:
        verbose_name = "Product Revenue Split"
        verbose_name_plural = "Product Revenue Splits"
        ordering = ["product_id", "recipient_type", "guild_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(percent__gt=0) & Q(percent__lte=100),
                name="prodrevsplit_percent_range",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(recipient_type="guild") & Q(guild__isnull=False))
                    | (Q(recipient_type="admin") & Q(guild__isnull=True))
                ),
                name="prodrevsplit_recipient_guild_consistent",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(recipient_type="admin"),
                name="uq_prodrevsplit_admin_per_product",
            ),
            models.UniqueConstraint(
                fields=["product", "guild"],
                condition=Q(recipient_type="guild"),
                name="uq_prodrevsplit_guild_per_product",
            ),
        ]

    def __str__(self) -> str:
        if self.recipient_type == self.RecipientType.ADMIN:
            return f"Admin {self.percent}%"
        return f"{self.guild.name if self.guild_id else 'Guild?'} {self.percent}%"


class TabEntrySplit(models.Model):
    """Frozen snapshot of one recipient's share of a TabEntry.

    Created in ``TabEntry.snapshot_splits()`` at entry-creation time. Reports
    SELECT directly from this table — never recomputed.
    """

    class RecipientType(models.TextChoices):
        ADMIN = "admin", "Admin"
        GUILD = "guild", "Guild"

    entry = models.ForeignKey(
        "TabEntry",
        on_delete=models.CASCADE,
        related_name="splits",
        help_text="The tab entry this split row belongs to.",
    )
    recipient_type = models.CharField(
        max_length=10,
        choices=RecipientType.choices,
        help_text="Whether this row paid the admin or a specific guild.",
    )
    guild = models.ForeignKey(
        "membership.Guild",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tab_entry_splits",
        help_text="The guild this row paid (snapshot). Required for GUILD rows, NULL for ADMIN rows.",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage of the entry amount paid to this recipient at snapshot time.",
    )
    amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Dollar amount paid to this recipient. Computed at snapshot time.",
    )

    class Meta:
        verbose_name = "Tab Entry Split"
        verbose_name_plural = "Tab Entry Splits"
        ordering = ["entry_id", "recipient_type", "guild_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(percent__gt=0) & Q(percent__lte=100),
                name="tabentrysplit_percent_range",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(recipient_type="guild") & Q(guild__isnull=False))
                    | (Q(recipient_type="admin") & Q(guild__isnull=True))
                ),
                name="tabentrysplit_recipient_guild_consistent",
            ),
        ]

    def __str__(self) -> str:
        recipient = "Admin" if self.recipient_type == self.RecipientType.ADMIN else (self.guild.name if self.guild_id else "Guild?")
        return f"{recipient} ${self.amount} ({self.percent}%)"
```

- [ ] **Step 4: Generate the migration**

Run:
```bash
.venv/bin/python manage.py makemigrations billing --name product_revenue_split_tabentry_split
```

Verify: a file named `billing/migrations/0009_product_revenue_split_tabentry_split.py` is created and contains `CreateModel` for both new models. Open it; ensure the constraint names match what's in `Meta`.

- [ ] **Step 5: Apply the migration**

Run: `.venv/bin/python manage.py migrate billing`
Expected: `Applying billing.0009_product_revenue_split_tabentry_split... OK`

- [ ] **Step 6: Run the new spec — should pass**

Run: `.venv/bin/pytest billing/spec/models/product_revenue_split_spec.py -v`
Expected: all 9 tests pass.

- [ ] **Step 7: Run full test suite — should still pass (no other code changed)**

Run: `.venv/bin/pytest -q`
Expected: same number of tests as baseline pass; new 9 added.

- [ ] **Step 8: Suggested commit**

```
feat(billing): add ProductRevenueSplit and TabEntrySplit tables

Schema-only addition; no business logic wired up yet.
```

---

## Task 2: Add `TabEntry.snapshot_splits()` with rounding rule

**Files:**
- Modify: `billing/models.py` (add method on `TabEntry`)
- Create: `billing/spec/models/tab_entry_split_spec.py`

- [ ] **Step 1: Write the failing tests for snapshot_splits**

Create `billing/spec/models/tab_entry_split_spec.py`:

```python
from decimal import Decimal

import pytest

from billing.models import TabEntrySplit
from tests.billing.factories import TabFactory, TabEntryFactory
from tests.membership.factories import GuildFactory


def _split_input(recipient_type, percent, guild=None):
    return {"recipient_type": recipient_type, "guild": guild, "percent": Decimal(str(percent))}


def describe_TabEntry_snapshot_splits():
    def it_writes_one_TabEntrySplit_per_input_row(db):
        entry = TabEntryFactory(amount=Decimal("10.00"))
        guild = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "20"),
            _split_input("guild", "80", guild=guild),
        ])
        assert entry.splits.count() == 2

    def it_rounds_each_split_amount_with_round_half_up(db):
        entry = TabEntryFactory(amount=Decimal("10.00"))
        guild = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "20", guild=None),
            _split_input("guild", "80", guild=guild),
        ])
        admin = entry.splits.get(recipient_type="admin")
        g = entry.splits.get(recipient_type="guild")
        assert admin.amount == Decimal("2.00")
        assert g.amount == Decimal("8.00")

    def it_assigns_remainder_pennies_to_the_largest_percent_row(db):
        # $0.03 split three ways = $0.01 each, no remainder. Try $0.10 / 3 ways:
        # 33% -> 0.033 -> 0.03;  33% -> 0.033 -> 0.03;  34% -> 0.034 -> 0.03
        # raw sum = 0.09; remainder = 0.01 should go to largest (34%) row.
        entry = TabEntryFactory(amount=Decimal("0.10"))
        g1 = GuildFactory()
        g2 = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "33", guild=None),
            _split_input("guild", "33", guild=g1),
            _split_input("guild", "34", guild=g2),
        ])
        amounts = sorted(entry.splits.values_list("amount", flat=True))
        assert amounts == [Decimal("0.03"), Decimal("0.03"), Decimal("0.04")]
        # 34% row absorbs the penny
        largest = entry.splits.get(percent=Decimal("34"))
        assert largest.amount == Decimal("0.04")

    def it_keeps_sum_equal_to_entry_amount_for_one_cent_50_50(db):
        entry = TabEntryFactory(amount=Decimal("0.01"))
        g = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "50"),
            _split_input("guild", "50", guild=g),
        ])
        total = sum((s.amount for s in entry.splits.all()), Decimal("0"))
        assert total == Decimal("0.01")

    def it_handles_a_single_recipient_at_100_percent(db):
        entry = TabEntryFactory(amount=Decimal("25.00"))
        g = GuildFactory()
        entry.snapshot_splits([_split_input("guild", "100", guild=g)])
        assert entry.splits.count() == 1
        only = entry.splits.first()
        assert only.amount == Decimal("25.00")
        assert only.percent == Decimal("100")
        assert only.guild_id == g.pk

    def it_breaks_largest_percent_ties_by_lowest_id(db):
        # 50/50 split: both rows are equally largest. Penny remainder
        # (if any) should go to the row created first (lowest id).
        entry = TabEntryFactory(amount=Decimal("0.03"))
        g = GuildFactory()
        entry.snapshot_splits([
            _split_input("admin", "50"),
            _split_input("guild", "50", guild=g),
        ])
        admin_split = entry.splits.get(recipient_type="admin")
        guild_split = entry.splits.get(recipient_type="guild")
        # 0.03 * 0.5 = 0.015 -> rounds half-up to 0.02 each = 0.04 (overshoot by 0.01)
        # OR 0.015 floors to 0.01 each = 0.02 (undershoot by 0.01).
        # Either way one row absorbs +/-0.01 to make total exactly 0.03.
        # Lowest id (admin, created first) absorbs the adjustment.
        assert admin_split.amount + guild_split.amount == Decimal("0.03")
        assert admin_split.id < guild_split.id

    def it_raises_if_inputs_dont_cover_full_amount_after_rounding(db):
        # Sanity check: snapshot_splits should not be callable with bad inputs.
        # Form-level validation prevents this in production, but the method
        # asserts internally as defense in depth.
        entry = TabEntryFactory(amount=Decimal("10.00"))
        with pytest.raises(AssertionError):
            entry.snapshot_splits([
                _split_input("admin", "50"),
                # Missing other 50% — sums to 50, not 100
            ])

    def it_creates_admin_split_with_null_guild(db):
        entry = TabEntryFactory(amount=Decimal("5.00"))
        entry.snapshot_splits([_split_input("admin", "100")])
        only = entry.splits.first()
        assert only.recipient_type == TabEntrySplit.RecipientType.ADMIN
        assert only.guild_id is None
```

- [ ] **Step 2: Run test to verify it fails (method doesn't exist)**

Run: `.venv/bin/pytest billing/spec/models/tab_entry_split_spec.py -v`
Expected: `AttributeError: 'TabEntry' object has no attribute 'snapshot_splits'`.

- [ ] **Step 3: Implement `snapshot_splits` on `TabEntry`**

In `billing/models.py`, inside the `TabEntry` class (after the `void()` method, before `compute_splits`), add:

```python
def snapshot_splits(self, splits: list[dict[str, Any]]) -> list[TabEntrySplit]:
    """Freeze the revenue split for this entry into TabEntrySplit rows.

    Args:
        splits: List of dicts with keys: ``recipient_type`` (str: 'admin' or
            'guild'), ``guild`` (Guild instance or None), ``percent`` (Decimal).
            The percents must sum to exactly 100. The caller (form layer) is
            responsible for validating this before calling.

    Returns:
        The list of created TabEntrySplit instances.

    Rounding rule:
        Each row's amount is computed as
        ``quantize(self.amount * percent / 100, '0.01', ROUND_HALF_UP)``. The
        row with the largest percent absorbs the +/-1c remainder so the
        children sum exactly to ``self.amount``. Ties on largest percent are
        broken by the order rows are passed in (lowest creation id wins,
        because the largest is rebound after creation).

    Raises:
        AssertionError: If the inputs don't sum to exactly 100% or if the
            rounded splits cannot be reconciled to the entry total.
    """
    total_percent = sum((Decimal(str(s["percent"])) for s in splits), Decimal("0"))
    assert total_percent == _HUNDRED, f"splits must sum to 100, got {total_percent}"

    created: list[TabEntrySplit] = []
    raw_total = _ZERO
    largest_idx = 0
    largest_pct = Decimal("-1")
    for i, s in enumerate(splits):
        pct = Decimal(str(s["percent"]))
        amt = (self.amount * pct / _HUNDRED).quantize(_CENTS, rounding=ROUND_HALF_UP)
        raw_total += amt
        if pct > largest_pct:
            largest_pct = pct
            largest_idx = i
        created.append(
            TabEntrySplit.objects.create(
                entry=self,
                recipient_type=s["recipient_type"],
                guild=s["guild"],
                percent=pct,
                amount=amt,
            )
        )

    drift = self.amount - raw_total
    if drift != _ZERO:
        # Adjust the largest-percent row by the drift (+/- 1c typically)
        adj_row = created[largest_idx]
        adj_row.amount = adj_row.amount + drift
        adj_row.save(update_fields=["amount"])

    final_total = sum((s.amount for s in TabEntrySplit.objects.filter(entry=self)), _ZERO)
    assert final_total == self.amount, f"split sum {final_total} != entry {self.amount}"

    return list(self.splits.all())
```

- [ ] **Step 4: Run the new spec**

Run: `.venv/bin/pytest billing/spec/models/tab_entry_split_spec.py -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -q`
Expected: still passes (existing tests untouched; new 8 added).

- [ ] **Step 6: Suggested commit**

```
feat(billing): add TabEntry.snapshot_splits with penny-rounding rule
```

---

## Task 3: Wipe legacy data + drop legacy split fields

**Files:**
- Create: `billing/migrations/0010_wipe_and_drop_legacy_split_fields.py`
- Modify: `billing/models.py` (delete `EntrySplit` dataclass; delete `Product.SplitMode`; delete legacy fields on `Product` and `TabEntry`; delete `TabEntry.compute_splits()`; remove `is_active` from `Product`; update `Tab.add_entry()` signature placeholder)
- Modify: `billing/reports.py` (temporarily comment out `build_report` body or have it return empties — Task 8 rebuilds it)
- Modify: `billing/forms.py` (`TabItemForm` references `admin_percent`/`split_equally` — temporarily strip those fields; Task 6 rebuilds)
- Delete: `tests/billing/models/compute_splits_spec.py`

> **Note:** This task intentionally leaves the codebase in a degraded state — `build_report` returns empty rows and `TabItemForm` has reduced fields. Tasks 4–8 restore full functionality. The migration is the destructive event; we **must not** ship anything with this on prod without the followups.

- [ ] **Step 1: Inspect what currently references the legacy symbols**

Run:
```bash
.venv/bin/python -c "import django; django.setup()" 2>&1 || true
grep -rn 'compute_splits\|EntrySplit\|SplitMode\|admin_percent_override\|split_mode\|split_guild_ids\|is_active' billing/ membership/ hub/ tests/ templates/ --include='*.py' --include='*.html' | grep -v '__pycache__' > /tmp/legacy-refs.txt
wc -l /tmp/legacy-refs.txt
```
Skim `/tmp/legacy-refs.txt`. Anything outside `billing/`, `tests/`, and the templates/admin guild template that surprises you should be flagged before proceeding.

- [ ] **Step 2: Write the data-wipe migration**

Create `billing/migrations/0010_wipe_and_drop_legacy_split_fields.py`:

```python
"""Wipe products + tab entries/charges, then drop legacy split fields.

This is a one-time, irreversible migration tied to the v1.7 product-revenue-
splits feature. It assumes the operator has backed up the database before
running it. Re-applying it on an already-migrated database is a no-op for the
data wipe (everything is already gone) and the schema changes are idempotent
under Django's migration framework.
"""

from django.db import migrations, models


def wipe_billing_data(apps, schema_editor):
    Product = apps.get_model("billing", "Product")
    TabEntry = apps.get_model("billing", "TabEntry")
    TabCharge = apps.get_model("billing", "TabCharge")

    # Delete in dependency order: TabEntry FK -> TabCharge, Product;
    # TabCharge FK -> Tab (kept). Wiping TabEntry/TabCharge first is safest.
    TabEntry.objects.all().delete()
    TabCharge.objects.all().delete()
    Product.objects.all().delete()


def cannot_reverse(apps, schema_editor):
    raise RuntimeError(
        "Migration 0010 is irreversible: it wipes Product/TabEntry/TabCharge data. "
        "Restore from a database backup if you need to roll back."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_product_revenue_split_tabentry_split"),
    ]

    operations = [
        migrations.RunPython(wipe_billing_data, cannot_reverse),
        migrations.RemoveField(model_name="product", name="admin_percent_override"),
        migrations.RemoveField(model_name="product", name="split_mode"),
        migrations.RemoveField(model_name="product", name="is_active"),
        migrations.RemoveField(model_name="tabentry", name="admin_percent"),
        migrations.RemoveField(model_name="tabentry", name="split_mode"),
        migrations.RemoveField(model_name="tabentry", name="guild"),
        migrations.RemoveField(model_name="tabentry", name="split_guild_ids"),
        # Drop the legacy DB-level CHECK constraint on admin_percent_override
        migrations.RemoveConstraint(
            model_name="product",
            name="product_admin_percent_override_range",
        ),
    ]
```

- [ ] **Step 3: Edit `billing/models.py` — remove the legacy code in lockstep**

Apply each of these edits:

1. **Delete the `EntrySplit` dataclass** (currently lines ~32–40):

   Remove:
   ```python
   @dataclass(frozen=True)
   class EntrySplit:
       """One row of a TabEntry's revenue breakdown — see TabEntry.compute_splits()."""
       guild_id: int | None
       admin_amount: Decimal
       guild_amount: Decimal
       is_admin_only: bool = False
   ```

   Also remove the `from dataclasses import dataclass` import line if `dataclass` is no longer used elsewhere in the file (verify with grep).

2. **Delete `Product.SplitMode` enum and the legacy fields**:

   In the `Product` class, remove the entire `class SplitMode(...)` block, the `admin_percent_override = models.DecimalField(...)`, the `split_mode = models.CharField(...)`, and the `is_active = models.BooleanField(...)` field declarations. Remove the `effective_admin_percent` property too.

   Also remove the `product_admin_percent_override_range` `CheckConstraint` from `Product.Meta.constraints` (keep the `product_price_positive` check).

3. **Delete legacy fields from `TabEntry`**:

   Remove `admin_percent`, `split_mode`, `guild`, `split_guild_ids` field declarations and the comment block above them.

4. **Delete `TabEntry.compute_splits()`** entirely (lines ~724–787).

5. **Update `Tab.add_entry()` to a stub signature**:

   Change the signature to:

   ```python
   def add_entry(
       self,
       *,
       description: str,
       amount: Decimal,
       added_by: User | None = None,
       is_self_service: bool = False,
       product: Product | None = None,
       splits: list[dict[str, Any]] | None = None,
   ) -> TabEntry:
       """Add a line item to this tab, snapshotting the revenue split.

       Args:
           splits: Required unless ``product`` is supplied. List of dicts:
               ``[{"recipient_type": "admin"|"guild", "guild": Guild|None, "percent": Decimal}]``.
               Must sum to 100. Pulled from ``product.splits`` when ``product``
               is given and ``splits`` is None.

       Raises:
           TabLockedError, TabLimitExceededError, ValueError: see body.
       """
       if splits is None:
           if product is None:
               raise ValueError("Either product or splits must be supplied.")
           splits = [
               {"recipient_type": s.recipient_type, "guild": s.guild, "percent": s.percent}
               for s in product.splits.all()
           ]

       with transaction.atomic():
           locked_self = Tab.objects.select_for_update().get(pk=self.pk)
           if locked_self.is_locked:
               raise TabLockedError(f"Tab is locked: {locked_self.locked_reason}")
           current = locked_self.current_balance
           if current + amount > locked_self.effective_tab_limit:
               raise TabLimitExceededError(
                   f"Entry of ${amount} would exceed tab limit "
                   f"(balance: ${current}, limit: ${locked_self.effective_tab_limit})."
               )
           entry = TabEntry.objects.create(
               tab=self,
               description=description,
               amount=amount,
               added_by=added_by,
               is_self_service=is_self_service,
               product=product,
           )
           entry.snapshot_splits(splits)
           return entry
   ```

   Remove the now-unused import `from membership.models import Guild as _Guild` line at the top of the method body. The `if TYPE_CHECKING: from membership.models import Guild` import at the top of the file can stay.

- [ ] **Step 4: Stub out `billing/reports.py` and `billing/forms.py` to compile**

In `billing/reports.py`, around the `build_report` body (lines ~106-192):

Replace the entire `build_report` function body with:

```python
def build_report(
    *,
    start_date: date_cls | None = None,
    end_date: date_cls | None = None,
    guild_ids: list[int] | None = None,
    charge_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[ReportRow], list[PayoutRow], Decimal]:
    """Stubbed during refactor — see Task 8 for the real implementation."""
    return [], [], _ZERO
```

Also remove `from billing.models import Product, TabCharge, TabEntry` and replace with `from billing.models import TabCharge, TabEntry` (Product no longer needed here). Drop `_base_entries` and `_guild_name_cache` for now — Task 8 will rewrite them. Comment out the body of `_base_entries` similarly:

```python
def _base_entries(*args, **kwargs):
    raise NotImplementedError("Rebuilt in Task 8")
```

In `billing/forms.py`, in `TabItemForm.__init__` and the form fields, **remove** every reference to `admin_percent` and `split_equally`. Specifically:

- Delete `admin_percent = forms.DecimalField(...)` and `split_equally = forms.BooleanField(...)` field declarations on the form class.
- Delete code in `__init__` that disables/initializes those fields.
- Delete code in `clean()` and `save()` that reads `cleaned_data["admin_percent"]` or `cleaned_data["split_equally"]`.
- The form's `save()` method should now call `tab.add_entry()` with `product=` only (not `admin_percent=`/`split_mode=`); if that path was used for custom (non-product) entries, raise `NotImplementedError("Custom-entry splits rebuilt in Task 7")` for now.

If the file becomes too tangled, just stub `TabItemForm.save` to `raise NotImplementedError`. Task 7 rewrites the form.

- [ ] **Step 5: Delete legacy specs that test deleted code**

Run:
```bash
rm tests/billing/models/compute_splits_spec.py
```

Open each of these files and either delete the file outright or comment out every test that references the deleted symbols (`compute_splits`, `EntrySplit`, `SplitMode`, `admin_percent`, `admin_percent_override`, `split_mode`, `split_guild_ids`, `is_active`):

- `tests/billing/models/product_spec.py` — likely needs heavy edits
- `tests/billing/models/tab_spec.py` — `add_entry` tests likely need rewriting
- `tests/billing/models/tab_entry_spec.py` — same
- `tests/billing/reports_spec.py` — comment out everything; Task 8 rewrites
- `tests/billing/forms_spec.py` — comment out everything that touched admin_percent/split_equally; Task 7 rewrites
- `tests/billing/admin_dashboard_spec.py` — review

Mark each commented-out test with a `# TODO(splits): rewrite in Task N` comment so they don't get lost.

For each file you delete entirely, also `rm` the file. For each file you partially comment, leave it tracked.

- [ ] **Step 6: Rewrite `tests/billing/factories.py`**

Locate `ProductFactory` and `TabEntryFactory`. Replace with:

```python
import factory
from decimal import Decimal

from billing.models import Product, ProductRevenueSplit, Tab, TabCharge, TabEntry, TabEntrySplit
from tests.membership.factories import GuildFactory, MemberFactory


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Product {n}")
    price = Decimal("10.00")
    guild = factory.SubFactory(GuildFactory)

    @factory.post_generation
    def with_default_splits(self, create, extracted, **kwargs):
        """Auto-attach 20% Admin / 80% owning-guild splits unless caller opts out."""
        if not create:
            return
        if extracted is False:
            return  # caller passed `with_default_splits=False`
        if self.splits.exists():
            return  # caller already added splits manually
        ProductRevenueSplit.objects.create(
            product=self,
            recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
            guild=None,
            percent=Decimal("20"),
        )
        ProductRevenueSplit.objects.create(
            product=self,
            recipient_type=ProductRevenueSplit.RecipientType.GUILD,
            guild=self.guild,
            percent=Decimal("80"),
        )


class ProductRevenueSplitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductRevenueSplit

    product = factory.SubFactory(ProductFactory, with_default_splits=False)
    recipient_type = ProductRevenueSplit.RecipientType.GUILD
    guild = factory.SubFactory(GuildFactory)
    percent = Decimal("100")


class TabFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tab

    member = factory.SubFactory(MemberFactory)
    stripe_payment_method_id = "pm_test"
    payment_method_last4 = "4242"
    payment_method_brand = "visa"


class TabEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TabEntry

    tab = factory.SubFactory(TabFactory)
    description = factory.Sequence(lambda n: f"Charge {n}")
    amount = Decimal("10.00")


class TabEntrySplitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TabEntrySplit

    entry = factory.SubFactory(TabEntryFactory)
    recipient_type = TabEntrySplit.RecipientType.GUILD
    guild = factory.SubFactory(GuildFactory)
    percent = Decimal("100")
    amount = Decimal("10.00")


class TabChargeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TabCharge

    tab = factory.SubFactory(TabFactory)
    amount = Decimal("10.00")
    status = TabCharge.Status.PENDING
```

(Adjust other fields to match whatever `BillingSettingsFactory` etc. already exist in the file — keep those untouched.)

- [ ] **Step 7: Generate the migration check, then apply**

Run:
```bash
.venv/bin/python manage.py makemigrations --dry-run --check
```
Expected: "No changes detected" (the model edits should already be reflected by the manually-written 0010 migration).

If it reports unmodeled changes, the manual migration is incomplete — add the missing operations.

Apply:
```bash
.venv/bin/python manage.py migrate billing
```
Expected: `Applying billing.0010_wipe_and_drop_legacy_split_fields... OK`

- [ ] **Step 8: Run the test suite — expect a smaller passing set**

Run: `.venv/bin/pytest -q`
Expected: All remaining tests pass. Many specs are commented out (TODO markers). The new specs from Tasks 1–2 still pass.

- [ ] **Step 9: Suggested commit**

```
refactor(billing): wipe legacy product/entry data, drop legacy split fields

DESTRUCTIVE — see migration 0010 docstring. Reports + custom entry forms
are stubbed; Tasks 4–8 restore them on top of the new split tables.
```

---

## Task 4: Rewrite `Tab.add_entry()` integration tests

**Files:**
- Modify: `tests/billing/models/tab_spec.py`

This task adds back the `add_entry` test coverage we commented out in Task 3, now exercising the new splits-snapshot behaviour.

- [ ] **Step 1: Write the new tests**

In `tests/billing/models/tab_spec.py`, append (or replace the commented-out `describe_add_entry` block with) the following spec:

```python
from decimal import Decimal

import pytest

from billing.models import ProductRevenueSplit, TabEntrySplit
from tests.billing.factories import ProductFactory, TabFactory
from tests.membership.factories import GuildFactory


def describe_Tab_add_entry_with_splits():
    def it_pulls_splits_from_the_product_when_no_splits_kwarg(db):
        product = ProductFactory()  # default 20% admin / 80% owning guild
        tab = TabFactory()
        entry = tab.add_entry(description="bag of clay", amount=Decimal("10.00"), product=product)
        assert entry.splits.count() == 2
        admin = entry.splits.get(recipient_type=TabEntrySplit.RecipientType.ADMIN)
        guild_split = entry.splits.get(recipient_type=TabEntrySplit.RecipientType.GUILD)
        assert admin.amount == Decimal("2.00")
        assert guild_split.amount == Decimal("8.00")
        assert guild_split.guild_id == product.guild_id

    def it_uses_explicit_splits_kwarg_when_supplied(db):
        tab = TabFactory()
        g = GuildFactory()
        entry = tab.add_entry(
            description="custom",
            amount=Decimal("10.00"),
            splits=[
                {"recipient_type": "admin", "guild": None, "percent": Decimal("100")},
            ],
        )
        assert entry.splits.count() == 1
        only = entry.splits.first()
        assert only.recipient_type == TabEntrySplit.RecipientType.ADMIN
        assert only.amount == Decimal("10.00")

    def it_raises_when_neither_product_nor_splits_supplied(db):
        tab = TabFactory()
        with pytest.raises(ValueError):
            tab.add_entry(description="x", amount=Decimal("5.00"))

    def it_snapshots_split_state_at_creation_time(db):
        # If the product's splits are edited later, the entry's snapshot should not change.
        product = ProductFactory()
        tab = TabFactory()
        entry = tab.add_entry(description="x", amount=Decimal("10.00"), product=product)

        product.splits.all().delete()
        ProductRevenueSplit.objects.create(
            product=product,
            recipient_type=ProductRevenueSplit.RecipientType.ADMIN,
            guild=None,
            percent=Decimal("100"),
        )

        entry.refresh_from_db()
        assert entry.splits.count() == 2  # unchanged
```

- [ ] **Step 2: Run the new tests**

Run: `.venv/bin/pytest tests/billing/models/tab_spec.py -v`
Expected: all 4 tests pass. (Existing tests in this file that don't reference legacy fields should also still pass.)

- [ ] **Step 3: Suggested commit**

```
test(billing): cover Tab.add_entry splits snapshot behaviour
```

---

## Task 5: `ProductForm` + `ProductRevenueSplitFormSet` with sum-to-100 validation

**Files:**
- Modify: `billing/forms.py` (add `ProductForm`, `ProductRevenueSplitFormSet`)
- Create: `billing/spec/forms/product_form_spec.py`

- [ ] **Step 1: Write the failing form spec**

Create `billing/spec/forms/product_form_spec.py`:

```python
from decimal import Decimal

import pytest

from billing.forms import ProductForm, ProductRevenueSplitFormSet, build_product_split_formset
from billing.models import Product, ProductRevenueSplit
from tests.billing.factories import ProductFactory
from tests.membership.factories import GuildFactory


def _split_post(prefix, idx, *, recipient_type, guild_id, percent, delete=False):
    """Helper: build POST kwargs for one split row in a formset."""
    out = {
        f"{prefix}-{idx}-recipient_type": recipient_type,
        f"{prefix}-{idx}-guild": str(guild_id) if guild_id else "",
        f"{prefix}-{idx}-percent": str(percent),
    }
    if delete:
        out[f"{prefix}-{idx}-DELETE"] = "on"
    return out


def _post(*, product_name, price, splits, owning_guild, prefix="splits"):
    """Build a full POST dict for ProductForm + formset."""
    data = {
        "name": product_name,
        "price": str(price),
        "guild": str(owning_guild.pk),
        f"{prefix}-TOTAL_FORMS": str(len(splits)),
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "1",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for i, s in enumerate(splits):
        data.update(_split_post(prefix, i, **s))
    return data


def describe_ProductForm():
    def describe_validation():
        def it_accepts_a_valid_admin_plus_guild_split(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="Test Bag", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": None, "percent": Decimal("20")},
                    {"recipient_type": "guild", "guild_id": owning_guild.pk, "percent": Decimal("80")},
                ],
            )
            form = ProductForm(data=data)
            formset = build_product_split_formset(data=data, instance=Product())
            assert form.is_valid(), form.errors
            assert formset.is_valid(), formset.errors

        def it_rejects_when_percentages_dont_sum_to_100(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": None, "percent": Decimal("20")},
                    {"recipient_type": "guild", "guild_id": owning_guild.pk, "percent": Decimal("70")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()
            assert any("100" in e for e in formset.non_form_errors())

        def it_rejects_when_no_split_rows_supplied(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild, splits=[],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_duplicate_admin_rows(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": None, "percent": Decimal("50")},
                    {"recipient_type": "admin", "guild_id": None, "percent": Decimal("50")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()
            assert any("Admin" in e or "duplicate" in e.lower() for e in formset.non_form_errors())

        def it_rejects_the_same_guild_twice(db):
            owning_guild = GuildFactory()
            other = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "guild", "guild_id": other.pk, "percent": Decimal("50")},
                    {"recipient_type": "guild", "guild_id": other.pk, "percent": Decimal("50")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_a_guild_row_without_a_guild(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "guild", "guild_id": None, "percent": Decimal("100")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_an_admin_row_with_a_guild(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": owning_guild.pk, "percent": Decimal("100")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_zero_percent(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x", price=Decimal("10.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": None, "percent": Decimal("0")},
                    {"recipient_type": "guild", "guild_id": owning_guild.pk, "percent": Decimal("100")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

    def describe_save():
        def it_persists_product_and_split_rows_in_one_transaction(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="Bag", price=Decimal("12.00"), owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": None, "percent": Decimal("20")},
                    {"recipient_type": "guild", "guild_id": owning_guild.pk, "percent": Decimal("80")},
                ],
            )
            form = ProductForm(data=data)
            assert form.is_valid()
            product = form.save(commit=False)
            product.save()
            formset = build_product_split_formset(data=data, instance=product)
            assert formset.is_valid(), formset.errors
            formset.save()
            assert product.splits.count() == 2
            assert ProductRevenueSplit.objects.filter(product=product, recipient_type="admin").exists()
```

- [ ] **Step 2: Run the new spec — should fail (forms not implemented)**

Run: `.venv/bin/pytest billing/spec/forms/product_form_spec.py -v`
Expected: ImportError on `ProductForm` / `build_product_split_formset`.

- [ ] **Step 3: Implement the form + formset in `billing/forms.py`**

At the bottom of `billing/forms.py`, add:

```python
from decimal import Decimal as _Decimal  # avoid colliding with module-level imports

from django.forms import inlineformset_factory, BaseInlineFormSet

from billing.models import Product, ProductRevenueSplit


class ProductForm(forms.ModelForm):
    """Product fields only — splits are handled by ProductRevenueSplitFormSet."""

    class Meta:
        model = Product
        fields = ["name", "price", "guild"]


class _BaseProductSplitFormSet(BaseInlineFormSet):
    """Validates: >=1 active row, sum=100, no duplicates, recipient_type/guild rules."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return  # let per-form errors surface first

        active_rows = [
            f.cleaned_data for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE", False)
        ]
        if not active_rows:
            raise forms.ValidationError("At least one revenue split row is required.")

        # Sum to 100
        total = sum((row["percent"] for row in active_rows), _Decimal("0"))
        if total != _Decimal("100"):
            raise forms.ValidationError(
                f"Revenue splits must sum to 100% — currently {total}%."
            )

        # recipient_type / guild consistency + duplicate detection
        seen_admin = False
        seen_guilds = set()
        for row in active_rows:
            rtype = row["recipient_type"]
            guild = row.get("guild")
            if rtype == ProductRevenueSplit.RecipientType.ADMIN:
                if guild is not None:
                    raise forms.ValidationError("Admin rows must not select a guild.")
                if seen_admin:
                    raise forms.ValidationError("Only one Admin row is allowed per product.")
                seen_admin = True
            elif rtype == ProductRevenueSplit.RecipientType.GUILD:
                if guild is None:
                    raise forms.ValidationError("Guild rows must select a guild.")
                if guild.pk in seen_guilds:
                    raise forms.ValidationError(
                        f"Guild '{guild.name}' appears more than once. Each guild may only appear in one split row."
                    )
                seen_guilds.add(guild.pk)


ProductRevenueSplitFormSet = inlineformset_factory(
    Product,
    ProductRevenueSplit,
    formset=_BaseProductSplitFormSet,
    fields=["recipient_type", "guild", "percent"],
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


def build_product_split_formset(*, data=None, instance=None, prefix: str = "splits"):
    """Convenience constructor used by views and tests so the prefix is consistent."""
    return ProductRevenueSplitFormSet(data=data, instance=instance, prefix=prefix)
```

- [ ] **Step 4: Run the spec**

Run: `.venv/bin/pytest billing/spec/forms/product_form_spec.py -v`
Expected: all 9 tests pass. Fix any failures by adjusting form code.

- [ ] **Step 5: Suggested commit**

```
feat(billing): add ProductForm + revenue-split formset with validation
```

---

## Task 6: Replace the inline modal template with always-visible inline form

**Files:**
- Modify: `templates/admin/membership/guild_product_inline.html` — remove modal, add inline form with Alpine dynamic split rows + live preview
- Modify: `membership/admin.py` — `GuildProductInline` swap (use a custom add view, since the inline-formset for splits-of-products doesn't fit Django admin's nested-inline limitation)

> **Design note:** Django admin doesn't natively support nested inlines (Guild → Product → ProductRevenueSplit), AND HTML forbids nested `<form>` elements. The Django admin change-view wraps everything in a single `<form>`, so a nested "Add Product" `<form>` posting to a different URL won't work if rendered *inside* it.
>
> **Approach:** drop the `GuildProductInline` entirely. Override `GuildAdmin.change_form_template` to point at a custom template (`templates/admin/membership/guild/change_form.html`) that extends the default admin change form and **adds the products section AFTER `{% block content %}`'s closing `</form>`** (use `{% block after_field_sets %}` is inside the form — instead use a position outside, see step below). The products section then has its own standalone `<form method="post" action="...">` that posts to a dedicated view.
>
> Override `change_view()` to inject context vars (`existing_products`, `all_guilds`) used by the custom template.

- [ ] **Step 1: Add a route for the new view**

In `billing/urls.py` (find the existing patterns), add:

```python
path(
    "admin/products/add/<int:guild_id>/",
    views.admin_add_product_for_guild,
    name="billing_admin_add_product_for_guild",
),
path(
    "admin/products/<int:product_id>/delete/",
    views.admin_delete_product,
    name="billing_admin_delete_product",
),
```

(Adjust the import path to match the file's existing style.)

- [ ] **Step 2: Add the view in `billing/views.py`**

```python
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from billing.forms import ProductForm, build_product_split_formset
from billing.models import Product
from membership.models import Guild


@staff_member_required
@require_http_methods(["POST"])
def admin_add_product_for_guild(request: HttpRequest, guild_id: int) -> HttpResponse:
    """POST-only — accepts product fields + splits formset, redirects back to the guild change page."""
    guild = get_object_or_404(Guild, pk=guild_id)
    form = ProductForm(data=request.POST)
    formset = build_product_split_formset(data=request.POST, instance=Product())

    # Pre-bind guild on the unsaved instance so the formset's instance has the right FK
    if form.is_valid() and formset.is_valid():
        product = form.save(commit=False)
        product.guild = guild  # always force to the page's guild
        product.created_by = request.user
        product.save()
        formset.instance = product
        formset.save()
        messages.success(request, f"Added product '{product.name}'.")
    else:
        # Stash errors in session so the redirected page can re-render them
        request.session["_pending_product_form"] = {
            "post": dict(request.POST.lists()),
            "form_errors": form.errors.as_json(),
            "formset_errors": formset.errors,  # list of dicts
            "non_form_errors": list(formset.non_form_errors()),
        }
        messages.error(request, "Could not add product — see errors below.")

    return redirect(reverse("admin:membership_guild_change", args=[guild_id]))


@staff_member_required
@require_http_methods(["POST"])
def admin_delete_product(request: HttpRequest, product_id: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=product_id)
    guild_id = product.guild_id
    product.delete()
    messages.success(request, f"Deleted product '{product.name}'.")
    return redirect(reverse("admin:membership_guild_change", args=[guild_id]))
```

- [ ] **Step 3: Modify `membership/admin.py` — drop `GuildProductInline`, custom change_form**

In `membership/admin.py`:

1. Remove `GuildProductInline` from `GuildAdmin.inlines` (don't delete the class definition yet — wait until you confirm nothing else imports it via grep). After confirming nothing imports it, delete the class.

2. Set `GuildAdmin.change_form_template = "admin/membership/guild/change_form.html"`.

3. Override `change_view`:

```python
from billing.models import Product, ProductRevenueSplit  # add to imports

class GuildAdmin(admin.ModelAdmin):
    # ... existing class config ...
    change_form_template = "admin/membership/guild/change_form.html"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        guild = self.get_object(request, object_id)
        if guild is not None:
            extra_context["existing_products"] = (
                Product.objects.filter(guild=guild)
                .prefetch_related("splits__guild")
                .order_by("name")
            )
            extra_context["all_guilds"] = type(guild).objects.order_by("name")
            extra_context["editing_guild"] = guild
        return super().change_view(request, object_id, form_url, extra_context)
```

- [ ] **Step 4: Create the custom change_form template**

Delete the old `templates/admin/membership/guild_product_inline.html` (it's no longer used because we removed the inline).

Create `templates/admin/membership/guild/change_form.html`:

```django
{% extends "admin/change_form.html" %}
{% load i18n admin_urls %}

{% block after_field_sets %}{{ block.super }}
    {# Inside the admin form — render the read-only products list here as a fieldset. #}
    {% if editing_guild %}
    <fieldset class="module aligned">
        <h2>Products</h2>
        {% if existing_products %}
        <table class="pl-products-table">
            <thead>
                <tr><th>Name</th><th>Price</th><th>Revenue split</th></tr>
            </thead>
            <tbody>
                {% for product in existing_products %}
                <tr>
                    <td>{{ product.name }}</td>
                    <td>${{ product.price }}</td>
                    <td>
                        {% for split in product.splits.all %}
                            {% if split.recipient_type == "admin" %}Admin{% else %}{{ split.guild.name }}{% endif %} {{ split.percent }}%{% if not forloop.last %} · {% endif %}
                        {% endfor %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p class="pl-products-empty">No products yet. Add one below.</p>
        {% endif %}
    </fieldset>
    {% endif %}
{% endblock %}

{% block after_related_objects %}{{ block.super }}
    {# OUTSIDE the admin form — both the delete-product forms and the add-product form must live
       outside the wrapping <form> that the admin change view emits, since HTML forbids nested forms. #}
    {% if editing_guild %}

    {# Delete buttons (one tiny POST form per product) #}
    {% if existing_products %}
    <div class="pl-products-actions">
        <h3>Delete a product</h3>
        {% for product in existing_products %}
            <form method="post" action="{% url 'billing_admin_delete_product' product.pk %}" style="display:inline-block; margin-right:0.5rem;" onsubmit="return confirm('Delete {{ product.name|escapejs }}?');">
                {% csrf_token %}
                <button type="submit" class="pl-product-btn pl-product-btn--delete">Delete {{ product.name }}</button>
            </form>
        {% endfor %}
    </div>
    {% endif %}

    {# Add product form — separate standalone <form> #}
    {% include "admin/billing/_inline_product_form.html" with guild=editing_guild all_guilds=all_guilds %}
    {% endif %}
{% endblock %}
```

> **Block name caveat:** Django admin's `change_form.html` exposes `after_field_sets` (inside the form, after the model fields) and `after_related_objects` (after inlines, but still inside the form in default admin). To get content **outside** the form you may need to extend even further — wrap the include in a `{% block content %}{{ block.super }}<div>...</div>{% endblock %}` instead. **Verify by viewing source in the browser** that the add-product `<form>` element is NOT nested inside the admin's `<form id="guild_form">`. If it is, move it to override `{% block content %}` and append after `{{ block.super }}` (which closes the admin form before any extra content).

- [ ] **Step 5: Add the inline product form template**

Create `templates/admin/billing/_inline_product_form.html`:

```django
{% load static %}
{# Inline Add Product form — Alpine.js drives the dynamic split rows + preview. #}

<div class="pl-add-product-form" x-data="productSplitForm({
        guildId: {{ guild.pk }},
        guildName: '{{ guild.name|escapejs }}',
        recipients: [
            { value: 'admin', label: 'Admin', type: 'admin', guildId: null },
            {% for g in all_guilds %}
            { value: 'guild:{{ g.pk }}', label: '{{ g.name|escapejs }}', type: 'guild', guildId: {{ g.pk }} },
            {% endfor %}
        ],
        defaults: [
            { recipient: 'admin', percent: 20 },
            { recipient: 'guild:{{ guild.pk }}', percent: 80 }
        ],
        price: 0
     })">

    <h4>Add a product</h4>

    <form method="post" action="{% url 'billing_admin_add_product_for_guild' guild.pk %}">
        {% csrf_token %}

        <div class="pl-add-product-row">
            <label>Name <input type="text" name="name" required></label>
            <label>Price $<input type="number" step="0.01" min="0.01" name="price" x-model.number="price" required></label>
            <input type="hidden" name="guild" value="{{ guild.pk }}">
        </div>

        <fieldset class="pl-splits-fieldset">
            <legend>Revenue Split — must sum to 100%</legend>

            <input type="hidden" name="splits-TOTAL_FORMS" :value="rows.length">
            <input type="hidden" name="splits-INITIAL_FORMS" value="0">
            <input type="hidden" name="splits-MIN_NUM_FORMS" value="1">
            <input type="hidden" name="splits-MAX_NUM_FORMS" value="1000">

            <table class="pl-splits-table">
                <thead><tr><th>Recipient</th><th>Percent</th><th></th></tr></thead>
                <tbody>
                    <template x-for="(row, i) in rows" :key="i">
                        <tr>
                            <td>
                                <select :name="`splits-${i}-recipient_type`" x-model="row.recipientType" x-init="$nextTick(() => syncRow(i))" hidden></select>
                                <select :name="`splits-${i}-guild`" x-model="row.guildId" hidden></select>

                                <select x-model="row.recipient" @change="syncRow(i)">
                                    <template x-for="r in recipients" :key="r.value">
                                        <option :value="r.value" :disabled="isPicked(r.value, i)" x-text="r.label"></option>
                                    </template>
                                </select>
                            </td>
                            <td>
                                <input type="number" step="0.01" min="0.01" max="100"
                                       :name="`splits-${i}-percent`"
                                       x-model.number="row.percent"
                                       required>%
                            </td>
                            <td>
                                <button type="button" @click="rows.splice(i, 1)" aria-label="Remove">&times;</button>
                            </td>
                        </tr>
                    </template>
                </tbody>
            </table>

            <button type="button" @click="addRow()" :disabled="!hasUnpickedRecipient()">+ Add recipient</button>

            <p class="pl-splits-preview" x-show="price > 0">
                Live preview: $<span x-text="price.toFixed(2)"></span> →
                <template x-for="(row, i) in rows" :key="i">
                    <span><span x-text="recipientLabel(row.recipient)"></span> $<span x-text="((price * row.percent) / 100).toFixed(2)"></span><span x-show="i < rows.length - 1">, </span></span>
                </template>
            </p>

            <p :class="{'pl-splits-total': true, 'pl-splits-total--ok': totalPercent === 100, 'pl-splits-total--bad': totalPercent !== 100}">
                Total: <span x-text="totalPercent"></span>% <span x-text="totalPercent === 100 ? '✓' : '✗'"></span>
            </p>
        </fieldset>

        <div class="pl-add-product-actions">
            <button type="submit" class="pl-btn pl-btn--primary" :disabled="!canSave()">Save Product</button>
            <button type="reset" class="pl-btn pl-btn--secondary" @click="rows = JSON.parse(JSON.stringify(defaults)); $nextTick(() => rows.forEach((_, i) => syncRow(i)))">Cancel</button>
        </div>
    </form>
</div>

<script>
function productSplitForm({ guildId, guildName, recipients, defaults, price }) {
    return {
        recipients,
        defaults,
        price,
        rows: JSON.parse(JSON.stringify(defaults)),

        init() {
            this.rows.forEach((_, i) => this.syncRow(i));
        },

        get totalPercent() {
            return this.rows.reduce((sum, r) => sum + (parseFloat(r.percent) || 0), 0);
        },

        recipientLabel(value) {
            const r = this.recipients.find(x => x.value === value);
            return r ? r.label : '?';
        },

        isPicked(value, ownIdx) {
            return this.rows.some((r, i) => i !== ownIdx && r.recipient === value);
        },

        hasUnpickedRecipient() {
            return this.recipients.some(r => !this.rows.some(row => row.recipient === r.value));
        },

        addRow() {
            const next = this.recipients.find(r => !this.rows.some(row => row.recipient === r.value));
            if (!next) return;
            this.rows.push({ recipient: next.value, percent: 0 });
            this.$nextTick(() => this.syncRow(this.rows.length - 1));
        },

        syncRow(i) {
            const row = this.rows[i];
            const r = this.recipients.find(x => x.value === row.recipient);
            if (!r) return;
            row.recipientType = r.type;
            row.guildId = r.guildId == null ? '' : String(r.guildId);
        },

        canSave() {
            return this.totalPercent === 100 && this.rows.length >= 1 && this.rows.every(r => r.percent > 0);
        }
    };
}
</script>
```

- [ ] **Step 6: Confirm the wiring**

The `change_view` override from Step 3 already injects `existing_products`, `all_guilds`, and `editing_guild` into the template context. No further wiring needed.

- [ ] **Step 7: Smoke test in browser**

```bash
.venv/bin/python manage.py runserver
```
Visit `http://127.0.0.1:8000/admin/membership/guild/<some-guild-id>/change/`. Expected:
- Existing products list (none, since wiped) shows "No products yet."
- "Add a product" form below with name, price, two default split rows (Admin 20% / `<guild name>` 80%).
- Adding a row, removing a row, and changing percent updates the live preview and total badge.
- Submitting valid data lands you back on the guild page with the product listed; total = 100%; can buy.
- Submitting invalid (sum != 100) re-renders with errors (currently via Django messages — TODO note: error display can be polished in a follow-up).

If the JavaScript is broken, fix it before moving on. (Open browser dev console.)

- [ ] **Step 8: Suggested commit**

```
feat(billing): inline product form on guild admin page (Alpine dynamic splits)
```

---

## Task 7: Rewrite `TabItemForm` for splits + custom-entry view

**Files:**
- Modify: `billing/forms.py` — restore `TabItemForm` with a splits formset for custom entries
- Modify: `billing/views.py` — `admin_add_tab_entry` accepts the new form
- Modify any template that renders `TabItemForm` (search the codebase)
- Create/update: `tests/billing/forms_spec.py`

- [ ] **Step 1: Restore `TabItemForm` with a splits formset**

Open `billing/forms.py`. Replace the stubbed `TabItemForm` with the new shape. Keep the three contexts (`member_guild_page`, `member_tab_page`, `admin_dashboard`) — only the split fields change.

```python
class TabItemForm(forms.Form):
    """See module docstring. Splits are handled by an attached
    ``ProductRevenueSplitFormSet``-like child formset for custom entries.

    For *product* entries (``product`` selected), the splits come from the
    product itself — no formset needed.
    """

    description = forms.CharField(max_length=500)
    amount = forms.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))
    member = forms.ModelChoiceField(queryset=Member.objects.all(), required=False)
    product = forms.ModelChoiceField(queryset=Product.objects.all(), required=False)
    guild = forms.ModelChoiceField(queryset=Guild.objects.all(), required=False)

    def __init__(self, *args, context: str, user=None, default_guild=None, **kwargs):
        super().__init__(*args, **kwargs)
        if context not in VALID_CONTEXTS:
            raise ValueError(f"Unknown TabItemForm context: {context}")
        self.context = context
        self.user = user
        self.default_guild = default_guild

        # Hide member picker outside admin context
        if context != CONTEXT_ADMIN_DASHBOARD:
            self.fields.pop("member", None)
        if context == CONTEXT_MEMBER_GUILD_PAGE:
            self.fields.pop("guild", None)  # fixed via default_guild

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        if product is None and self.context == CONTEXT_MEMBER_GUILD_PAGE:
            # Members on a guild page must pick a product
            raise forms.ValidationError("Please pick a product.")
        return cleaned

    def save(self, *, tab, splits: list[dict[str, Any]] | None = None) -> "TabEntry":
        product = self.cleaned_data.get("product")
        if product is None and splits is None:
            raise ValueError("Custom entries (no product) require explicit splits.")
        return tab.add_entry(
            description=self.cleaned_data["description"],
            amount=self.cleaned_data["amount"],
            added_by=self.user,
            is_self_service=(self.context != CONTEXT_ADMIN_DASHBOARD),
            product=product,
            splits=splits,
        )
```

- [ ] **Step 2: Build a custom-entry splits formset**

In `billing/forms.py`, add a non-model formset for custom entries (since it's not bound to any DB model — just produces split dicts):

```python
class _SplitRowForm(forms.Form):
    recipient_type = forms.ChoiceField(choices=ProductRevenueSplit.RecipientType.choices)
    guild = forms.ModelChoiceField(queryset=Guild.objects.all(), required=False)
    percent = forms.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0.01"), max_value=Decimal("100"))


class _BaseCustomSplitFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE", False)]
        if not active:
            raise forms.ValidationError("At least one split row is required.")
        total = sum((row["percent"] for row in active), Decimal("0"))
        if total != Decimal("100"):
            raise forms.ValidationError(f"Splits must sum to 100% — currently {total}%.")
        seen_admin = False
        seen_guilds = set()
        for row in active:
            rtype = row["recipient_type"]
            guild = row.get("guild")
            if rtype == ProductRevenueSplit.RecipientType.ADMIN:
                if guild is not None:
                    raise forms.ValidationError("Admin rows must not select a guild.")
                if seen_admin:
                    raise forms.ValidationError("Only one Admin row is allowed.")
                seen_admin = True
            else:
                if guild is None:
                    raise forms.ValidationError("Guild rows must select a guild.")
                if guild.pk in seen_guilds:
                    raise forms.ValidationError(f"Guild '{guild.name}' appears more than once.")
                seen_guilds.add(guild.pk)

    def to_split_dicts(self) -> list[dict[str, Any]]:
        out = []
        for f in self.forms:
            if not f.cleaned_data or f.cleaned_data.get("DELETE"):
                continue
            out.append({
                "recipient_type": f.cleaned_data["recipient_type"],
                "guild": f.cleaned_data.get("guild"),
                "percent": f.cleaned_data["percent"],
            })
        return out


CustomSplitFormSet = forms.formset_factory(
    _SplitRowForm,
    formset=_BaseCustomSplitFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
```

- [ ] **Step 3: Update `admin_add_tab_entry` view**

In `billing/views.py`, find `admin_add_tab_entry` (lines ~252–273). Update to wire in the splits formset:

```python
@staff_member_required
@require_http_methods(["POST"])
def admin_add_tab_entry(request: HttpRequest) -> HttpResponse:
    from billing.forms import CONTEXT_ADMIN_DASHBOARD, CustomSplitFormSet, TabItemForm

    form = TabItemForm(data=request.POST, context=CONTEXT_ADMIN_DASHBOARD, user=request.user)
    if not form.is_valid():
        messages.error(request, "Invalid entry — see errors.")
        return redirect(request.META.get("HTTP_REFERER", reverse("billing_admin_dashboard")))

    member = form.cleaned_data["member"]
    if not hasattr(member, "tab"):
        Tab.objects.create(member=member)
    tab = member.tab

    product = form.cleaned_data.get("product")
    if product is not None:
        # Splits come from the product
        form.save(tab=tab)
    else:
        # Custom entry — splits formset required
        splits_formset = CustomSplitFormSet(data=request.POST, prefix="splits")
        if not splits_formset.is_valid():
            messages.error(request, f"Invalid splits: {splits_formset.non_form_errors()}")
            return redirect(request.META.get("HTTP_REFERER", reverse("billing_admin_dashboard")))
        form.save(tab=tab, splits=splits_formset.to_split_dicts())

    messages.success(request, "Entry added.")
    return redirect(request.META.get("HTTP_REFERER", reverse("billing_admin_dashboard")))
```

- [ ] **Step 4: Update the admin "add tab entry" template to render the splits formset**

Find the template that renders `TabItemForm` for the admin dashboard. It's likely `templates/billing/admin_dashboard.html` or `templates/billing/admin_add_entry.html` (search to confirm).

For the **product-selected** path: no formset needed.
For the **custom (no product)** path: render the same Alpine `productSplitForm` widget from Task 6, but with `defaults: [{ recipient: 'admin', percent: 100 }]` and posting prefixed `splits-N-...` fields. Reuse the include `admin/billing/_inline_product_form.html`'s split section by extracting it into a partial `admin/billing/_split_rows_widget.html` if you want DRY (recommended).

Show/hide the formset based on whether `product` is selected (Alpine `x-show="!productSelected"`).

- [ ] **Step 5: Update `tests/billing/forms_spec.py`**

Uncomment / rewrite the `TabItemForm` tests to drop `admin_percent` / `split_equally` references. Add a few coverage tests for the new shape:

```python
from decimal import Decimal

import pytest

from billing.forms import (
    CONTEXT_ADMIN_DASHBOARD,
    CONTEXT_MEMBER_GUILD_PAGE,
    CustomSplitFormSet,
    TabItemForm,
)
from billing.models import TabEntrySplit
from tests.billing.factories import ProductFactory, TabFactory
from tests.membership.factories import GuildFactory, MemberFactory


def describe_TabItemForm():
    def describe_save_with_product():
        def it_creates_an_entry_with_product_splits(db):
            product = ProductFactory()
            tab = TabFactory()
            form = TabItemForm(
                data={"description": "x", "amount": "10.00", "product": product.pk, "member": tab.member.pk},
                context=CONTEXT_ADMIN_DASHBOARD,
            )
            assert form.is_valid(), form.errors
            entry = form.save(tab=tab)
            assert entry.splits.count() == 2

    def describe_save_with_custom_splits():
        def it_creates_an_entry_with_explicit_splits(db):
            tab = TabFactory()
            g = GuildFactory()
            form = TabItemForm(
                data={"description": "custom", "amount": "10.00", "member": tab.member.pk},
                context=CONTEXT_ADMIN_DASHBOARD,
            )
            assert form.is_valid(), form.errors
            entry = form.save(
                tab=tab,
                splits=[
                    {"recipient_type": "admin", "guild": None, "percent": Decimal("100")},
                ],
            )
            assert entry.splits.count() == 1
            only = entry.splits.first()
            assert only.recipient_type == TabEntrySplit.RecipientType.ADMIN

    def describe_custom_split_formset():
        def it_rejects_when_sum_not_100(db):
            data = {
                "splits-TOTAL_FORMS": "1",
                "splits-INITIAL_FORMS": "0",
                "splits-MIN_NUM_FORMS": "1",
                "splits-MAX_NUM_FORMS": "1000",
                "splits-0-recipient_type": "admin",
                "splits-0-percent": "50",
            }
            fs = CustomSplitFormSet(data=data, prefix="splits")
            assert not fs.is_valid()
```

- [ ] **Step 6: Run the new spec**

Run: `.venv/bin/pytest tests/billing/forms_spec.py billing/spec/forms/ -v`
Expected: all pass.

- [ ] **Step 7: Suggested commit**

```
feat(billing): TabItemForm + custom-entry splits formset
```

---

## Task 8: Rewrite `build_report` against `TabEntrySplit`

**Files:**
- Modify: `billing/reports.py` — replace stubbed body
- Modify: `tests/billing/reports_spec.py` — uncomment and update

- [ ] **Step 1: Write the failing tests for the new report shape**

Update `tests/billing/reports_spec.py`:

```python
from decimal import Decimal

import pytest
from django.utils import timezone

from billing.models import TabCharge
from billing.reports import build_report
from tests.billing.factories import ProductFactory, TabFactory
from tests.membership.factories import GuildFactory


def describe_build_report():
    def it_returns_one_row_per_TabEntrySplit(db):
        product = ProductFactory()  # default 20/80 split
        tab = TabFactory()
        tab.add_entry(description="x", amount=Decimal("10.00"), product=product)
        rows, payouts, admin_total = build_report()
        assert len(rows) == 2
        assert admin_total == Decimal("2.00")
        assert sum((r.amount for r in rows), Decimal("0")) == Decimal("10.00")

    def it_aggregates_payouts_per_recipient(db):
        product = ProductFactory()
        tab = TabFactory()
        tab.add_entry(description="x", amount=Decimal("10.00"), product=product)
        tab.add_entry(description="y", amount=Decimal("10.00"), product=product)
        rows, payouts, admin_total = build_report()
        # One payout row per recipient (admin + the owning guild)
        assert len(payouts) == 2
        admin_payout = next(p for p in payouts if p.recipient_type == "admin")
        guild_payout = next(p for p in payouts if p.recipient_type == "guild")
        assert admin_payout.amount == Decimal("4.00")
        assert guild_payout.amount == Decimal("16.00")
        assert guild_payout.entry_count == 2

    def it_excludes_voided_entries(db, django_user_model):
        product = ProductFactory()
        tab = TabFactory()
        e = tab.add_entry(description="x", amount=Decimal("10.00"), product=product)
        voider = django_user_model.objects.create_user(username="voider", password="x")
        e.void(user=voider, reason="oops")
        rows, payouts, admin_total = build_report()
        assert rows == []
        assert payouts == []
        assert admin_total == Decimal("0")

    def it_filters_by_recipient_guild(db):
        g1 = GuildFactory()
        g2 = GuildFactory()
        p1 = ProductFactory(guild=g1)
        p2 = ProductFactory(guild=g2)
        tab = TabFactory()
        tab.add_entry(description="x", amount=Decimal("10.00"), product=p1)
        tab.add_entry(description="y", amount=Decimal("10.00"), product=p2)
        rows, payouts, admin_total = build_report(guild_ids=[g1.pk])
        recipient_guild_ids = {r.guild_id for r in rows if r.recipient_type == "guild"}
        assert recipient_guild_ids == {g1.pk}
```

- [ ] **Step 2: Rewrite `billing/reports.py`**

Replace the stubbed `build_report` and the `ReportRow` / `PayoutRow` dataclasses:

```python
from billing.models import TabCharge, TabEntry, TabEntrySplit
from membership.models import Guild


@dataclass(frozen=True)
class ReportRow:
    created_at: datetime
    member_name: str
    description: str
    recipient_type: str          # "admin" | "guild"
    recipient_label: str         # "Admin" or guild name
    guild_id: int | None
    amount: Decimal              # this recipient's share
    percent: Decimal
    entry_amount: Decimal        # the parent entry's full amount
    charge_status: str
    charge_type: str             # "product" | "custom"


@dataclass(frozen=True)
class PayoutRow:
    recipient_type: str          # "admin" | "guild"
    recipient_label: str
    guild_id: int | None
    entry_count: int             # distinct entries that paid this recipient
    amount: Decimal


def build_report(
    *,
    start_date: date_cls | None = None,
    end_date: date_cls | None = None,
    guild_ids: list[int] | None = None,
    charge_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[ReportRow], list[PayoutRow], Decimal]:
    """Return (rows, payout_summary, admin_total) sourced from TabEntrySplit."""
    qs: QuerySet[TabEntrySplit] = (
        TabEntrySplit.objects.all()
        .select_related("entry__tab__member", "entry__tab_charge", "entry__product", "guild")
        .filter(entry__voided_at__isnull=True)
        .order_by("entry__created_at", "entry_id", "id")
    )
    if start_date:
        qs = qs.filter(entry__created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(entry__created_at__date__lte=end_date)

    if guild_ids:
        # Only show guild splits that match the requested guilds.
        # Admin splits for matching entries are still included.
        qs = qs.filter(
            Q(recipient_type=TabEntrySplit.RecipientType.GUILD, guild_id__in=guild_ids)
            | Q(recipient_type=TabEntrySplit.RecipientType.ADMIN, entry__splits__guild_id__in=guild_ids)
        ).distinct()

    if charge_types:
        if "product" in charge_types and "custom" not in charge_types:
            qs = qs.filter(entry__product__isnull=False)
        elif "custom" in charge_types and "product" not in charge_types:
            qs = qs.filter(entry__product__isnull=True)

    if statuses:
        status_q = Q()
        if "pending" in statuses:
            status_q |= Q(entry__tab_charge__isnull=True)
        other = [s for s in statuses if s != "pending"]
        if other:
            status_q |= Q(entry__tab_charge__status__in=other)
        qs = qs.filter(status_q)

    rows: list[ReportRow] = []
    payouts: dict[tuple[str, int | None], PayoutRow] = {}
    admin_total = _ZERO

    for split in qs.iterator(chunk_size=500):
        entry = split.entry
        charge_status = entry.tab_charge.status if entry.tab_charge_id else "pending"
        charge_type = "product" if entry.product_id else "custom"
        recipient_label = "Admin" if split.recipient_type == TabEntrySplit.RecipientType.ADMIN else (split.guild.name if split.guild_id else "?")

        rows.append(ReportRow(
            created_at=entry.created_at,
            member_name=entry.tab.member.display_name,
            description=entry.description,
            recipient_type=split.recipient_type,
            recipient_label=recipient_label,
            guild_id=split.guild_id,
            amount=split.amount,
            percent=split.percent,
            entry_amount=entry.amount,
            charge_status=charge_status,
            charge_type=charge_type,
        ))

        if split.recipient_type == TabEntrySplit.RecipientType.ADMIN:
            admin_total += split.amount

        key = (split.recipient_type, split.guild_id)
        existing = payouts.get(key)
        if existing is None:
            payouts[key] = PayoutRow(
                recipient_type=split.recipient_type,
                recipient_label=recipient_label,
                guild_id=split.guild_id,
                entry_count=1,
                amount=split.amount,
            )
        else:
            payouts[key] = PayoutRow(
                recipient_type=split.recipient_type,
                recipient_label=recipient_label,
                guild_id=split.guild_id,
                entry_count=existing.entry_count + 1,
                amount=existing.amount + split.amount,
            )

    payout_list = sorted(
        payouts.values(),
        key=lambda p: (0 if p.recipient_type == "admin" else 1, p.recipient_label),
    )
    return rows, payout_list, admin_total
```

Update CSV export at the bottom of `billing/reports.py` to use the new field names (`recipient_label`, `recipient_type`, `amount` instead of `guild_amount`/`admin_amount`).

- [ ] **Step 3: Run the spec**

Run: `.venv/bin/pytest tests/billing/reports_spec.py -v`
Expected: all 4 tests pass.

- [ ] **Step 4: Suggested commit**

```
feat(billing): rebuild reports against TabEntrySplit table
```

---

## Task 9: Update reports template

**Files:**
- Modify: `templates/billing/admin_reports.html`

- [ ] **Step 1: Update the entries-table header**

Find the entries-table header (lines ~134–146 in the original). Replace columns:
- `Guild` → `Recipient` (renders `row.recipient_label`)
- Add `%` column (renders `row.percent`)
- Replace `Admin amount` / `Guild amount` columns with single `Amount` column (renders `row.amount`)

Update the per-row template to match.

- [ ] **Step 2: Update the payout-summary table**

The summary now includes both Admin and per-guild rows. Update header to: `Recipient | Entries | Amount`. Iterate `payout_summary` directly — each row has `recipient_label`, `entry_count`, `amount`.

Remove the separate "Admin total" callout if present (now folded into the payout summary).

- [ ] **Step 3: Update the recipient filter**

If the existing filter has a `Guild` dropdown (probably `<select name="guild_ids" multiple>`), rename it to `Recipient` and ensure the queryset includes a virtual "Admin" entry. Or keep filtering by guild only and add a separate "include admin" toggle.

Simplest: leave the guild multi-select as-is; admin always shows.

- [ ] **Step 4: Smoke test**

Visit `/billing/admin/dashboard/` → Reports tab. Add a product, charge a tab entry, view the report. Confirm rows and payout summary look right.

- [ ] **Step 5: Suggested commit**

```
feat(billing): update reports template to show recipient breakdown
```

---

## Task 10: Show split summary on guild detail page

**Files:**
- Modify: `templates/hub/guild_detail.html`

- [ ] **Step 1: Locate the product list section**

Search for the loop over `guild.products` in `templates/hub/guild_detail.html`.

- [ ] **Step 2: Render split summary inline**

For each product, render the splits as a comma-separated list. Add a small helper template tag if the project uses any, or inline it:

```django
{% for product in guild.products.all %}
    <li class="pl-product-card">
        <strong>{{ product.name }}</strong> — ${{ product.price }}
        <small class="pl-product-splits">
            {% for split in product.splits.all %}
                {% if split.recipient_type == "admin" %}Admin{% else %}{{ split.guild.name }}{% endif %} {{ split.percent }}%{% if not forloop.last %} · {% endif %}
            {% endfor %}
        </small>
        ...
    </li>
{% endfor %}
```

To avoid N+1 queries on this page, ensure the view that renders `guild_detail.html` does `Guild.objects.prefetch_related("products__splits__guild")` for the relevant guild.

- [ ] **Step 3: Verify the prefetch in the view**

Open `hub/views.py` and find the guild detail view. Add or confirm:

```python
guild = get_object_or_404(
    Guild.objects.prefetch_related("products__splits__guild"),
    pk=guild_id,
)
```

- [ ] **Step 4: Smoke test**

Visit `/guilds/<some-guild-id>/`. Confirm each product shows its split breakdown.

- [ ] **Step 5: Suggested commit**

```
feat(hub): show product split summary on guild detail page
```

---

## Task 11: View test for the inline guild admin product form

**Files:**
- Create: `billing/spec/views/guild_admin_product_form_spec.py`

- [ ] **Step 1: Write the spec**

```python
from decimal import Decimal

import pytest
from django.urls import reverse

from billing.models import Product, ProductRevenueSplit
from tests.membership.factories import GuildFactory


def _staff_client(client, db, django_user_model):
    user = django_user_model.objects.create_user(username="staff", password="x", is_staff=True, is_superuser=True)
    client.force_login(user)
    return client


def describe_admin_add_product_for_guild():
    def it_creates_a_product_and_splits_on_valid_post(db, client, django_user_model):
        client = _staff_client(client, db, django_user_model)
        guild = GuildFactory()
        url = reverse("billing_admin_add_product_for_guild", args=[guild.pk])
        data = {
            "name": "Test Bag",
            "price": "12.00",
            "guild": str(guild.pk),
            "splits-TOTAL_FORMS": "2",
            "splits-INITIAL_FORMS": "0",
            "splits-MIN_NUM_FORMS": "1",
            "splits-MAX_NUM_FORMS": "1000",
            "splits-0-recipient_type": "admin",
            "splits-0-guild": "",
            "splits-0-percent": "20",
            "splits-1-recipient_type": "guild",
            "splits-1-guild": str(guild.pk),
            "splits-1-percent": "80",
        }
        response = client.post(url, data=data)
        assert response.status_code == 302
        assert Product.objects.count() == 1
        product = Product.objects.first()
        assert product.guild == guild
        assert product.splits.count() == 2

    def it_rejects_invalid_sum_and_does_not_create(db, client, django_user_model):
        client = _staff_client(client, db, django_user_model)
        guild = GuildFactory()
        url = reverse("billing_admin_add_product_for_guild", args=[guild.pk])
        data = {
            "name": "x",
            "price": "10.00",
            "guild": str(guild.pk),
            "splits-TOTAL_FORMS": "2",
            "splits-INITIAL_FORMS": "0",
            "splits-MIN_NUM_FORMS": "1",
            "splits-MAX_NUM_FORMS": "1000",
            "splits-0-recipient_type": "admin",
            "splits-0-guild": "",
            "splits-0-percent": "20",
            "splits-1-recipient_type": "guild",
            "splits-1-guild": str(guild.pk),
            "splits-1-percent": "70",
        }
        response = client.post(url, data=data)
        assert response.status_code == 302
        assert Product.objects.count() == 0


def describe_admin_delete_product():
    def it_deletes_the_product_and_redirects(db, client, django_user_model):
        client = _staff_client(client, db, django_user_model)
        guild = GuildFactory()
        # Create product directly so the test doesn't depend on factory defaults
        product = Product.objects.create(name="x", price=Decimal("5.00"), guild=guild)
        ProductRevenueSplit.objects.create(
            product=product, recipient_type="admin", guild=None, percent=Decimal("100"),
        )
        url = reverse("billing_admin_delete_product", args=[product.pk])
        response = client.post(url)
        assert response.status_code == 302
        assert Product.objects.count() == 0
```

- [ ] **Step 2: Run the spec**

Run: `.venv/bin/pytest billing/spec/views/guild_admin_product_form_spec.py -v`
Expected: all 3 tests pass.

- [ ] **Step 3: Suggested commit**

```
test(billing): cover inline product form view
```

---

## Task 12: Cleanup pass — re-enable / delete remaining commented specs

**Files:**
- Various test files commented in Task 3

- [ ] **Step 1: Find all `TODO(splits)` markers**

```bash
grep -rn 'TODO(splits)' tests/
```

- [ ] **Step 2: For each marked block**

Decide one of:
- **Delete** if the test was specifically for legacy behaviour (e.g. SPLIT_EQUALLY across all active guilds) that no longer exists.
- **Rewrite** if the test covers behaviour that still applies (e.g. tab limit checks, voiding) — uncomment, update field references to the new shape.

Don't leave any `TODO(splits)` markers in the tree.

- [ ] **Step 3: Run full suite + coverage**

```bash
.venv/bin/pytest -q --cov --cov-report=term-missing
```
Expected: all tests pass; coverage at the project's `fail_under` threshold (100%).

- [ ] **Step 4: Lint & format**

```bash
.venv/bin/ruff format .
.venv/bin/ruff check --fix .
```
Fix any remaining warnings.

- [ ] **Step 5: Suggested commit**

```
test(billing): re-enable cleaned-up legacy specs
```

---

## Task 13: Update `billing/CLAUDE.md`

**Files:**
- Modify: `billing/CLAUDE.md`

- [ ] **Step 1: Rewrite the affected sections**

Update the **Models** table:
- Remove `admin_percent_override`, `split_mode`, `is_active` from Product row
- Add a row for `ProductRevenueSplit` (product FK, recipient_type, guild FK nullable, percent)
- Remove `admin_percent`, `split_mode`, `guild`, `split_guild_ids` from TabEntry row
- Add a row for `TabEntrySplit` (entry FK, recipient_type, guild FK nullable, percent, amount)

Replace the **Revenue split** section with:

```markdown
## Revenue split

Each `Product` has 1+ `ProductRevenueSplit` rows that name a recipient (Admin or a Guild) and a percentage. Per-product percentages must sum to exactly 100%, validated in `ProductForm.clean()`.

When a `TabEntry` is created via `Tab.add_entry()`, the splits are frozen onto `TabEntrySplit` rows by `TabEntry.snapshot_splits()`. Reports SELECT directly from `TabEntrySplit` — never recomputed.

Penny rounding: each split's amount is `round(entry.amount * percent / 100, 2, ROUND_HALF_UP)`. The row with the largest percent absorbs the +/-1c remainder so the children sum exactly to the entry total.

Guild payouts are reconciled manually via the admin Reports page — no automated Stripe Connect transfers.
```

Replace the **Tab Flow** step 2:

```markdown
2. Entries accumulate via `Tab.add_entry()` (race-safe with `select_for_update`). Snapshots `TabEntrySplit` rows onto each entry.
```

Update the factories list in the last section to include `ProductRevenueSplitFactory` and `TabEntrySplitFactory`.

- [ ] **Step 2: Suggested commit**

```
docs(billing): update CLAUDE.md for the new revenue split model
```

---

## Task 14: Bump version + changelog

**Files:**
- Modify: `plfog/version.py`

- [ ] **Step 1: Bump VERSION and add changelog entry**

Open `plfog/version.py`. Bump:
- `VERSION = "1.7.0"` (was `"1.6.0"`)

Prepend a new entry to `CHANGELOG`:

```
1.7.0 — Flexible product revenue splits

Products can now split revenue across multiple guilds and admin in any
combination. For example, a product priced at $10 can be set up so that
20% goes to admin, 60% to the Ceramics Guild, and 20% to the Art Framing
Guild. The percentages have to add up to 100%, but otherwise you can
mix recipients however you like.

The Add Product form has been redesigned: it now appears inline on the
guild edit page (no more popup) with a live preview that shows exactly
how a sale will be divided up. The "active/inactive" toggle is gone —
if a product exists, it's available; if you delete it, it's gone.

Existing products and past tab entries were cleared during this upgrade.
You'll need to re-add your products with their new split configuration.
```

- [ ] **Step 2: Run full suite one last time**

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Expected: all pass.

- [ ] **Step 3: Suggested commit + PR creation**

```
chore: bump to 1.7.0 — product revenue splits
```

Then push the branch and open a PR. Body should mention:
- Link to the spec
- Highlight the destructive migration (0010 wipes Product/TabEntry/TabCharge)
- Pre-deploy step: back up DB on Hetzner and Render before merging

---

## End-of-plan verification

Before declaring done:

- [ ] `.venv/bin/pytest -q` — green
- [ ] `.venv/bin/ruff check .` — green
- [ ] `.venv/bin/ruff format --check .` — green
- [ ] Manual smoke: visit guild admin page, add a product with a 50/50 split, charge an entry, view it on the reports page
- [ ] Manual smoke: try invalid forms (sum != 100, duplicate guild) and confirm errors render
- [ ] No `TODO(splits)` markers remain in tests
- [ ] `git status` clean except for the version bump
