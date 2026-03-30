import pytest
from django.db import IntegrityError

from membership.models import MemberEmail
from tests.membership.factories import MemberFactory


@pytest.mark.django_db
def describe_MemberEmail():
    def it_stores_an_alias_email_for_a_member():
        member = MemberFactory()
        alias = MemberEmail.objects.create(member=member, email="alias@example.com")
        assert alias.member == member
        assert alias.email == "alias@example.com"
        assert alias.is_primary is False

    def it_enforces_unique_email():
        member = MemberFactory()
        MemberEmail.objects.create(member=member, email="dupe@example.com")
        with pytest.raises(IntegrityError):
            MemberEmail.objects.create(member=member, email="dupe@example.com")

    def it_has_str_representation():
        member = MemberFactory(full_legal_name="Jane Doe")
        alias = MemberEmail.objects.create(member=member, email="jane@alt.com")
        assert str(alias) == "jane@alt.com (Jane Doe)"

    def it_cascades_on_member_delete():
        member = MemberFactory()
        MemberEmail.objects.create(member=member, email="gone@example.com")
        member_id = member.pk
        member.delete()
        assert not MemberEmail.objects.filter(member_id=member_id).exists()
