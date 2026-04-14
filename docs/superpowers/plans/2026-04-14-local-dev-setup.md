# Local Dev Setup & Prod DB Pull — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any developer can clone the repo, run a few commands, and have a fully working local environment with production data and frictionless login.

**Architecture:** Docker Compose runs PostgreSQL locally. A management command pulls the production database via `pg_dump`/`psql`. The allauth adapter shows the login code in the Django messages banner when `DEBUG=True`. A Makefile and `.env.example` standardize the developer workflow.

**Tech Stack:** Docker Compose, PostgreSQL 18, Django management commands, allauth adapter override, Make

---

### Task 1: Docker Compose for Local PostgreSQL

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:18
    environment:
      POSTGRES_DB: plfog
      POSTGRES_USER: plfog
      POSTGRES_PASSWORD: plfog
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql

volumes:
  pgdata:
```

- [ ] **Step 2: Verify it starts**

Run: `docker compose up -d && docker compose ps`
Expected: `db` service is running and healthy on port 5432.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "infra: add Docker Compose for local PostgreSQL"
```

---

### Task 2: `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

This lists every `os.environ.get()` from `plfog/settings.py`, grouped by concern, with sensible local defaults and comments. The `DATABASE_URL` default points to the Docker Compose Postgres.

```bash
# ===========================================
# Database
# ===========================================
# Local Docker Compose default — no changes needed for standard setup
DATABASE_URL=postgres://plfog:plfog@localhost:5432/plfog

# Production DB — only needed for `make db-pull-prod`
# Get this from Render dashboard > plfog database > External Connection String
PROD_DATABASE_URL=

# ===========================================
# Django
# ===========================================
DJANGO_SECRET_KEY=django-insecure-dev-key-change-in-production
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# ===========================================
# Stripe (optional for local dev)
# ===========================================
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_FIELD_ENCRYPTION_KEY=

# ===========================================
# Email (optional — DEBUG mode prints to console)
# ===========================================
RESEND_API_KEY=
DEFAULT_FROM_EMAIL=noreply@pastlives.space
BETA_FEEDBACK_EMAILS=josh@plaza.codes

# ===========================================
# Airtable Sync (optional)
# ===========================================
AIRTABLE_API_TOKEN=
AIRTABLE_BASE_ID=
AIRTABLE_SYNC_ENABLED=false

# ===========================================
# Web Push (optional)
# ===========================================
WEBPUSH_VAPID_PUBLIC_KEY=
WEBPUSH_VAPID_PRIVATE_KEY=
WEBPUSH_VAPID_ADMIN_EMAIL=

# ===========================================
# Sentry (optional)
# ===========================================
SENTRY_DSN=

# ===========================================
# Allauth
# ===========================================
ALLAUTH_TRUSTED_PROXY_COUNT=0

# ===========================================
# Infrastructure (set automatically on Render — ignore locally)
# ===========================================
# RENDER_EXTERNAL_HOSTNAME=
# CSRF_TRUSTED_ORIGINS=
# ADMIN_DOMAINS=
```

- [ ] **Step 2: Verify `.env.example` is tracked by git**

`.gitignore` already has `!.env.example` so it will be tracked. Verify:

Run: `git check-ignore .env.example`
Expected: No output (not ignored).

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example with all local dev defaults"
```

---

### Task 3: Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create `Makefile`**

```makefile
.DEFAULT_GOAL := help

# Load .env if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

.PHONY: help setup install db-up db-down db-pull-prod migrate server test lint format

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup: .env, venv, deps, migrate
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — edit it if needed")
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Setup complete. Next steps:"
	@echo "  1. make db-up        (start PostgreSQL)"
	@echo "  2. make migrate      (create tables)"
	@echo "  3. make server       (start dev server)"
	@echo ""
	@echo "Optional: set PROD_DATABASE_URL in .env, then run 'make db-pull-prod' to load production data."

install: ## Install Python dependencies into venv
	.venv/bin/pip install -r requirements.txt

db-up: ## Start PostgreSQL via Docker Compose
	docker compose up -d
	@echo "PostgreSQL running on localhost:5432"

db-down: ## Stop PostgreSQL
	docker compose down

db-pull-prod: ## Download production database into local Postgres
	.venv/bin/python manage.py pull_prod_db

migrate: ## Run Django migrations
	.venv/bin/python manage.py migrate

server: ## Start Django dev server
	.venv/bin/python manage.py runserver

test: ## Run tests
	.venv/bin/pytest

lint: ## Run ruff linter and formatter check
	.venv/bin/ruff check . && .venv/bin/ruff format --check .

format: ## Auto-format code with ruff
	.venv/bin/ruff format . && .venv/bin/ruff check --fix .
```

**Important:** Makefile rules require literal tab characters for indentation, not spaces. Ensure your editor writes tabs.

- [ ] **Step 2: Verify `make help` works**

Run: `make help`
Expected: Formatted list of all targets with descriptions.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "infra: add Makefile with developer commands"
```

---

### Task 4: `pull_prod_db` Management Command — Tests

**Files:**
- Create: `tests/core/pull_prod_db_spec.py`

The management command shells out to `pg_dump` and `psql`. Tests should mock `subprocess.run` to avoid needing a real prod database. Test the guard rails: DEBUG check, missing env vars, user confirmation.

- [ ] **Step 1: Create `tests/core/pull_prod_db_spec.py`**

```python
"""BDD-style tests for the pull_prod_db management command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import call, patch

import pytest
from django.core.management import CommandError, call_command


def describe_pull_prod_db():
    def describe_guard_rails():
        def it_refuses_to_run_when_debug_is_false(settings):
            settings.DEBUG = False
            with pytest.raises(CommandError, match="DEBUG is not True"):
                call_command("pull_prod_db", "--no-input", stdout=StringIO())

        @patch.dict("os.environ", {"PROD_DATABASE_URL": ""}, clear=False)
        def it_refuses_when_prod_database_url_is_empty(settings):
            settings.DEBUG = True
            with pytest.raises(CommandError, match="PROD_DATABASE_URL is not set"):
                call_command("pull_prod_db", "--no-input", stdout=StringIO())

        @patch.dict("os.environ", {"PROD_DATABASE_URL": "postgres://prod:5432/db"}, clear=False)
        def it_refuses_when_local_db_is_sqlite(settings):
            settings.DEBUG = True
            settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}}
            with pytest.raises(CommandError, match="local database must be PostgreSQL"):
                call_command("pull_prod_db", "--no-input", stdout=StringIO())

    def describe_interactive_confirmation():
        @patch.dict("os.environ", {"PROD_DATABASE_URL": "postgres://prod:5432/db"}, clear=False)
        @patch("builtins.input", return_value="n")
        def it_aborts_when_user_declines(mock_input, settings):
            settings.DEBUG = True
            out = StringIO()
            call_command("pull_prod_db", stdout=out)
            assert "Aborted" in out.getvalue()

    def describe_successful_pull():
        @patch.dict(
            "os.environ",
            {"PROD_DATABASE_URL": "postgres://user:pass@host:5432/proddb"},
            clear=False,
        )
        @patch("core.management.commands.pull_prod_db.call_command")
        @patch("subprocess.run")
        def it_dumps_and_loads_prod_data(mock_run, mock_call_command, settings, tmp_path):
            settings.DEBUG = True
            mock_run.return_value.returncode = 0

            out = StringIO()
            call_command("pull_prod_db", "--no-input", stdout=out)

            # Should call pg_dump and psql
            commands_run = [c.args[0][0] for c in mock_run.call_args_list]
            assert "pg_dump" in commands_run
            assert "psql" in commands_run

            # Should run migrate after loading
            mock_call_command.assert_called_once_with("migrate", verbosity=1, stdout=out)

            output = out.getvalue()
            assert "production data" in output.lower() or "Done" in output

        @patch.dict(
            "os.environ",
            {"PROD_DATABASE_URL": "postgres://user:pass@host:5432/proddb"},
            clear=False,
        )
        @patch("core.management.commands.pull_prod_db.call_command")
        @patch("subprocess.run")
        def it_fails_gracefully_on_pg_dump_error(mock_run, mock_call_command, settings):
            settings.DEBUG = True
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "connection refused"

            with pytest.raises(CommandError, match="pg_dump failed"):
                call_command("pull_prod_db", "--no-input", stdout=StringIO())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/pull_prod_db_spec.py -v`
Expected: FAIL — `CommandError: Unknown command: 'pull_prod_db'`

---

### Task 5: `pull_prod_db` Management Command — Implementation

**Files:**
- Create: `core/management/commands/pull_prod_db.py`

- [ ] **Step 1: Create `core/management/commands/pull_prod_db.py`**

```python
"""Download the production database into local PostgreSQL.

Usage:
    python manage.py pull_prod_db          # interactive confirmation
    python manage.py pull_prod_db --no-input  # skip confirmation (CI/scripts)

Requires:
    - PROD_DATABASE_URL env var (Render external connection string)
    - Local DATABASE_URL pointing to PostgreSQL (not SQLite)
    - pg_dump and psql available on PATH
    - DEBUG=True (refuses to run in production)
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Download the production database into your local PostgreSQL."

    def add_arguments(self, parser: object) -> None:
        parser.add_argument("--no-input", action="store_true", help="Skip confirmation prompt")

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            raise CommandError("Refusing to run: DEBUG is not True.")

        prod_url = os.environ.get("PROD_DATABASE_URL", "")
        if not prod_url:
            raise CommandError("PROD_DATABASE_URL is not set. Add it to your .env file.")

        db_engine = settings.DATABASES["default"].get("ENGINE", "")
        if "sqlite" in db_engine:
            raise CommandError(
                "Your local database must be PostgreSQL, not SQLite. "
                "Set DATABASE_URL in your .env and run 'make db-up'."
            )

        local_url = os.environ.get("DATABASE_URL", "")

        if not options["no_input"]:
            confirm = input("This will REPLACE your local database with production data. Continue? [y/N] ")
            if confirm.lower() != "y":
                self.stdout.write("Aborted.")
                return

        self.stdout.write(self.style.NOTICE("Dumping production database..."))

        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as dump_file:
            dump_path = dump_file.name

        try:
            # pg_dump from production
            result = subprocess.run(
                ["pg_dump", "--no-owner", "--no-acl", "--clean", "--if-exists", "-f", dump_path, prod_url],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise CommandError(f"pg_dump failed: {result.stderr}")

            self.stdout.write(self.style.NOTICE("Loading into local database..."))

            # psql into local
            result = subprocess.run(
                ["psql", "-f", dump_path, local_url],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise CommandError(f"psql failed: {result.stderr}")

        finally:
            os.unlink(dump_path)

        self.stdout.write(self.style.NOTICE("Running migrations..."))
        call_command("migrate", verbosity=1, stdout=self.stdout)

        self.stdout.write(self.style.SUCCESS("Done — loaded production data into local database."))
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/core/pull_prod_db_spec.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Run linter**

Run: `ruff check core/management/commands/pull_prod_db.py && ruff format --check core/management/commands/pull_prod_db.py`
Expected: Clean.

- [ ] **Step 4: Commit**

```bash
git add core/management/commands/pull_prod_db.py tests/core/pull_prod_db_spec.py
git commit -m "feat: add pull_prod_db management command"
```

---

### Task 6: Dev-Mode Login Code Display — Tests

**Files:**
- Modify: `tests/plfog/adapters_spec.py`

The adapter override works in two parts:
1. `send_mail` stashes the code on the request when `DEBUG=True` and the template is `account/email/login_code`
2. `add_message` reads the stashed code and appends a `[DEV]` Django message

- [ ] **Step 1: Add tests to `tests/plfog/adapters_spec.py`**

Add these test blocks inside `describe_AdminRedirectAccountAdapter()`:

```python
    def describe_send_mail():
        def it_stashes_login_code_on_request_in_debug_mode(rf, settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.DEBUG = True
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            context = {"request": request, "code": "123456"}

            with patch.object(AdminRedirectAccountAdapter.__bases__[0], "send_mail"):
                adapter.send_mail("account/email/login_code", "user@example.com", context)

            assert request._dev_login_code == "123456"

        def it_does_not_stash_code_when_debug_is_false(rf, settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.DEBUG = False
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            context = {"request": request, "code": "123456"}

            with patch.object(AdminRedirectAccountAdapter.__bases__[0], "send_mail"):
                adapter.send_mail("account/email/login_code", "user@example.com", context)

            assert not hasattr(request, "_dev_login_code")

        def it_does_not_stash_code_for_other_templates(rf, settings):
            from plfog.adapters import AdminRedirectAccountAdapter

            settings.DEBUG = True
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            context = {"request": request, "code": "123456"}

            with patch.object(AdminRedirectAccountAdapter.__bases__[0], "send_mail"):
                adapter.send_mail("account/email/password_reset", "user@example.com", context)

            assert not hasattr(request, "_dev_login_code")

    def describe_add_message():
        def it_appends_dev_code_message_when_code_is_stashed(rf, settings):
            from django.contrib.messages import get_messages
            from django.contrib.messages.storage.fallback import FallbackStorage

            from plfog.adapters import AdminRedirectAccountAdapter

            settings.DEBUG = True
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            # Django messages middleware setup
            setattr(request, "session", {})
            setattr(request, "_messages", FallbackStorage(request))
            request._dev_login_code = "654321"

            adapter.add_message(
                request,
                messages.SUCCESS,
                message_template="account/messages/login_code_sent.txt",
                message_context={"recipient": "user@example.com", "email": "user@example.com"},
            )

            all_messages = [str(m) for m in get_messages(request)]
            assert any("[DEV] Your login code is: 654321" in m for m in all_messages)

        def it_does_not_append_code_when_none_stashed(rf, settings):
            from django.contrib.messages import get_messages
            from django.contrib.messages.storage.fallback import FallbackStorage

            from plfog.adapters import AdminRedirectAccountAdapter

            settings.DEBUG = True
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            setattr(request, "session", {})
            setattr(request, "_messages", FallbackStorage(request))

            adapter.add_message(
                request,
                messages.SUCCESS,
                message_template="account/messages/login_code_sent.txt",
                message_context={"recipient": "user@example.com", "email": "user@example.com"},
            )

            all_messages = [str(m) for m in get_messages(request)]
            assert not any("[DEV]" in m for m in all_messages)

        def it_cleans_up_stashed_code_after_use(rf, settings):
            from django.contrib.messages.storage.fallback import FallbackStorage

            from plfog.adapters import AdminRedirectAccountAdapter

            settings.DEBUG = True
            adapter = AdminRedirectAccountAdapter()
            request = rf.get("/")
            setattr(request, "session", {})
            setattr(request, "_messages", FallbackStorage(request))
            request._dev_login_code = "111222"

            adapter.add_message(
                request,
                messages.SUCCESS,
                message_template="account/messages/login_code_sent.txt",
                message_context={"recipient": "user@example.com", "email": "user@example.com"},
            )

            assert not hasattr(request, "_dev_login_code")
```

Note: You'll need to add `from django.contrib import messages` to the imports at the top of the file.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/plfog/adapters_spec.py -k "send_mail or add_message" -v`
Expected: FAIL — `AdminRedirectAccountAdapter` has no `send_mail` or `add_message` override yet.

---

### Task 7: Dev-Mode Login Code Display — Implementation

**Files:**
- Modify: `plfog/adapters.py`

- [ ] **Step 1: Add `send_mail` and `add_message` overrides to `AdminRedirectAccountAdapter`**

Add these two methods to the `AdminRedirectAccountAdapter` class in `plfog/adapters.py`, after the existing `_sync_permissions` method:

```python
    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        """In DEBUG mode, stash the login code on the request for display in the UI."""
        if settings.DEBUG and template_prefix == "account/email/login_code" and "code" in context:
            request = context.get("request")
            if request:
                request._dev_login_code = context["code"]
        super().send_mail(template_prefix, email, context)

    def add_message(
        self,
        request: HttpRequest,
        level: int,
        message_template: str | None = None,
        message_context: dict | None = None,
        extra_tags: str = "",
        message: str | None = None,
    ) -> None:
        """In DEBUG mode, append the login code to the 'code sent' message."""
        super().add_message(request, level, message_template, message_context, extra_tags=extra_tags, message=message)
        if settings.DEBUG and hasattr(request, "_dev_login_code"):
            from django.contrib import messages

            messages.success(request, f"[DEV] Your login code is: {request._dev_login_code}")
            del request._dev_login_code
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/plfog/adapters_spec.py -k "send_mail or add_message" -v`
Expected: All PASS.

- [ ] **Step 3: Run the full adapter test suite**

Run: `pytest tests/plfog/adapters_spec.py -v`
Expected: All PASS (no regressions).

- [ ] **Step 4: Run linter**

Run: `ruff check plfog/adapters.py && ruff format --check plfog/adapters.py`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add plfog/adapters.py tests/plfog/adapters_spec.py
git commit -m "feat: show login code in banner during local dev (DEBUG=True)"
```

---

### Task 8: Full Test Suite & Coverage Check

- [ ] **Step 1: Run full test suite**

Run: `pytest -q`
Expected: All tests pass, 100% coverage maintained.

- [ ] **Step 2: Run linter on entire project**

Run: `ruff check . && ruff format --check .`
Expected: Clean.

- [ ] **Step 3: Run type checker**

Run: `mypy .`
Expected: No new errors.

---

### Task 9: Version Bump & Changelog

**Files:**
- Modify: `plfog/version.py`

Note: The hotfix branch already has version 1.5.2 for the center cart toast. This work should be included in the same release or bumped to 1.6.0 since it adds new features (management command, Makefile, Docker Compose). Decide based on whether the cart toast hotfix is being shipped separately.

- [ ] **Step 1: Update version and changelog**

If shipping together with the cart toast fix as a feature release, update the existing 1.5.2 entry or bump to 1.6.0. Add changelog entries:

```python
{
    "version": "1.6.0",
    "date": "2026-04-14",
    "title": "Local Dev Setup & Cart Toast Fix",
    "changes": [
        "New developer setup: clone, make setup, make server — and you're running locally with PostgreSQL",
        "New 'make db-pull-prod' command downloads a copy of the production database for local testing",
        "Login codes now appear directly on screen during local development — no more checking the terminal",
        "The 'added to cart' notification now appears in the center of the screen instead of covering the tab balance",
    ],
},
```

- [ ] **Step 2: Run tests to confirm version bump doesn't break anything**

Run: `pytest tests/plfog/version_spec.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add plfog/version.py
git commit -m "chore: bump version to 1.6.0 with changelog"
```
