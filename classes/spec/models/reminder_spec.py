"""BDD specs for RegistrationReminder."""

from __future__ import annotations

import pytest
from django.db.utils import IntegrityError

from classes.factories import (
    ClassSessionFactory,
    RegistrationFactory,
    RegistrationReminderFactory,
)


def describe_RegistrationReminder():
    def it_enforces_unique_registration_session_pair(db):
        reg = RegistrationFactory()
        session = ClassSessionFactory()
        RegistrationReminderFactory(registration=reg, session=session)
        with pytest.raises(IntegrityError):
            RegistrationReminderFactory(registration=reg, session=session)

    def it_stringifies_with_registration_and_session_ids(db):
        reg = RegistrationFactory()
        session = ClassSessionFactory()
        reminder = RegistrationReminderFactory(registration=reg, session=session)
        assert str(reminder) == f"Reminder for registration {reg.pk} → session {session.pk}"
