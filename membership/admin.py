from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline

from .forms import MemberAdminForm
from .models import FundingSnapshot, Guild, Member, MemberEmail, VotePreference


# ---------------------------------------------------------------------------
# MemberEmail Inline
# ---------------------------------------------------------------------------


class MemberEmailInline(TabularInline):
    model = MemberEmail
    extra = 1
    fields = ["email", "is_primary"]


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


class HasUserFilter(admin.SimpleListFilter):
    """Filter to show only members with linked User accounts (i.e., they've logged in)."""

    title = "account type"
    parameter_name = "has_user"

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> list[tuple[str, str]]:  # type: ignore[override]
        return [
            ("yes", "Users — members who have logged into this web app"),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Member]) -> QuerySet[Member]:
        if self.value() == "yes":
            return queryset.filter(user__isnull=False)
        return queryset


@admin.register(Member)
class MemberAdmin(ModelAdmin):
    change_list_template = "admin/membership/member/change_list.html"
    form = MemberAdminForm
    inlines = [MemberEmailInline]
    list_display = [
        "display_name",
        "email",
        "status",
        "member_type",
        "fog_role",
        "join_date",
        "last_login_display",
    ]
    list_display_links = ["display_name"]
    list_filter = [ActiveStatusFilter, HasUserFilter, "member_type"]
    search_fields = ["full_legal_name", "preferred_name", "email"]
    list_per_page = 100
    ordering = ["full_legal_name"]

    def get_fieldsets(self, request: HttpRequest, obj: object = None) -> list[tuple[str, dict]]:
        """Build fieldsets dynamically — fog_role only visible to superusers."""
        membership_fields: list[str] = [
            "membership_plan",
            "status",
            "member_type",
            "join_date",
            "cancellation_date",
            "committed_until",
        ]
        if request.user.is_superuser:
            membership_fields.insert(3, "fog_role")

        personal_fields: list[str] = [
            "full_legal_name",
            "preferred_name",
            "email",
            "phone",
            "billing_name",
        ]

        # Show "user" link on edit, "create_user" checkbox on add
        if obj is not None:
            personal_fields.insert(0, "user")
        else:
            personal_fields.append("create_user")

        return [
            (
                "Personal Info",
                {
                    "fields": personal_fields,
                },
            ),
            (
                "Membership",
                {
                    "fields": membership_fields,
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

    def save_model(self, request: HttpRequest, obj: Member, form: MemberAdminForm, change: bool) -> None:
        """Optionally create a User account when adding a new member with 'Create login' checked."""
        create_user = form.cleaned_data.get("create_user", False)

        if not change and create_user and obj.email:
            from django.contrib.auth import get_user_model

            UserModel = get_user_model()

            # Save the member first (without a user)
            super().save_model(request, obj, form, change)
            # Create the user — the post_save signal will try to auto-link a member
            user = UserModel.objects.create_user(username=obj.email, email=obj.email)
            # Signal may have created a duplicate member or linked to wrong one.
            # Delete any signal-created member and link ours.
            from membership.models import Member as MemberModel

            MemberModel.objects.filter(user=user).exclude(pk=obj.pk).delete()
            obj.user = user
            obj.save(update_fields=["user"])
            obj.sync_user_permissions()
        else:
            super().save_model(request, obj, form, change)

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet[Member], search_term: str
    ) -> tuple[QuerySet[Member], bool]:
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            alias_member_ids = MemberEmail.objects.filter(email__icontains=search_term).values_list(
                "member_id", flat=True
            )
            queryset = queryset | self.model.objects.filter(pk__in=alias_member_ids)
            use_distinct = True
        return queryset, use_distinct

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
    """Filter vote preferences by whether the member is a paying (standard) member."""

    title = "paying status"
    parameter_name = "paying"

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> list[tuple[str, str]]:  # type: ignore[override]
        return [
            ("yes", "Paying members"),
            ("no", "Non-paying members"),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[VotePreference]) -> QuerySet[VotePreference]:
        if self.value() == "yes":
            return queryset.filter(member__member_type=Member.MemberType.STANDARD)
        if self.value() == "no":
            return queryset.exclude(member__member_type=Member.MemberType.STANDARD)
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


# ---------------------------------------------------------------------------
# Hide default User and EmailAddress admin pages
# ---------------------------------------------------------------------------

# Hide default User admin and allauth EmailAddress admin — members page is the
# single interface for user management.
from django.contrib.auth import get_user_model  # noqa: E402
from allauth.account.models import EmailAddress  # noqa: E402

for _model in (get_user_model(), EmailAddress):
    try:
        admin.site.unregister(_model)
    except Exception:  # pragma: no cover  # NotRegistered
        pass
