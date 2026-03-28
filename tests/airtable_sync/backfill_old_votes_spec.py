from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from airtable_sync.management.commands.backfill_old_votes import _deduplicate_votes, _resolve_guild_names
from membership.models import VotePreference
from tests.membership.factories import GuildFactory, MemberFactory, VotePreferenceFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GUILD_ID_MAP = {"recAAA": "Woodworkers", "recBBB": "Metalworkers", "recCCC": "Tech Guild"}


def _at_guild_record(record_id: str, name: str) -> dict:
    return {"id": record_id, "fields": {"Guild": name}}


def _at_vote_record(name: str, multiselect: list[str], created: str = "2025-01-01T00:00:00.000Z") -> dict:
    return {
        "id": f"rec_{name.replace(' ', '_')}",
        "createdTime": created,
        "fields": {"Name": name, "Guild Rankings Multiselect": multiselect},
    }


def _mock_api(guild_records: list[dict], vote_records: list[dict]) -> MagicMock:
    """Return a mock pyairtable.Api whose .table().all() returns the right data per table."""
    api = MagicMock()
    guilds_table = MagicMock()
    guilds_table.all.return_value = guild_records
    votes_table = MagicMock()
    votes_table.all.return_value = vote_records

    def table_router(base_id: str, table_id: str) -> MagicMock:
        if table_id == "tbla02m2GnUAsg3eW":
            return guilds_table
        return votes_table

    api.table.side_effect = table_router
    return api


# ---------------------------------------------------------------------------
# _resolve_guild_names
# ---------------------------------------------------------------------------


def describe_resolve_guild_names():
    def it_uses_explicit_preferences_when_all_three_present():
        fields = {
            "Guild Preference 1": ["recAAA"],
            "Guild Preference 2": ["recBBB"],
            "Guild Preference 3": ["recCCC"],
            "Guild Rankings Multiselect": ["recCCC", "recBBB", "recAAA"],
        }
        result = _resolve_guild_names(fields, GUILD_ID_MAP)
        assert result == ["Woodworkers", "Metalworkers", "Tech Guild"]

    def it_falls_back_to_multiselect():
        fields = {"Guild Rankings Multiselect": ["recBBB", "recCCC", "recAAA"]}
        result = _resolve_guild_names(fields, GUILD_ID_MAP)
        assert result == ["Metalworkers", "Tech Guild", "Woodworkers"]

    def it_returns_none_when_fewer_than_3():
        assert _resolve_guild_names({"Guild Rankings Multiselect": ["recAAA"]}, GUILD_ID_MAP) is None

    def it_returns_none_for_empty_fields():
        assert _resolve_guild_names({}, GUILD_ID_MAP) is None

    def it_returns_empty_string_for_unknown_ids():
        fields = {"Guild Rankings Multiselect": ["recAAA", "recBBB", "recUNKNOWN"]}
        result = _resolve_guild_names(fields, GUILD_ID_MAP)
        assert result == ["Woodworkers", "Metalworkers", ""]


# ---------------------------------------------------------------------------
# _deduplicate_votes
# ---------------------------------------------------------------------------


def describe_deduplicate_votes():
    def it_keeps_latest_per_name():
        records = [
            _at_vote_record("Alice", ["recAAA", "recBBB", "recCCC"], "2024-01-01T00:00:00.000Z"),
            _at_vote_record("Alice", ["recCCC", "recBBB", "recAAA"], "2025-06-01T00:00:00.000Z"),
        ]
        result = _deduplicate_votes(records)
        assert len(result) == 1
        assert result["Alice"]["createdTime"] == "2025-06-01T00:00:00.000Z"

    def it_skips_records_with_no_name():
        records = [
            {"id": "rec1", "createdTime": "2025-01-01T00:00:00.000Z", "fields": {"Name": ""}},
            {"id": "rec2", "createdTime": "2025-01-01T00:00:00.000Z", "fields": {}},
        ]
        assert _deduplicate_votes(records) == {}

    def it_keeps_earlier_record_when_later_duplicate_is_older():
        records = [
            _at_vote_record("Alice", ["recCCC", "recBBB", "recAAA"], "2025-06-01T00:00:00.000Z"),
            _at_vote_record("Alice", ["recAAA", "recBBB", "recCCC"], "2024-01-01T00:00:00.000Z"),
        ]
        result = _deduplicate_votes(records)
        assert result["Alice"]["createdTime"] == "2025-06-01T00:00:00.000Z"

    def it_strips_whitespace_from_names():
        records = [_at_vote_record("  Bob  ", ["recAAA", "recBBB", "recCCC"])]
        result = _deduplicate_votes(records)
        assert "Bob" in result


# ---------------------------------------------------------------------------
# Command integration tests
# ---------------------------------------------------------------------------


def describe_backfill_old_votes_command():
    @pytest.fixture()
    def three_guilds(db):
        return (
            GuildFactory(name="Woodworkers"),
            GuildFactory(name="Metalworkers"),
            GuildFactory(name="Tech Guild"),
        )

    def it_creates_vote_preferences(three_guilds, settings):
        g1, g2, g3 = three_guilds
        member = MemberFactory(full_legal_name="Alice Smith")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Alice Smith", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        vote = VotePreference.objects.get(member=member)
        assert vote.guild_1st == g1
        assert vote.guild_2nd == g2
        assert vote.guild_3rd == g3

    def it_skips_in_dry_run(three_guilds, settings):
        MemberFactory(full_legal_name="Alice Smith")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Alice Smith", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes", dry_run=True)

        assert VotePreference.objects.count() == 0

    def it_skips_former_members(three_guilds, settings):
        MemberFactory(full_legal_name="Former Fred", status="former")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Former Fred", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        assert VotePreference.objects.count() == 0

    def it_skips_members_who_already_voted(three_guilds, settings):
        g1, g2, g3 = three_guilds
        member = MemberFactory(full_legal_name="Already Voted")
        VotePreferenceFactory(member=member, guild_1st=g1, guild_2nd=g2, guild_3rd=g3)

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Already Voted", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        assert VotePreference.objects.filter(member=member).count() == 1

    def it_skips_unmatched_members(three_guilds, settings):
        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Nobody Here", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        assert VotePreference.objects.count() == 0

    def it_skips_votes_with_unknown_guilds(three_guilds, settings):
        MemberFactory(full_legal_name="Bob Jones")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Bob Jones", ["recAAA", "recBBB", "recUNKNOWN"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        assert VotePreference.objects.count() == 0

    def it_skips_votes_with_fewer_than_3_guilds(three_guilds, settings):
        MemberFactory(full_legal_name="Short Vote")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("Short Vote", ["recAAA"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        assert VotePreference.objects.count() == 0

    def it_creates_missing_guild_and_vote_preference(db, settings):
        from membership.models import Guild

        MemberFactory(full_legal_name="New Member")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("New Member", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes")

        assert Guild.objects.filter(name="Woodworkers").exists()
        assert Guild.objects.filter(name="Metalworkers").exists()
        assert Guild.objects.filter(name="Tech Guild").exists()
        assert VotePreference.objects.count() == 1

    def it_does_not_create_guild_in_dry_run(db, settings):
        from membership.models import Guild

        MemberFactory(full_legal_name="New Member")

        guild_records = [_at_guild_record(k, v) for k, v in GUILD_ID_MAP.items()]
        vote_records = [_at_vote_record("New Member", ["recAAA", "recBBB", "recCCC"])]

        with patch(
            "pyairtable.Api",
            return_value=_mock_api(guild_records, vote_records),
        ):
            call_command("backfill_old_votes", dry_run=True)

        assert Guild.objects.count() == 0
        assert VotePreference.objects.count() == 0
