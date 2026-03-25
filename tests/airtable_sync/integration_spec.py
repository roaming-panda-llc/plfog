"""Integration tests — verify model save()/delete() triggers Airtable sync."""

from __future__ import annotations

from unittest.mock import patch

from tests.membership.factories import MemberFactory, SpaceFactory


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

        from tests.membership.factories import MembershipPlanFactory

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
        member = MemberFactory(airtable_record_id=None)
        # save() triggered sync and set record_id; clear it for this test
        from membership.models import Member

        Member.objects.filter(pk=member.pk).update(airtable_record_id=None)
        member.refresh_from_db()
        mock_airtable_table.reset_mock()
        member.delete()
        mock_airtable_table.delete.assert_not_called()


def describe_space_save_triggers_sync():
    def it_calls_sync_on_save(db, enable_airtable_sync, mock_airtable_table):
        SpaceFactory()
        mock_airtable_table.create.assert_called()


def describe_space_delete_triggers_sync():
    def it_calls_delete_on_airtable(db, enable_airtable_sync, mock_airtable_table):
        space = SpaceFactory(airtable_record_id="recSPACEDEL12345")
        mock_airtable_table.reset_mock()
        space.delete()
        mock_airtable_table.delete.assert_called_once_with("recSPACEDEL12345")
