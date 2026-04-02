"""Admin dashboard callback for Unfold."""

from __future__ import annotations

from typing import TypedDict

from django.db.models import Count
from django.http import HttpRequest
from django.utils import timezone

from membership.models import FundingSnapshot, Guild, Member, VotePreference


class GuildStanding(TypedDict, total=False):
    name: str
    first: int
    second: int
    third: int
    points: int
    bar_pct: float


def dashboard_callback(request: HttpRequest, context: dict) -> dict:
    """Populate voting stats for the admin dashboard."""
    active_members = Member.objects.filter(status=Member.Status.ACTIVE).count()
    total_voters = VotePreference.objects.count()
    paying_voters = VotePreference.objects.filter(
        member__member_type=Member.MemberType.STANDARD,
    ).count()
    active_guilds = Guild.objects.filter(is_active=True).count()
    projected_pool = paying_voters * 10
    participation_pct = round(total_voters / active_members * 100) if active_members else 0

    # Current vote leaders
    guilds = (
        Guild.objects.filter(is_active=True)
        .annotate(
            first=Count("first_choice_votes"),
            second=Count("second_choice_votes"),
            third=Count("third_choice_votes"),
        )
        .order_by("-first", "-second", "-third")
    )

    top_guilds: list[GuildStanding] = []
    for g in guilds:
        points = g.first * 5 + g.second * 3 + g.third * 2
        if points > 0:
            top_guilds.append(
                GuildStanding(
                    name=g.name,
                    first=g.first,
                    second=g.second,
                    third=g.third,
                    points=points,
                )
            )
    top_guilds.sort(key=lambda x: x["points"], reverse=True)
    max_points = top_guilds[0]["points"] if top_guilds else 1
    for entry in top_guilds:
        entry["bar_pct"] = round(entry["points"] / max_points * 100, 1)

    last_snapshot = FundingSnapshot.objects.order_by("-snapshot_at").first()

    context["stats"] = {
        "active_members": active_members,
        "total_voters": total_voters,
        "paying_voters": paying_voters,
        "active_guilds": active_guilds,
        "projected_pool": projected_pool,
        "participation_pct": participation_pct,
        "top_guilds": top_guilds,
        "last_snapshot": last_snapshot,
        "current_month": timezone.now().strftime("%B %Y"),
    }
    return context
