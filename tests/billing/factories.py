from __future__ import annotations

from decimal import Decimal

import factory
from django.utils import timezone

from billing.models import Invoice, MemberSubscription, Order, Payout, RevenueSplit, SubscriptionPlan
from tests.core.factories import UserFactory


class RevenueSplitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RevenueSplit

    name = factory.Sequence(lambda n: f"Split {n}")
    splits = [{"entity_type": "org", "entity_id": 1, "percentage": 100}]


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    description = "Test order"
    amount = 5000  # $50.00 in cents
    revenue_split = factory.SubFactory(RevenueSplitFactory)
    status = "on_tab"
    issued_at = factory.LazyFunction(timezone.now)


class InvoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invoice

    user = factory.SubFactory(UserFactory)
    stripe_invoice_id = factory.Sequence(lambda n: f"inv_{n}")
    amount_due = 5000
    amount_paid = 0
    status = "open"
    issued_at = factory.LazyFunction(timezone.now)


class PayoutFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payout

    payee_type = "user"
    payee_id = 1
    amount = 5000
    status = "pending"
    period_start = factory.LazyFunction(lambda: timezone.now().date())
    period_end = factory.LazyFunction(lambda: timezone.now().date())


class SubscriptionPlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubscriptionPlan

    name = factory.Sequence(lambda n: f"Plan {n}")
    price = Decimal("29.99")
    interval = "monthly"
    is_active = True


class MemberSubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MemberSubscription

    user = factory.SubFactory(UserFactory)
    subscription_plan = factory.SubFactory(SubscriptionPlanFactory)
    status = "active"
    starts_at = factory.LazyFunction(timezone.now)
