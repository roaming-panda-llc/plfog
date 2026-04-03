"""BDD specs for guild pages views."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from membership.models import Guild
from tests.membership.factories import GuildFactory, MemberFactory


@pytest.mark.django_db
def describe_guild_about_field():
    def it_defaults_to_empty_string():
        guild = GuildFactory()
        assert guild.about == ""

    def it_stores_about_text():
        guild = GuildFactory(about="Welcome to our guild!")
        guild.refresh_from_db()
        assert guild.about == "Welcome to our guild!"
