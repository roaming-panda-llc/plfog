"""BDD specs for the new instructor role in view_as."""

from __future__ import annotations

from django.test import RequestFactory

from django.contrib.auth.models import AnonymousUser

from classes.factories import InstructorFactory
from hub.view_as import ROLE_GUEST, ROLE_INSTRUCTOR, ROLE_MEMBER, ViewAs, compute_actual_roles


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
        request.session = {}
        view_as = ViewAs.for_request(request)
        assert view_as.is_instructor is True


def describe_guest_role():
    def it_is_assigned_to_anonymous_users(db):
        roles = compute_actual_roles(AnonymousUser())
        assert roles == frozenset({ROLE_GUEST})

    def it_exposes_is_guest_on_view_as(db):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        request.session = {}
        view_as = ViewAs.for_request(request)
        assert view_as.is_guest is True
        assert view_as.is_admin is False
        assert view_as.is_member is False


def describe_non_member_instructor_label():
    def it_labels_instructor_without_active_member_as_non_member_instructor(db):
        from membership.models import Member

        instructor = InstructorFactory()
        # The ensure_user_has_member signal auto-creates Member with Status.ACTIVE;
        # an "instructor-only" account is one whose placeholder Member is Invited.
        Member.objects.filter(user=instructor.user).update(status=Member.Status.INVITED)
        request = RequestFactory().get("/")
        request.user = instructor.user
        request.session = {}
        view_as = ViewAs.for_request(request)
        assert view_as.is_non_member_instructor is True
        assert view_as.instructor_label == "Non-member Instructor"
        assert ROLE_MEMBER not in view_as.actual

    def it_labels_member_instructor_just_as_instructor(db, member_user):
        # member_user fixture creates a real ACTIVE member; make them an instructor too.
        InstructorFactory(user=member_user)
        request = RequestFactory().get("/")
        request.user = member_user
        request.session = {}
        view_as = ViewAs.for_request(request)
        assert view_as.is_non_member_instructor is False
        assert view_as.instructor_label == "Instructor"
