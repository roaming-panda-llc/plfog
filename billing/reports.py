"""Reports queries and CSV export for billing.

The report expands TabEntries into per-guild "long-format" rows using
``TabEntry.compute_splits()``. Filtering by date range, guild, charge type,
and charge status all happen at the queryset level; SPLIT_EQUALLY expansion
happens in Python because JSONField-contains semantics vary by backend and
the plfog row count is tiny.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from decimal import Decimal
from typing import Iterator

from django.db.models import Q, QuerySet
from django.http import StreamingHttpResponse
from django.utils import timezone

from billing.models import Product, TabCharge, TabEntry
from membership.models import Guild

_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReportRow:
    created_at: datetime
    member_name: str
    description: str
    guild_id: int | None
    guild_name: str
    split_mode: str
    split_mode_display: str
    amount: Decimal
    admin_percent: Decimal
    admin_amount: Decimal
    guild_amount: Decimal
    charge_status: str
    charge_type: str  # "product" | "custom"


@dataclass(frozen=True)
class PayoutRow:
    guild_id: int | None
    guild_name: str
    entry_count: int
    guild_amount: Decimal


def _base_entries(
    *,
    start_date: date_cls | None,
    end_date: date_cls | None,
    guild_ids: list[int] | None,
    charge_types: list[str] | None,
    statuses: list[str] | None,
) -> QuerySet[TabEntry]:
    """Return a filtered, ordered TabEntry queryset for report generation."""
    qs: QuerySet[TabEntry] = (
        TabEntry.objects.all()
        .select_related("tab__member", "guild", "product", "tab_charge")
        .order_by("created_at", "pk")
    )
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    if guild_ids:
        # Match entries whose snapshot guild is in the requested set OR any
        # SPLIT_EQUALLY entry (we filter the individual splits in Python below
        # since JSONField contains semantics vary by backend).
        qs = qs.filter(
            Q(guild_id__in=guild_ids)
            | Q(split_mode=Product.SplitMode.SPLIT_EQUALLY)
        )

    if charge_types:
        has_product = "product" in charge_types
        has_custom = "custom" in charge_types
        if has_product and not has_custom:
            qs = qs.filter(product__isnull=False)
        elif has_custom and not has_product:
            qs = qs.filter(product__isnull=True)

    if statuses:
        status_q = Q()
        if "pending" in statuses:
            status_q |= Q(tab_charge__isnull=True)
        other = [s for s in statuses if s != "pending"]
        if other:
            status_q |= Q(tab_charge__status__in=other)
        qs = qs.filter(status_q)

    return qs


def _guild_name_cache() -> dict[int, str]:
    return dict(Guild.objects.values_list("pk", "name"))


def build_report(
    *,
    start_date: date_cls | None = None,
    end_date: date_cls | None = None,
    guild_ids: list[int] | None = None,
    charge_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[ReportRow], list[PayoutRow], Decimal]:
    """Return ``(rows, payout_summary, admin_total)`` for the Reports page.

    ``rows`` is a long-format list: one row per (entry × guild split). A
    SPLIT_EQUALLY entry across N guilds emits N rows; the admin share sits
    on the first row only to avoid double-counting. Sum of ``admin_amount``
    across all rows equals ``admin_total``. Sum of ``guild_amount`` grouped
    by guild matches ``payout_summary``.

    When ``guild_ids`` is set, split rows that map to non-requested guilds
    are dropped so the payout summary only shows what's owed to the filtered
    guilds.
    """
    name_cache = _guild_name_cache()
    split_mode_choices = dict(Product.SplitMode.choices)

    rows: list[ReportRow] = []
    payouts: dict[int | None, PayoutRow] = {}
    admin_total = _ZERO

    qs = _base_entries(
        start_date=start_date,
        end_date=end_date,
        guild_ids=guild_ids,
        charge_types=charge_types,
        statuses=statuses,
    )

    for entry in qs.iterator(chunk_size=500):
        splits = entry.compute_splits()
        charge_status = entry.tab_charge.status if entry.tab_charge_id else "pending"
        charge_type = "product" if entry.product_id else "custom"

        for split in splits:
            if guild_ids and split.guild_id is not None and split.guild_id not in guild_ids:
                # Filtered out — this split row is for a guild the user didn't request
                continue

            gname = (
                name_cache.get(split.guild_id, "— unattributed —")
                if split.guild_id is not None
                else "— unattributed —"
            )
            rows.append(
                ReportRow(
                    created_at=entry.created_at,
                    member_name=entry.tab.member.display_name,
                    description=entry.description,
                    guild_id=split.guild_id,
                    guild_name=gname,
                    split_mode=entry.split_mode,
                    split_mode_display=split_mode_choices.get(entry.split_mode, entry.split_mode),
                    amount=entry.amount,
                    admin_percent=entry.admin_percent,
                    admin_amount=split.admin_amount,
                    guild_amount=split.guild_amount,
                    charge_status=charge_status,
                    charge_type=charge_type,
                )
            )

            admin_total += split.admin_amount
            if split.guild_id is not None and split.guild_amount > _ZERO:
                existing = payouts.get(split.guild_id)
                if existing is None:
                    payouts[split.guild_id] = PayoutRow(
                        guild_id=split.guild_id,
                        guild_name=gname,
                        entry_count=1,
                        guild_amount=split.guild_amount,
                    )
                else:
                    payouts[split.guild_id] = PayoutRow(
                        guild_id=split.guild_id,
                        guild_name=gname,
                        entry_count=existing.entry_count + 1,
                        guild_amount=existing.guild_amount + split.guild_amount,
                    )

    payout_list = sorted(payouts.values(), key=lambda p: (p.guild_name or "", p.guild_id or 0))
    return rows, payout_list, admin_total


class _Echo:
    """File-like object whose ``write()`` returns the payload (for StreamingHttpResponse)."""

    def write(self, value: str) -> str:
        return value


CSV_HEADERS = [
    "date",
    "member",
    "description",
    "guild",
    "split_mode",
    "charge_type",
    "charge_status",
    "amount",
    "admin_percent",
    "admin_amount",
    "guild_amount",
]


def stream_report_csv(
    *,
    start_date: date_cls | None = None,
    end_date: date_cls | None = None,
    guild_ids: list[int] | None = None,
    charge_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> StreamingHttpResponse:
    """Build a streaming CSV response for a filtered report."""
    pseudo = _Echo()
    writer = csv.writer(pseudo)

    def iter_rows() -> Iterator[str]:
        yield writer.writerow(CSV_HEADERS)
        rows, _payouts, _admin_total = build_report(
            start_date=start_date,
            end_date=end_date,
            guild_ids=guild_ids,
            charge_types=charge_types,
            statuses=statuses,
        )
        for r in rows:
            yield writer.writerow(
                [
                    r.created_at.date().isoformat(),
                    r.member_name,
                    r.description,
                    r.guild_name,
                    r.split_mode,
                    r.charge_type,
                    r.charge_status,
                    f"{r.amount:.2f}",
                    f"{r.admin_percent:.2f}",
                    f"{r.admin_amount:.2f}",
                    f"{r.guild_amount:.2f}",
                ]
            )

    response = StreamingHttpResponse(iter_rows(), content_type="text/csv")
    stamp = timezone.now().strftime("%Y%m%d")
    response["Content-Disposition"] = f'attachment; filename="plfog-billing-report-{stamp}.csv"'
    return response


class ReportFilterForm:
    """A lightweight not-a-Django-form that parses ``request.GET`` into filter kwargs.

    We use this instead of a real forms.Form because the Reports page submits
    filters via GET query params — each field is optional, errors should fall
    back to "no filter", and the same field set needs to survive round-trips
    on the CSV download URL. A plain dataclass parse is cleaner than wiring up
    a real form for that.
    """

    def __init__(self, data):
        self.data = data or {}

    def filter_kwargs(self) -> dict:
        return {
            "start_date": self._parse_date("start_date"),
            "end_date": self._parse_date("end_date"),
            "guild_ids": self._parse_int_list("guilds") or None,
            "charge_types": self._parse_str_list("charge_type") or None,
            "statuses": self._parse_str_list("status") or None,
        }

    def _parse_date(self, key: str) -> date_cls | None:
        raw = (self.data.get(key) or "").strip()
        if not raw:
            return None
        try:
            return date_cls.fromisoformat(raw)
        except ValueError:
            return None

    def _parse_int_list(self, key: str) -> list[int]:
        raw = self.data.getlist(key) if hasattr(self.data, "getlist") else self.data.get(key, [])
        if isinstance(raw, str):
            raw = [raw]
        parsed: list[int] = []
        for value in raw:
            try:
                parsed.append(int(value))
            except (TypeError, ValueError):
                continue
        return parsed

    def _parse_str_list(self, key: str) -> list[str]:
        raw = self.data.getlist(key) if hasattr(self.data, "getlist") else self.data.get(key, [])
        if isinstance(raw, str):
            raw = [raw] if raw else []
        return [s for s in raw if s]


# Convenience: expose valid status / charge-type choices for the filter UI
STATUS_CHOICES = [
    ("pending", "Pending (not yet charged)"),
    (TabCharge.Status.SUCCEEDED, "Succeeded"),
    (TabCharge.Status.FAILED, "Failed"),
    (TabCharge.Status.PROCESSING, "Processing"),
]

CHARGE_TYPE_CHOICES = [
    ("product", "Product"),
    ("custom", "Custom (Enter Your Own Price)"),
]
