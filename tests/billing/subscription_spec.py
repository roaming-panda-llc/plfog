"""Tests for SubscriptionPlan and MemberSubscription models."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from billing.models import MemberSubscription, SubscriptionPlan
from tests.billing.factories import MemberSubscriptionFactory, SubscriptionPlanFactory
from tests.core.factories import UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# SubscriptionPlan
# ---------------------------------------------------------------------------


def describe_SubscriptionPlan():
    def it_has_str_representation():
        plan = SubscriptionPlanFactory(name="Maker Plus", price=Decimal("49.99"), interval="monthly")
        assert str(plan) == "Maker Plus ($49.99/monthly)"

    def it_defaults_is_active_to_true():
        plan = SubscriptionPlanFactory()
        assert plan.is_active is True

    def it_can_be_deactivated():
        plan = SubscriptionPlanFactory(is_active=False)
        plan.refresh_from_db()
        assert plan.is_active is False

    def it_has_formatted_price():
        plan = SubscriptionPlanFactory(price=Decimal("29.99"))
        assert plan.formatted_price == "$29.99"

    def it_has_monthly_interval():
        plan = SubscriptionPlanFactory(interval=SubscriptionPlan.Interval.MONTHLY)
        plan.refresh_from_db()
        assert plan.interval == "monthly"

    def it_has_yearly_interval():
        plan = SubscriptionPlanFactory(interval=SubscriptionPlan.Interval.YEARLY)
        plan.refresh_from_db()
        assert plan.interval == "yearly"

    def it_has_stripe_price_id():
        plan = SubscriptionPlanFactory(stripe_price_id="price_1ABCxyz")
        plan.refresh_from_db()
        assert plan.stripe_price_id == "price_1ABCxyz"

    def it_has_plan_type():
        plan = SubscriptionPlanFactory(plan_type="studio")
        plan.refresh_from_db()
        assert plan.plan_type == "studio"

    def it_allows_blank_description():
        plan = SubscriptionPlanFactory(description="")
        assert plan.description == ""

    def it_stores_description():
        plan = SubscriptionPlanFactory(description="Full access to all studio spaces.")
        plan.refresh_from_db()
        assert plan.description == "Full access to all studio spaces."

    def it_orders_by_name():
        SubscriptionPlanFactory(name="Zeta Plan")
        SubscriptionPlanFactory(name="Alpha Plan")
        names = list(SubscriptionPlan.objects.values_list("name", flat=True))
        assert names == sorted(names)

    def it_formats_yearly_price_correctly():
        plan = SubscriptionPlanFactory(price=Decimal("299.00"), interval="yearly")
        assert plan.formatted_price == "$299.00"


# ---------------------------------------------------------------------------
# MemberSubscription
# ---------------------------------------------------------------------------


def describe_MemberSubscription():
    def it_has_str_representation():
        user = UserFactory(username="janesmith")
        plan = SubscriptionPlanFactory(name="Studio Basic")
        sub = MemberSubscriptionFactory(user=user, subscription_plan=plan, status="active")
        assert str(sub) == "janesmith - Studio Basic (active)"

    def it_is_active_when_status_active():
        sub = MemberSubscriptionFactory(status="active")
        assert sub.is_active is True

    def it_is_not_active_when_cancelled():
        sub = MemberSubscriptionFactory(status="cancelled")
        assert sub.is_active is False

    def it_is_not_active_when_past_due():
        sub = MemberSubscriptionFactory(status="past_due")
        assert sub.is_active is False

    def it_calculates_effective_price_without_discount():
        plan = SubscriptionPlanFactory(price=Decimal("50.00"))
        sub = MemberSubscriptionFactory(subscription_plan=plan, discount_percentage=None)
        assert sub.effective_price == Decimal("50.00")

    def it_calculates_effective_price_with_discount():
        plan = SubscriptionPlanFactory(price=Decimal("100.00"))
        sub = MemberSubscriptionFactory(subscription_plan=plan, discount_percentage=Decimal("20.00"))
        assert sub.effective_price == Decimal("80.00")

    def it_belongs_to_user():
        user = UserFactory()
        sub = MemberSubscriptionFactory(user=user)
        assert sub.user == user

    def it_belongs_to_plan():
        plan = SubscriptionPlanFactory(name="Premium")
        sub = MemberSubscriptionFactory(subscription_plan=plan)
        assert sub.subscription_plan == plan

    def it_defaults_status_to_active():
        user = UserFactory()
        plan = SubscriptionPlanFactory()
        from django.utils import timezone

        sub = MemberSubscription.objects.create(user=user, subscription_plan=plan, starts_at=timezone.now())
        assert sub.status == MemberSubscription.Status.ACTIVE

    def it_stores_stripe_subscription_id():
        sub = MemberSubscriptionFactory(stripe_subscription_id="sub_1XYZabc")
        sub.refresh_from_db()
        assert sub.stripe_subscription_id == "sub_1XYZabc"

    def it_orders_by_starts_at_descending():
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        user = UserFactory()
        plan = SubscriptionPlanFactory()
        older = MemberSubscriptionFactory(user=user, subscription_plan=plan, starts_at=now - timedelta(days=30))
        newer = MemberSubscriptionFactory(user=user, subscription_plan=plan, starts_at=now)
        subs = list(MemberSubscription.objects.filter(user=user))
        assert subs[0].pk == newer.pk
        assert subs[1].pk == older.pk

    def it_applies_partial_discount_correctly():
        plan = SubscriptionPlanFactory(price=Decimal("200.00"))
        sub = MemberSubscriptionFactory(subscription_plan=plan, discount_percentage=Decimal("10.00"))
        assert sub.effective_price == Decimal("180.00")


# ---------------------------------------------------------------------------
# Admin changelist views
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client():
    """Return a Django test client logged in as a superuser."""
    user = User.objects.create_superuser(
        username="sub-admin-test",
        password="sub-admin-pw",
        email="sub-admin@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


def describe_admin_subscription_plan_views():
    def it_loads_changelist(admin_client):
        SubscriptionPlanFactory(name="Admin Test Plan")
        resp = admin_client.get("/admin/billing/subscriptionplan/")
        assert resp.status_code == 200


def describe_admin_member_subscription_views():
    def it_loads_changelist(admin_client):
        MemberSubscriptionFactory()
        resp = admin_client.get("/admin/billing/membersubscription/")
        assert resp.status_code == 200
