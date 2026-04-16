# Local Development Runbook

## Prereqs

- Docker
- Python 3.13

## First-Time Setup

```bash
make setup
make db-up
make migrate
```

To populate users for local development:
 
```bash
make localfix
```

That will give you:

- `super@example.com`
- `normal@example.com`

Then load the server:

```bash
make server
```

Open `http://localhost:8000/`.

## Day To Day

Start Postgres:

```bash
make db-up
```

Run Django:

```bash
make server
```

Run tests:

```bash
make test
```

Stop Postgres:

```bash
make db-down
```

## Notes

- `.env` is created from `.env.example` by `make setup`
- local DB default is `postgres://plfog:plfog@localhost:5432/plfog`
- if port `5432` is busy, stop your other local Postgres first
- if Docker is unavailable in WSL, enable Docker Desktop WSL integration

## Optional

To pull production data into your local Postgres, set `PROD_DATABASE_URL` in `.env` and run:

```bash
make db-pull-prod
```
