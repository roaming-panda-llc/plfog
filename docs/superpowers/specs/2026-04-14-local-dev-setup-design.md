# Local Dev Setup & Prod DB Pull — Design Spec

**Date:** 2026-04-14
**Status:** Draft
**Goal:** Any developer can clone the repo, run a few commands, and have a fully working local environment with production data.

---

## 1. Problem

Local dev currently uses SQLite with no seed data. Developers can't test against real guilds, members, products, or tab entries. The passwordless login flow requires checking the terminal console for the 6-digit code, which is annoying. There are no setup instructions or standardized commands.

## 2. Solution Overview

| Component | What it does |
|-----------|-------------|
| `docker-compose.yml` | Runs PostgreSQL 18 locally (nothing else in Docker) |
| `.env.example` | Documents every env var with sensible local defaults |
| `Makefile` | Standardized commands: `make setup`, `make server`, `make db-pull-prod`, etc. |
| `pull_prod_db` management command | Downloads the Render production database into local Postgres |
| Dev-mode login code display | Shows the 6-digit code in the green banner instead of requiring email/console |

## 3. Docker Compose — Local PostgreSQL

A minimal `docker-compose.yml` at the project root. Only Postgres — the Django app runs natively in the venv.

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

Default local `DATABASE_URL`: `postgres://plfog:plfog@localhost:5432/plfog`

## 4. Environment Variables — `.env.example`

Lists every `os.environ.get()` from `settings.py` with placeholder values and comments. Grouped by concern.

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

The `Makefile setup` target copies `.env.example` → `.env` if `.env` doesn't already exist.

## 5. Makefile

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

setup: ## First-time setup: .env, venv, deps, DB, migrate
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Run 'make db-up' to start PostgreSQL, then 'make migrate' to set up tables."

install: ## Install Python dependencies into venv
	.venv/bin/pip install -r requirements.txt

db-up: ## Start PostgreSQL via Docker Compose
	docker compose up -d

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

lint: ## Run ruff linter
	.venv/bin/ruff check .

format: ## Run ruff formatter
	.venv/bin/ruff format .
```

## 6. Management Command — `pull_prod_db`

**Location:** `core/management/commands/pull_prod_db.py`

**Behavior:**
1. Reads `PROD_DATABASE_URL` from environment
2. Refuses to run if `DEBUG` is not `True` (safety check)
3. Confirms with the user: "This will REPLACE your local database with production data. Continue? [y/N]"
4. Runs `pg_dump` against the Render Postgres (external connection string)
5. Drops and recreates the local `plfog` database
6. Loads the dump via `psql`
7. Runs `migrate` to apply any pending local migrations not yet in prod
8. Prints summary: "Done — loaded production data into local database."

**Requirements:**
- `pg_dump` and `psql` must be available locally. These come with the `postgresql-client` package (Linux/WSL) or Homebrew `libpq` (Mac). Docker Desktop also includes them.
- The Render database must allow external connections (it does — external connection string is in the Render dashboard).

**Implementation sketch:**

```python
class Command(BaseCommand):
    help = "Download the production database into your local PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--no-input", action="store_true", help="Skip confirmation prompt")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to run: DEBUG is not True.")

        prod_url = os.environ.get("PROD_DATABASE_URL")
        if not prod_url:
            raise CommandError("PROD_DATABASE_URL is not set.")

        local_url = os.environ.get("DATABASE_URL")
        if not local_url or "sqlite" in local_url:
            raise CommandError("DATABASE_URL must point to a PostgreSQL database.")

        if not options["no_input"]:
            confirm = input("This will REPLACE your local database with production data. Continue? [y/N] ")
            if confirm.lower() != "y":
                self.stdout.write("Aborted.")
                return

        # 1. pg_dump from prod
        # 2. dropdb + createdb locally
        # 3. psql load dump
        # 4. migrate
```

**`--no-input` flag** for CI/scripting use without interactive prompt.

## 7. Dev-Mode Login Code Display

**Goal:** When `DEBUG=True`, show the 6-digit login code directly in the green Django messages banner on the "Check Your Email" page, so developers never need to check the console.

**Approach:** Override allauth's message template. Allauth sends a Django message using the template `account/messages/login_code_sent.txt`. The default says:

> "A sign-in code has been sent to {recipient}."

We already have a `templates/` directory that takes priority over allauth's built-in templates (`DIRS` comes before `APP_DIRS` in settings). We'll create a custom template at:

```
templates/account/messages/login_code_sent.txt
```

However, the message template doesn't receive the code — it only gets `recipient` and `email`/`phone` context. The code is stored in the session state, not passed to the message.

**Solution:** Override `add_message` in the existing `AdminRedirectAccountAdapter` to intercept the login-code-sent message and append the code from the session state when `DEBUG=True`.

```python
# In plfog/adapters.py — add to AdminRedirectAccountAdapter

def add_message(self, request, level, message_template, message_context=None, *args, **kwargs):
    super().add_message(request, level, message_template, message_context, *args, **kwargs)
    if settings.DEBUG and message_template == "account/messages/login_code_sent.txt":
        # The code is in the stashed login state in the session
        from allauth.account.internal.stagekit import get_pending_stage
        stage = get_pending_stage(request)
        if stage and "code" in stage.state:
            messages.success(request, f"[DEV] Your login code is: {stage.state['code']}")
```

This is minimal, safe (only fires in DEBUG), and doesn't modify any allauth internals. The dev sees two messages: the normal "code sent" message plus a `[DEV] Your login code is: 123456` message in the green banner.

**Alternative considered:** Override the `confirm_login_code.html` template to read from the session. Rejected because the session state is in an allauth-internal format and accessing it from a template is fragile.

## 8. Files Changed

| File | Action | Description |
|------|--------|-------------|
| `docker-compose.yml` | Create | PostgreSQL 18 service |
| `.env.example` | Create | All env vars with local defaults and comments |
| `Makefile` | Create | Developer commands |
| `core/management/commands/pull_prod_db.py` | Create | Prod DB download command |
| `plfog/adapters.py` | Modify | Add `add_message` override for dev-mode login code display |
| `tests/plfog/adapters_spec.py` | Modify | Test the dev-mode login code message |
| `tests/core/pull_prod_db_spec.py` | Create | Tests for the management command |
| `.gitignore` | Modify | Ensure `.env` is gitignored (`.env.example` is tracked) |

## 9. Out of Scope

- Containerizing the Django app itself (runs natively in venv)
- Seed data / fixtures (prod DB pull replaces this need)
- CI/CD changes (this is local dev tooling only)
- `README.md` or `CONTRIBUTING.md` (the Makefile `help` target and `.env.example` comments serve as docs for now)
