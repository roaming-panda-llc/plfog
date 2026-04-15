from decimal import Decimal

from billing.forms import (
    ProductForm,
    ProductRevenueSplitFormSet,  # noqa: F401  # re-exported for downstream test imports per plan
    build_product_split_formset,
)
from billing.models import Product, ProductRevenueSplit
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
                product_name="Test Bag",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
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
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
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
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
                splits=[],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_duplicate_admin_rows(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
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
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
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
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "guild", "guild_id": None, "percent": Decimal("100")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_an_admin_row_with_a_guild(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
                splits=[
                    {"recipient_type": "admin", "guild_id": owning_guild.pk, "percent": Decimal("100")},
                ],
            )
            formset = build_product_split_formset(data=data, instance=Product())
            assert not formset.is_valid()

        def it_rejects_zero_percent(db):
            owning_guild = GuildFactory()
            data = _post(
                product_name="x",
                price=Decimal("10.00"),
                owning_guild=owning_guild,
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
                product_name="Bag",
                price=Decimal("12.00"),
                owning_guild=owning_guild,
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
