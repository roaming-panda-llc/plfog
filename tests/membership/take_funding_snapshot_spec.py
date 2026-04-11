"""BDD specs for the take_funding_snapshot management command."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from membership.models import FundingSnapshot, Member
from tests.membership.factories import (
    GuildFactory,
    MemberFactory,
    MembershipPlanFactory,
    VotePreferenceFactory,
)


@pytest.mark.django_db
def describe_take_funding_snapshot_command():
    def it_creates_snapshot_from_existing_votes():
        plan = MembershipPlanFactory(monthly_price=Decimal("100.00"))
        g1 = GuildFactory(name="Wood")
        g2 = GuildFactory(name="Metal")
        g3 = GuildFactory(name="Clay")
        member = MemberFactory(membership_plan=plan)
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        out = StringIO()
        call_command("take_funding_snapshot", stdout=out)

        assert FundingSnapshot.objects.count() == 1
        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert snap.contributor_count == 1
        assert "results" in snap.results
        assert "Snapshot created" in out.getvalue()

    def it_handles_no_votes_gracefully():
        out = StringIO()
        call_command("take_funding_snapshot", stdout=out)

        assert FundingSnapshot.objects.count() == 0
        assert "No vote preferences found" in out.getvalue()

    def it_only_counts_paying_members_in_contribution():
        """contributor_count is the paying-only count; pool is max(contrib, floor)."""
        g1 = GuildFactory(name="G1")
        g2 = GuildFactory(name="G2")
        g3 = GuildFactory(name="G3")
        paying = MemberFactory(member_type=Member.MemberType.STANDARD)
        non_paying = MemberFactory(member_type=Member.MemberType.WORK_TRADE)
        VotePreferenceFactory(member=paying, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)
        VotePreferenceFactory(member=non_paying, guild_1st=g2, guild_2nd=g1, guild_3rd=g3)

        # Run with no floor so we can observe the raw contribution.
        call_command("take_funding_snapshot", "--minimum-pool", "0", stdout=StringIO())

        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert snap.contributor_count == 1
        assert snap.funding_pool == Decimal("10.00")

    def it_applies_default_1000_minimum_pool_floor():
        g1 = GuildFactory(name="G1")
        g2 = GuildFactory(name="G2")
        g3 = GuildFactory(name="G3")
        member = MemberFactory(member_type=Member.MemberType.STANDARD)
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        call_command("take_funding_snapshot", stdout=StringIO())

        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert snap.contributor_count == 1
        assert snap.minimum_pool == Decimal("1000.00")
        assert snap.funding_pool == Decimal("1000.00")

    def it_honors_custom_minimum_pool_flag():
        g1 = GuildFactory(name="G1")
        g2 = GuildFactory(name="G2")
        g3 = GuildFactory(name="G3")
        member = MemberFactory(member_type=Member.MemberType.STANDARD)
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        call_command("take_funding_snapshot", "--minimum-pool", "500", stdout=StringIO())

        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert snap.minimum_pool == Decimal("500.00")
        assert snap.funding_pool == Decimal("500.00")

    def it_stores_raw_votes_with_denormalized_role_info():
        g1 = GuildFactory(name="G1")
        g2 = GuildFactory(name="G2")
        g3 = GuildFactory(name="G3")
        member = MemberFactory(
            member_type=Member.MemberType.WORK_TRADE,
            fog_role=Member.FogRole.GUILD_OFFICER,
            full_legal_name="Alice Officer",
        )
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        call_command("take_funding_snapshot", stdout=StringIO())

        snap = FundingSnapshot.objects.first()
        assert snap is not None
        assert len(snap.raw_votes) == 1
        row = snap.raw_votes[0]
        assert row["member_id"] == member.pk
        assert row["member_name"] == "Alice Officer"
        assert row["member_type"] == Member.MemberType.WORK_TRADE
        assert row["fog_role"] == Member.FogRole.GUILD_OFFICER
        assert row["is_paying"] is False
        assert row["guild_1st_name"] == "G1"
        assert row["guild_1st_id"] == g1.pk

    def it_uses_current_month_as_cycle_label():
        from django.utils import timezone

        plan = MembershipPlanFactory(monthly_price=Decimal("50.00"))
        g1 = GuildFactory(name="Alpha")
        g2 = GuildFactory(name="Beta")
        g3 = GuildFactory(name="Gamma")
        member = MemberFactory(membership_plan=plan)
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        call_command("take_funding_snapshot", stdout=StringIO())

        snap = FundingSnapshot.objects.first()
        assert snap is not None
        expected_label = timezone.now().strftime("%B %Y")
        assert snap.cycle_label == expected_label
