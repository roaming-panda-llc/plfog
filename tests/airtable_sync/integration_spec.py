"""Integration tests — verify sync behavior on model save()/delete().

Member, Space, and Lease are Airtable-managed (inbound only via airtable_pull).
VotePreference and FundingSnapshot push to Airtable on save.
"""

from __future__ import annotations

from unittest.mock import patch

from tests.membership.factories import (
    FundingSnapshotFactory,
    LeaseFactory,
    MemberFactory,
    SpaceFactory,
    VotePreferenceFactory,
)


# ---------------------------------------------------------------------------
# Member, Space, Lease — should NOT push to Airtable on save/delete
# ---------------------------------------------------------------------------


def describe_member_does_not_sync_to_airtable():
    def it_does_not_call_sync_on_save(db, enable_airtable_sync):
        with patch("airtable_sync.service.get_table") as mock_get:
            MemberFactory()
            mock_get.assert_not_called()

    def it_does_not_call_sync_on_delete(db, enable_airtable_sync):
        member = MemberFactory(airtable_record_id="recMEMBER12345678")
        with patch("airtable_sync.service.get_table") as mock_get:
            member.delete()
            mock_get.assert_not_called()


def describe_space_does_not_sync_to_airtable():
    def it_does_not_call_sync_on_save(db, enable_airtable_sync):
        with patch("airtable_sync.service.get_table") as mock_get:
            SpaceFactory()
            mock_get.assert_not_called()

    def it_does_not_call_sync_on_delete(db, enable_airtable_sync):
        space = SpaceFactory(airtable_record_id="recSPACE123456789")
        with patch("airtable_sync.service.get_table") as mock_get:
            space.delete()
            mock_get.assert_not_called()


def describe_lease_does_not_sync_to_airtable():
    def it_does_not_call_sync_on_save(db, enable_airtable_sync):
        with patch("airtable_sync.service.get_table") as mock_get:
            LeaseFactory()
            mock_get.assert_not_called()

    def it_does_not_call_sync_on_delete(db, enable_airtable_sync):
        lease = LeaseFactory(airtable_record_id="recLEASE123456789")
        with patch("airtable_sync.service.get_table") as mock_get:
            lease.delete()
            mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# VotePreference — pushes to Airtable on save/delete
# ---------------------------------------------------------------------------


def describe_vote_preference_save_triggers_sync():
    def it_calls_sync_on_save(db, enable_airtable_sync, mock_airtable_table):
        VotePreferenceFactory()
        mock_airtable_table.create.assert_called()

    def it_skips_sync_when_flag_set(db, enable_airtable_sync, mock_airtable_table):
        vote = VotePreferenceFactory()
        mock_airtable_table.reset_mock()
        vote._skip_airtable_sync = True  # type: ignore[attr-defined]
        vote.save()
        mock_airtable_table.update.assert_not_called()


def describe_vote_preference_delete_triggers_sync():
    def it_calls_delete_on_airtable(db, enable_airtable_sync, mock_airtable_table):
        vote = VotePreferenceFactory(airtable_record_id="recVOTEDEL123456")
        mock_airtable_table.reset_mock()
        vote.delete()
        mock_airtable_table.delete.assert_called_once_with("recVOTEDEL123456")

    def it_skips_delete_when_no_record_id(db, enable_airtable_sync, mock_airtable_table):
        from membership.models import VotePreference

        vote = VotePreferenceFactory(airtable_record_id=None)
        VotePreference.objects.filter(pk=vote.pk).update(airtable_record_id=None)
        vote.refresh_from_db()
        mock_airtable_table.reset_mock()
        vote.delete()
        mock_airtable_table.delete.assert_not_called()

    def it_skips_delete_when_skip_flag_set(db, enable_airtable_sync, mock_airtable_table):
        vote = VotePreferenceFactory(airtable_record_id="recVOTESKIP12345")
        mock_airtable_table.reset_mock()
        vote._skip_airtable_sync = True  # type: ignore[attr-defined]
        vote.delete()
        mock_airtable_table.delete.assert_not_called()


# ---------------------------------------------------------------------------
# FundingSnapshot — pushes to Airtable on save
# ---------------------------------------------------------------------------


def describe_funding_snapshot_save_triggers_sync():
    def it_calls_sync_on_save(db, enable_airtable_sync, mock_airtable_table):
        FundingSnapshotFactory()
        mock_airtable_table.create.assert_called()

    def it_skips_sync_when_flag_set(db, enable_airtable_sync, mock_airtable_table):
        snapshot = FundingSnapshotFactory()
        mock_airtable_table.reset_mock()
        snapshot._skip_airtable_sync = True  # type: ignore[attr-defined]
        snapshot.save()
        mock_airtable_table.update.assert_not_called()
