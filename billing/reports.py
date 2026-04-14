"""Reports queries and CSV export for billing.

Stubbed during the v1.7 product-revenue-splits refactor — Task 8 rebuilds the
report on top of the new ``TabEntrySplit`` snapshot rows. The public surface
(``build_report``, ``stream_report_csv``, ``ReportFilterForm``, choice
constants) is preserved so callers keep compiling; the body just returns
empty data until Task 8 wires it back up.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterator

from django.http import StreamingHttpResponse
from django.utils import timezone

from billing.models import TabCharge

if TYPE_CHECKING:
    from django.http.request import QueryDict  # noqa: F401

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


def _base_entries(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("Rebuilt in Task 8")


def _guild_name_cache() -> dict[int, str]:
    raise NotImplementedError("Rebuilt in Task 8")


def build_report(
    *,
    start_date: date_cls | None = None,
    end_date: date_cls | None = None,
    guild_ids: list[int] | None = None,
    charge_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[ReportRow], list[PayoutRow], Decimal]:
    """Stubbed during refactor — see Task 8 for the real implementation."""
    return [], [], _ZERO


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

    def __init__(self, data: "QueryDict | dict[str, Any] | None") -> None:
        self.data: Any = data if data is not None else {}

    def filter_kwargs(self) -> dict[str, Any]:
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
