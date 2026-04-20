"""BDD specs for the new instructor role in view_as."""

from __future__ import annotations

from django.test import RequestFactory

from classes.factories import InstructorFactory
from hub.view_as import ROLE_INSTRUCTOR, ViewAs, compute_actual_roles


def describe_instructor_role():
    def it_is_included_when_user_has_instructor_record(db):
        instructor = InstructorFactory()
        roles = compute_actual_roles(instructor.user)
        assert ROLE_INSTRUCTOR in roles

    def it_is_not_included_when_user_has_no_instructor(db, member_user):
        roles = compute_actual_roles(member_user)
        assert ROLE_INSTRUCTOR not in roles

    def it_is_exposed_as_is_instructor_property(db):
        instructor = InstructorFactory()
        request = RequestFactory().get("/")
        request.user = instructor.user
        # Set a minimal session for ViewAs.for_request()
        request.session = {}
        view_as = ViewAs.for_request(request)
        assert view_as.is_instructor is True
