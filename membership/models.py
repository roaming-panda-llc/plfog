from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

DEFAULT_PRICE_PER_SQFT = Decimal("3.75")


def _active_lease_q(prefix: str = "", today: date_type | None = None) -> Q:
    """Build the Q-object filter for active leases.

    Args:
        prefix: Field prefix for related lookups (e.g. "leases__").
        today: Reference date; defaults to today.
    """
    if today is None:
        today = timezone.now().date()
    start = f"{prefix}start_date__lte"
    end_null = f"{prefix}end_date__isnull"
    end_gte = f"{prefix}end_date__gte"
    return Q(**{start: today}) & (Q(**{end_null: True}) | Q(**{end_gte: today}))


# ---------------------------------------------------------------------------
# MembershipPlan
# ---------------------------------------------------------------------------


class MembershipPlan(models.Model):
    # Queryset annotation (set by MembershipPlanAdmin.get_queryset)
    member_count: int

    name = models.CharField(max_length=100, unique=True)
    monthly_price = models.DecimalField(max_digits=8, decimal_places=2)
    deposit_required = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Membership Plan"
        verbose_name_plural = "Membership Plans"

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Member
# ---------------------------------------------------------------------------


class MemberQuerySet(models.QuerySet):
    def active(self) -> MemberQuerySet:
        return self.filter(status=Member.Status.ACTIVE)

    def paying(self) -> MemberQuerySet:
        """Only standard members count as paying."""
        return self.filter(member_type=Member.MemberType.STANDARD)

    def with_lease_totals(self) -> MemberQuerySet:
        active_filter = _active_lease_q(prefix="leases__")
        return self.annotate(
            active_lease_count=models.Count("leases", filter=active_filter),
            total_monthly_rent=Coalesce(
                Sum(
                    "leases__monthly_rent",
                    filter=active_filter,
                    output_field=DecimalField(),
                ),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
        )


class Member(models.Model):
    # Queryset annotation (set by MemberQuerySet.with_lease_totals)
    total_monthly_rent: Decimal

    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        ACTIVE = "active", "Active"
        FORMER = "former", "Former"
        SUSPENDED = "suspended", "Suspended"

    class MemberType(models.TextChoices):
        STANDARD = "standard", "Standard"
        GUILD_LEAD = "guild_lead", "Guild Lead"
        WORK_TRADE = "work_trade", "Work-Trade"
        EMPLOYEE = "employee", "Employee"
        CONTRACTOR = "contractor", "Contractor"
        VOLUNTEER = "volunteer", "Volunteer"

    class FogRole(models.TextChoices):
        MEMBER = "member", "Member"
        GUILD_OFFICER = "guild_officer", "Guild Officer"
        ADMIN = "admin", "Admin"

    airtable_record_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Airtable record ID for bidirectional sync.",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    full_legal_name = models.CharField(max_length=255)
    preferred_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True)
    discord_handle = models.CharField(
        max_length=100, blank=True, help_text="Discord username (e.g. user#1234 or @user)."
    )
    other_contact_info = models.CharField(
        max_length=255, blank=True, help_text="Other ways to reach this member (Instagram, Signal, etc.)."
    )
    about_me = models.TextField(blank=True, help_text="Short bio shown in the member directory.")
    billing_name = models.CharField(max_length=255, blank=True)

    # Emergency contact
    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True)

    membership_plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    member_type = models.CharField(
        max_length=20,
        choices=MemberType.choices,
        default=MemberType.STANDARD,
        help_text="What kind of member (standard, guild lead, work-trade, etc.).",
    )
    fog_role = models.CharField(
        max_length=20,
        choices=FogRole.choices,
        default=FogRole.MEMBER,
        help_text="FOG access level: admin (full access), guild officer (no site settings), member (hub only).",
    )
    join_date = models.DateField(null=True, blank=True)
    cancellation_date = models.DateField(null=True, blank=True)
    committed_until = models.DateField(null=True, blank=True)
    show_in_directory = models.BooleanField(
        default=False, help_text="Whether this member appears in the public member directory."
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    leases = GenericRelation(
        "Lease",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    objects = MemberQuerySet.as_manager()

    class Meta:
        ordering = ["full_legal_name"]
        verbose_name = "Member"
        verbose_name_plural = "Members"

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.preferred_name if self.preferred_name else self.full_legal_name

    @property
    def initials(self) -> str:
        """Compute display initials from the linked user's name or email."""
        if self.user is None:
            return ""
        email = getattr(self.user, "email", "") or ""
        name = getattr(self.user, "get_full_name", lambda: "")() or email
        parts = name.strip().split()
        result = ""
        if parts:
            result = "".join(p[0].upper() for p in parts[:2])
        if not result and email:
            result = email[0].upper()
        return result

    @property
    def active_leases(self) -> models.QuerySet[Lease]:
        return self.leases.filter(_active_lease_q())

    @property
    def current_spaces(self) -> models.QuerySet[Space]:
        return Space.objects.filter(pk__in=self.active_leases.values("space"))

    @property
    def studio_storage_total(self) -> Decimal:
        total = self.active_leases.aggregate(
            total=Coalesce(
                Sum("monthly_rent"),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            )
        )["total"]
        return total

    @property
    def membership_monthly_dues(self) -> Decimal:
        return self.membership_plan.monthly_price

    @property
    def total_monthly_spend(self) -> Decimal:
        return self.membership_monthly_dues + self.studio_storage_total

    @property
    def is_paying(self) -> bool:
        """Only standard members are paying members."""
        return self.member_type == self.MemberType.STANDARD

    @property
    def is_fog_admin(self) -> bool:
        """True when fog_role is admin (full access)."""
        return self.fog_role == self.FogRole.ADMIN

    @property
    def is_guild_officer(self) -> bool:
        """True when fog_role is guild_officer (admin access without site settings)."""
        return self.fog_role == self.FogRole.GUILD_OFFICER

    def set_fog_role(self, new_role: str, *, changed_by: Member) -> None:
        """Change this member's fog_role with permission checks.

        Admins can assign any role. Guild officers can assign member or guild_officer
        but not admin. Regular members cannot change roles.

        Args:
            new_role: The FogRole value to set.
            changed_by: The Member performing the change.

        Raises:
            PermissionError: If the caller lacks permission.
            ValueError: If the role value is invalid.
        """
        if new_role not in {c.value for c in self.FogRole}:
            raise ValueError(f"Invalid role: {new_role}")

        if changed_by.is_fog_admin:
            pass  # admins can do anything
        elif changed_by.is_guild_officer:
            if new_role == self.FogRole.ADMIN:
                raise PermissionError("Guild officers cannot grant admin access.")
        else:
            raise PermissionError("Only admins and guild officers can change roles.")

        self.fog_role = new_role
        self.save(update_fields=["fog_role"])
        self.sync_user_permissions()

    def sync_user_permissions(self) -> None:
        """Set is_staff/is_superuser on the linked User based on fog_role.

        Admin gets full access. Guild officers get staff access but not
        superuser. Members lose staff access. Skips save if nothing changed.
        """
        if self.user is None:
            return

        if self.is_fog_admin:
            new_staff, new_super = True, True
        elif self.is_guild_officer:
            new_staff, new_super = True, False
        else:
            new_staff, new_super = False, False

        if self.user.is_staff == new_staff and self.user.is_superuser == new_super:
            return

        self.user.is_staff = new_staff
        self.user.is_superuser = new_super
        self.user.save(update_fields=["is_staff", "is_superuser"])

    # Member records are managed in Airtable and pulled into Django via airtable_pull.
    # No save()/delete() sync overrides — this model is read-only from Airtable's perspective.


# ---------------------------------------------------------------------------
# Guild
# ---------------------------------------------------------------------------


class Guild(models.Model):
    # Queryset annotation (set by GuildAdmin.get_queryset)
    sublet_count: int

    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True, help_text="Whether this guild is eligible for voting and display.")
    guild_lead = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="led_guilds",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    leases = GenericRelation(
        "Lease",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Guild"
        verbose_name_plural = "Guilds"

    def __str__(self) -> str:
        return self.name

    @property
    def active_leases(self) -> models.QuerySet[Lease]:
        return self.leases.filter(_active_lease_q())

    @property
    def sublet_revenue(self) -> Decimal:
        """Sum of monthly_rent from active leases on spaces sublet to this guild."""
        total = Lease.objects.filter(
            _active_lease_q(),
            space__sublet_guild=self,
        ).aggregate(
            total=Coalesce(
                Sum("monthly_rent", output_field=DecimalField()),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
        )["total"]
        return total


class VotePreference(models.Model):
    """Persistent guild funding vote per member — updated anytime, one row per member."""

    airtable_record_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Airtable record ID for bidirectional sync.",
    )
    member = models.OneToOneField(
        Member,
        on_delete=models.CASCADE,
        related_name="vote_preference",
        help_text="The member who cast this vote.",
    )
    guild_1st = models.ForeignKey(
        Guild,
        on_delete=models.CASCADE,
        related_name="first_choice_votes",
        help_text="First-choice guild (5 points).",
    )
    guild_2nd = models.ForeignKey(
        Guild,
        on_delete=models.CASCADE,
        related_name="second_choice_votes",
        help_text="Second-choice guild (3 points).",
    )
    guild_3rd = models.ForeignKey(
        Guild,
        on_delete=models.CASCADE,
        related_name="third_choice_votes",
        help_text="Third-choice guild (2 points).",
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="When this vote was last changed.")

    class Meta:
        verbose_name = "Vote Preference"
        verbose_name_plural = "Vote Preferences"

    def __str__(self) -> str:
        return f"{self.member.display_name}: {self.guild_1st} / {self.guild_2nd} / {self.guild_3rd}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        if not getattr(self, "_skip_airtable_sync", False):
            from airtable_sync.service import sync_vote_to_airtable

            sync_vote_to_airtable(self)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        record_id = self.airtable_record_id
        result = super().delete(*args, **kwargs)
        if record_id and not getattr(self, "_skip_airtable_sync", False):
            from airtable_sync.service import delete_vote_from_airtable

            delete_vote_from_airtable(record_id)
        return result


class FundingSnapshot(models.Model):
    """Immutable historical record of a funding calculation at a point in time."""

    airtable_record_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Airtable record ID for bidirectional sync.",
    )
    cycle_label = models.CharField(
        max_length=100, help_text="Human-readable label for the funding cycle (e.g. 'March 2026')."
    )
    snapshot_at = models.DateTimeField(auto_now_add=True, help_text="When this snapshot was taken.")
    contributor_count = models.PositiveIntegerField(
        help_text="Number of paying members who contributed to the funding pool."
    )
    funding_pool = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Total dollar pool (contributor_count × $10)."
    )
    results = models.JSONField(default=dict, help_text="Full calculation results including per-guild breakdowns.")

    class Meta:
        ordering = ["-snapshot_at"]
        verbose_name = "Funding Snapshot"
        verbose_name_plural = "Funding Snapshots"

    def __str__(self) -> str:
        return f"{self.cycle_label} — ${self.funding_pool}"

    class VoterFilter(models.TextChoices):
        ALL_MEMBERS = "all", "All Members"
        OFFICERS_ONLY = "officers_only", "Officers Only (Admins + Guild Officers)"

    @classmethod
    def take(
        cls,
        *,
        title: str = "",
        voter_filter: str = "",
        pool_override: int | None = None,
    ) -> FundingSnapshot | None:
        """Create a snapshot from current vote preferences.

        Args:
            title: Custom label for the snapshot. Defaults to current month/year.
            voter_filter: One of VoterFilter values. 'officers_only' limits votes
                to admin + guild_officer roles. Default includes all members.
            pool_override: Custom dollar amount for the funding pool. If None,
                calculates from paying_voter_count × $10.

        Returns:
            The created FundingSnapshot, or None if no votes exist.
        """
        from membership.vote_calculator import calculate_results

        preferences = VotePreference.objects.select_related(
            "member__membership_plan",
            "guild_1st",
            "guild_2nd",
            "guild_3rd",
        ).all()

        if voter_filter == cls.VoterFilter.OFFICERS_ONLY:
            preferences = preferences.filter(
                member__fog_role__in=[Member.FogRole.ADMIN, Member.FogRole.GUILD_OFFICER],
            )

        if not preferences.exists():
            return None

        paying_count = preferences.filter(member__member_type=Member.MemberType.STANDARD).count()

        votes = [
            {
                "guild_1st": pref.guild_1st.name,
                "guild_2nd": pref.guild_2nd.name,
                "guild_3rd": pref.guild_3rd.name,
            }
            for pref in preferences
        ]

        calc = calculate_results(votes, paying_voter_count=paying_count, pool_override=pool_override)

        cycle_label = title.strip() if title.strip() else timezone.now().strftime("%B %Y")

        return cls.objects.create(
            cycle_label=cycle_label,
            contributor_count=paying_count,
            funding_pool=calc["total_pool"],
            results=calc,
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        if not getattr(self, "_skip_airtable_sync", False):
            from airtable_sync.service import sync_snapshot_to_airtable

            sync_snapshot_to_airtable(self)


# ---------------------------------------------------------------------------
# Space
# ---------------------------------------------------------------------------


class SpaceQuerySet(models.QuerySet):
    def available(self) -> SpaceQuerySet:
        return self.filter(status=Space.Status.AVAILABLE)

    def with_revenue(self) -> SpaceQuerySet:
        active_filter = _active_lease_q(prefix="leases__")
        return self.annotate(
            active_lease_rent_total=Coalesce(
                Sum(
                    "leases__monthly_rent",
                    filter=active_filter,
                    output_field=DecimalField(),
                ),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            ),
        )


class Space(models.Model):
    # Queryset annotation (set by SpaceQuerySet.with_revenue)
    active_lease_rent_total: Decimal

    class SpaceType(models.TextChoices):
        STUDIO = "studio", "Studio"
        STORAGE = "storage", "Storage"
        PARKING = "parking", "Parking"
        DESK = "desk", "Desk"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Maintenance"

    airtable_record_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Airtable record ID for bidirectional sync.",
    )
    space_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255, blank=True)
    space_type = models.CharField(
        max_length=20,
        choices=SpaceType.choices,
    )
    size_sqft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    depth = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rate_per_sqft = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_rentable = models.BooleanField(default=True)
    manual_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    photo = models.ImageField(upload_to="spaces/", blank=True)
    floorplan_ref = models.CharField(max_length=100, blank=True)
    sublet_guild = models.ForeignKey(
        "Guild",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sublets",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SpaceQuerySet.as_manager()

    class Meta:
        ordering = ["space_id"]
        verbose_name = "Space"
        verbose_name_plural = "Spaces"

    def __str__(self) -> str:
        if self.name:
            return f"{self.space_id} - {self.name}"
        return self.space_id

    @property
    def full_price(self) -> Decimal | None:
        if self.manual_price is not None:
            return self.manual_price
        if self.size_sqft is not None:
            rate = self.rate_per_sqft if self.rate_per_sqft is not None else DEFAULT_PRICE_PER_SQFT
            return self.size_sqft * rate
        return None

    @property
    def current_occupants(self) -> list[Member | Guild]:
        """Return all active tenants (Members and Guilds) for this space."""
        active = self.leases.filter(_active_lease_q()).select_related("content_type")
        return [lease.tenant for lease in active]

    @property
    def vacancy_value(self) -> Decimal:
        if self.status == self.Status.AVAILABLE:
            return self.full_price or Decimal("0.00")
        return Decimal("0.00")

    @property
    def actual_revenue(self) -> Decimal:
        total = self.leases.filter(_active_lease_q()).aggregate(
            total=Coalesce(
                Sum("monthly_rent"),
                Value(Decimal("0.00")),
                output_field=DecimalField(),
            )
        )["total"]
        return total

    @property
    def revenue_loss(self) -> Decimal | None:
        fp = self.full_price
        if fp is None:
            return None
        return fp - self.actual_revenue

    # Space records are managed in Airtable and pulled into Django via airtable_pull.
    # No save()/delete() sync overrides — this model is read-only from Airtable's perspective.


# ---------------------------------------------------------------------------
# Lease
# ---------------------------------------------------------------------------


class LeaseQuerySet(models.QuerySet):
    def active(self, as_of: date_type | None = None) -> LeaseQuerySet:
        return self.filter(_active_lease_q(today=as_of))


class Lease(models.Model):
    airtable_record_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Airtable record ID for bidirectional sync.",
    )

    class LeaseType(models.TextChoices):
        MONTH_TO_MONTH = "month_to_month", "Month-to-Month"
        ANNUAL = "annual", "Annual"

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    tenant = GenericForeignKey("content_type", "object_id")
    space = models.ForeignKey(Space, on_delete=models.PROTECT, related_name="leases")
    lease_type = models.CharField(
        max_length=20,
        choices=LeaseType.choices,
    )
    base_price = models.DecimalField(max_digits=8, decimal_places=2)
    monthly_rent = models.DecimalField(max_digits=8, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    committed_until = models.DateField(null=True, blank=True)

    # Deposit tracking
    deposit_required = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    deposit_paid_date = models.DateField(null=True, blank=True)
    deposit_paid_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    discount_reason = models.TextField(blank=True)
    is_split = models.BooleanField(default=False)
    prepaid_through = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = LeaseQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Lease"
        verbose_name_plural = "Leases"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.tenant} @ {self.space} ({self.start_date})"

    @property
    def is_active(self) -> bool:
        today = timezone.now().date()
        if self.start_date is None or self.start_date > today:
            return False
        if self.end_date is not None and self.end_date < today:
            return False
        return True

    # Lease records are managed in Airtable and pulled into Django via airtable_pull.
    # No save()/delete() sync overrides — this model is read-only from Airtable's perspective.
