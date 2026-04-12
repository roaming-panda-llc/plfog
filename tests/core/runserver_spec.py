"""BDD-style tests for the auto-migrate runserver management command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.django_db


def _run_handle(debug: bool) -> str:
    """Invoke Command.handle() with a captured stdout, stubbing out the real server start."""
    from core.management.commands.runserver import Command

    stdout = StringIO()
    cmd = Command(stdout=stdout, stderr=StringIO())
    with patch.object(type(cmd).__mro__[1], "handle"):  # stub BaseRunserver.handle
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DEBUG = debug
            cmd.handle(addrport="8000", use_reloader=False)
    return stdout.getvalue()


def describe_runserver_auto_migrate():
    def it_runs_migrate_when_debug_and_unapplied():
        from core.management.commands.runserver import Command

        stdout = StringIO()
        cmd = Command(stdout=stdout, stderr=StringIO())

        with (
            patch("core.management.commands.runserver.settings") as mock_settings,
            patch("core.management.commands.runserver.call_command") as mock_cc,
            patch("django.core.management.commands.runserver.Command.handle"),
        ):
            mock_settings.DEBUG = True
            mock_cc.side_effect = [SystemExit(1), None]
            cmd.handle(addrport="8000", use_reloader=False)

        output = stdout.getvalue()
        assert "[dev] Checking for unapplied migrations" in output
        assert "[dev] Unapplied migrations detected" in output

    def it_skips_migrate_when_debug_and_all_applied():
        from core.management.commands.runserver import Command

        stdout = StringIO()
        cmd = Command(stdout=stdout, stderr=StringIO())

        with (
            patch("core.management.commands.runserver.settings") as mock_settings,
            patch("core.management.commands.runserver.call_command") as mock_cc,
            patch("django.core.management.commands.runserver.Command.handle"),
        ):
            mock_settings.DEBUG = True
            mock_cc.return_value = None
            cmd.handle(addrport="8000", use_reloader=False)

        output = stdout.getvalue()
        assert "[dev] All migrations applied" in output
        assert "Unapplied" not in output

    def it_skips_check_entirely_when_not_debug():
        from core.management.commands.runserver import Command

        stdout = StringIO()
        cmd = Command(stdout=stdout, stderr=StringIO())

        with (
            patch("core.management.commands.runserver.settings") as mock_settings,
            patch("core.management.commands.runserver.call_command") as mock_cc,
            patch("django.core.management.commands.runserver.Command.handle"),
        ):
            mock_settings.DEBUG = False
            cmd.handle(addrport="8000", use_reloader=False)

        mock_cc.assert_not_called()
        assert "[dev]" not in stdout.getvalue()
