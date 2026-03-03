from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import factory
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from membership.models import (
    Guild,
    GuildDocument,
    GuildMembership,
    GuildVote,
    GuildWishlistItem,
    Lease,
    Member,
    MemberSchedule,
    MembershipPlan,
    ScheduleBlock,
    Space,
)
from tests.core.factories import UserFactory


class MembershipPlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MembershipPlan

    name = factory.Sequence(lambda n: f"Plan {n}")
    monthly_price = Decimal("150.00")


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Member

    membership_plan = factory.SubFactory(MembershipPlanFactory)
    full_legal_name = factory.Faker("name")
    email = factory.Sequence(lambda n: f"member{n}@example.com")
    status = Member.Status.ACTIVE
    join_date = date(2024, 1, 1)


class SpaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Space

    space_id = factory.Sequence(lambda n: f"S-{n:03d}")
    space_type = Space.SpaceType.STUDIO
    status = Space.Status.AVAILABLE
    sublet_guild = None


class GuildFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Guild

    name = factory.Sequence(lambda n: f"Guild {n}")


class GuildVoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildVote

    member = factory.SubFactory(MemberFactory)
    guild = factory.SubFactory(GuildFactory)
    priority = 1


class LeaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Lease
        exclude = ["tenant_obj"]

    tenant_obj = factory.SubFactory(MemberFactory)
    content_type = factory.LazyAttribute(lambda o: ContentType.objects.get_for_model(o.tenant_obj))
    object_id = factory.LazyAttribute(lambda o: o.tenant_obj.pk)
    space = factory.SubFactory(SpaceFactory)
    lease_type = Lease.LeaseType.MONTH_TO_MONTH
    base_price = Decimal("200.00")
    monthly_rent = Decimal("200.00")
    start_date = factory.LazyFunction(lambda: timezone.now().date() - timedelta(days=30))


class GuildMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildMembership

    guild = factory.SubFactory(GuildFactory)
    user = factory.SubFactory(UserFactory)
    is_lead = False


class GuildDocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildDocument

    guild = factory.SubFactory(GuildFactory)
    name = factory.Sequence(lambda n: f"Document {n}")
    file_path = factory.django.FileField(filename="doc.pdf")
    uploaded_by = factory.SubFactory(UserFactory)


class GuildWishlistItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GuildWishlistItem

    guild = factory.SubFactory(GuildFactory)
    name = factory.Sequence(lambda n: f"Wishlist Item {n}")
    is_fulfilled = False


class MemberScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MemberSchedule

    user = factory.SubFactory(UserFactory)
    notes = ""


class ScheduleBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduleBlock

    member_schedule = factory.SubFactory(MemberScheduleFactory)
    day_of_week = 1
    start_time = "09:00"
    end_time = "17:00"
    is_recurring = True
