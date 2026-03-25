from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from .models import FundingSnapshot, Guild, Member, VotePreference


# ---------------------------------------------------------------------------
# MemberAdmin
# ---------------------------------------------------------------------------


class ActiveStatusFilter(admin.SimpleListFilter):
    """Default filter that shows only active members unless another status is selected."""

    title = "status"
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> list[tuple[str, str]]:  # type: ignore[override]
        return [
            ("all", "All"),
            *Member.Status.choices,
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Member]) -> QuerySet[Member]:
        if self.value() is None:
            return queryset.filter(status=Member.Status.ACTIVE)
        if self.value() == "all":
            return queryset
        return queryset.filter(status=self.value())


@admin.register(Member)
class MemberAdmin(ModelAdmin):
    change_list_template = "admin/membership/member/change_list.html"
    list_display = [
        "display_name",
        "email",
        "membership_plan",
        "status",
        "role",
        "join_date",
        "last_login_display",
    ]
    list_display_links = ["display_name"]
    list_filter = [ActiveStatusFilter, "role", "membership_plan"]
    search_fields = ["full_legal_name", "preferred_name", "email"]
    list_per_page = 100
    ordering = ["full_legal_name"]
    fieldsets = [
        (
            "Personal Info",
            {
                "fields": [
                    "user",
                    "full_legal_name",
                    "preferred_name",
                    "email",
                    "phone",
                    "billing_name",
                ],
            },
        ),
        (
            "Membership",
            {
                "fields": [
                    "membership_plan",
                    "status",
                    "role",
                    "join_date",
                    "cancellation_date",
                    "committed_until",
                ],
            },
        ),
        (
            "Emergency Contact",
            {
                "fields": [
                    "emergency_contact_name",
                    "emergency_contact_phone",
                    "emergency_contact_relationship",
                ],
            },
        ),
        (
            "Notes",
            {
                "fields": ["notes"],
            },
        ),
    ]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Member]:
        qs = super().get_queryset(request)
        return qs.select_related("membership_plan", "user")

    @admin.display(description="Name", ordering="full_legal_name")
    def display_name(self, obj: Member) -> str:
        return obj.display_name

    @admin.display(description="Last Login to FOG", ordering="user__last_login")
    def last_login_display(self, obj: Member) -> str:
        if obj.user is None or obj.user.last_login is None:
            return mark_safe('<span style="opacity:0.4">Never</span>')  # noqa: S308
        last = obj.user.last_login
        days_ago = (timezone.now() - last).days
        if days_ago == 0:
            return "Today"
        if days_ago == 1:
            return "Yesterday"
        return f"{days_ago} days ago"


# ---------------------------------------------------------------------------
# GuildAdmin
# ---------------------------------------------------------------------------


@admin.register(Guild)
class GuildAdmin(ModelAdmin):
    list_display = ["name", "guild_lead", "notes_preview"]
    search_fields = ["name"]

    @admin.display(description="Notes")
    def notes_preview(self, obj: Guild) -> str:
        if len(obj.notes) > 80:
            return obj.notes[:80] + "..."
        return obj.notes


# ---------------------------------------------------------------------------
# VotePreferenceAdmin
# ---------------------------------------------------------------------------


class PayingMemberFilter(admin.SimpleListFilter):
    """Filter vote preferences by whether the member is on a paying plan."""

    title = "paying status"
    parameter_name = "paying"

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> list[tuple[str, str]]:  # type: ignore[override]
        return [
            ("yes", "Paying members"),
            ("no", "Non-paying members"),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[VotePreference]) -> QuerySet[VotePreference]:
        if self.value() == "yes":
            return queryset.filter(member__membership_plan__monthly_price__gt=0)
        if self.value() == "no":
            return queryset.filter(member__membership_plan__monthly_price=0)
        return queryset


@admin.register(VotePreference)
class VotePreferenceAdmin(ModelAdmin):
    list_display = ["member", "guild_1st", "guild_2nd", "guild_3rd", "updated_at"]
    list_filter = [PayingMemberFilter]
    search_fields = ["member__full_legal_name", "member__preferred_name"]


# ---------------------------------------------------------------------------
# FundingSnapshotAdmin
# ---------------------------------------------------------------------------


@admin.register(FundingSnapshot)
class FundingSnapshotAdmin(ModelAdmin):
    list_display = ["cycle_label", "snapshot_at", "contributor_count", "funding_pool"]
    readonly_fields = ["snapshot_at", "results"]
