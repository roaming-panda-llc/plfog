from decimal import Decimal

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
            product=product,
            recipient_type="admin",
            guild=None,
            percent=Decimal("100"),
        )
        url = reverse("billing_admin_delete_product", args=[product.pk])
        response = client.post(url)
        assert response.status_code == 302
        assert Product.objects.count() == 0
