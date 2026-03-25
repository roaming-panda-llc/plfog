"""Integration tests — verify model save()/delete() triggers Airtable sync."""

from __future__ import annotations

from unittest.mock import patch

from tests.membership.factories import (
    FundingSnapshotFactory,
    LeaseFactory,
    MemberFactory,
    MembershipPlanFactory,
    SpaceFactory,
    VotePreferenceFactory,
)


def describe_member_save_triggers_sync():
    def it_calls_sync_on_save(db, enable_airtable_sync, mock_airtable_table):
        MemberFactory()
        mock_airtable_table.create.assert_called()

    def it_does_not_call_sync_when_disabled(db):
        with patch("airtable_sync.service.get_table") as mock_get:
            MemberFactory()
            mock_get.assert_not_called()

    def it_does_not_call_sync_when_skip_flag_set(db, enable_airtable_sync, mock_airtable_table):
        from membership.models import Member

        plan = MembershipPlanFactory()
        member = Member(full_legal_name="Test", membership_plan=plan)
        member._skip_airtable_sync = True  # type: ignore[attr-defined]
        member.save()
        mock_airtable_table.create.assert_not_called()


def describe_member_delete_triggers_sync():
    def it_calls_delete_on_airtable(db, enable_airtable_sync, mock_airtable_table):
        member = MemberFactory(airtable_record_id="recDELETEME12345")
        mock_airtable_table.reset_mock()
        member.delete()
        mock_airtable_table.delete.assert_called_once_with("recDELETEME12345")

    def it_skips_delete_when_no_record_id(db, enable_airtable_sync, mock_airtable_table):
        from membership.models import Member

        member = MemberFactory(airtable_record_id=None)
        Member.objects.filter(pk=member.pk).update(airtable_record_id=None)
        member.refresh_from_db()
        mock_airtable_table.reset_mock()
        member.delete()
        mock_airtable_table.delete.assert_not_called()


def describe_space_save_triggers_sync():
    def it_calls_sync_on_save(db, enable_airtable_sync, mock_airtable_table):
        SpaceFactory()
        mock_airtable_table.create.assert_called()

    def it_skips_sync_when_flag_set(db, enable_airtable_sync, mock_airtable_table):
        space = SpaceFactory()
        mock_airtable_table.reset_mock()
        space._skip_airtable_sync = True  # type: ignore[attr-defined]
        space.save()
        mock_airtable_table.update.assert_not_called()


def describe_space_delete_triggers_sync():
    def it_calls_delete_on_airtable(db, enable_airtable_sync, mock_airtable_table):
        space = SpaceFactory(airtable_record_id="recSPACEDEL12345")
        mock_airtable_table.reset_mock()
        space.delete()
        mock_airtable_table.delete.assert_called_once_with("recSPACEDEL12345")

    def it_skips_delete_when_skip_flag_set(db, enable_airtable_sync, mock_airtable_table):
        space = SpaceFactory(airtable_record_id="recSPACESKIP12345")
        mock_airtable_table.reset_mock()
        space._skip_airtable_sync = True  # type: ignore[attr-defined]
        space.delete()
        mock_airtable_table.delete.assert_not_called()


def describe_lease_save_triggers_sync():
    def it_calls_sync_on_save(db, enable_airtable_sync, mock_airtable_table):
        LeaseFactory()
        mock_airtable_table.create.assert_called()

    def it_skips_sync_when_flag_set(db, enable_airtable_sync, mock_airtable_table):
        lease = LeaseFactory()
        mock_airtable_table.reset_mock()
        lease._skip_airtable_sync = True  # type: ignore[attr-defined]
        lease.save()
        mock_airtable_table.update.assert_not_called()


def describe_lease_delete_triggers_sync():
    def it_calls_delete_on_airtable(db, enable_airtable_sync, mock_airtable_table):
        lease = LeaseFactory(airtable_record_id="recLEASEDEL12345")
        mock_airtable_table.reset_mock()
        lease.delete()
        mock_airtable_table.delete.assert_called_once_with("recLEASEDEL12345")

    def it_skips_delete_when_no_record_id(db, enable_airtable_sync, mock_airtable_table):
        from membership.models import Lease

        lease = LeaseFactory(airtable_record_id=None)
        Lease.objects.filter(pk=lease.pk).update(airtable_record_id=None)
        lease.refresh_from_db()
        mock_airtable_table.reset_mock()
        lease.delete()
        mock_airtable_table.delete.assert_not_called()

    def it_skips_delete_when_skip_flag_set(db, enable_airtable_sync, mock_airtable_table):
        lease = LeaseFactory(airtable_record_id="recLEASESKIP12345")
        mock_airtable_table.reset_mock()
        lease._skip_airtable_sync = True  # type: ignore[attr-defined]
        lease.delete()
        mock_airtable_table.delete.assert_not_called()


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
