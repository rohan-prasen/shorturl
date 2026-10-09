# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A minimal Flask URL shortener. Short codes are the base62 encoding of a Postgres auto-increment `id`; Redis is a cache-aside layer in front of Postgres for redirect lookups. `AGENTS.md` is a symlink to this file.

## Commands

Dependencies are managed with **uv** (`uv.lock` is the source of truth; `requirements.txt` is a generated export consumed only by the Docker image).

```bash
uv sync                                  # install deps into .venv
uv run python app/app.py                 # run the app (needs Postgres + Redis + env, see below)
docker compose up --build                # run the full stack (web + postgres + redis)
uv run ruff check --fix                  # lint
uv run ruff format                       # format
uv run pre-commit run --all-files        # run all pre-commit hooks
uv run pytest                            # run tests (pytest is wired up; no tests exist yet)
```

The `shorturl` console script (`pyproject.toml` -> `app.__init__:main`) is only a stub that prints a greeting — it is **not** the web app entry point. The app runs via `app/app.py` (locally and as the Docker `CMD`).

## Architecture

Single module, `app/app.py`, holds the whole web app:

- **Write path** (`POST /shorten`): insert the long URL into Postgres, take the returned serial `id`, `base62_encode` it into a short code, prime the Redis cache, return the short URL.
- **Read path** (`GET /<short_code>`): check Redis first; on miss, `base62_decode` the code back to the `id`, look it up in Postgres, backfill the cache, then 302-redirect. Cache hit/miss is logged to stdout.
- `GET /health` returns a static healthy JSON.
- Postgres is permanent storage; the `urls` table is created by `app/init.sql`, mounted into the Postgres container's `docker-entrypoint-initdb.d` so it only runs on a fresh data volume.

## Configuration

All config comes from environment variables (loaded via `python-dotenv` from `.env`). `.env.example` lists the keys; `.env` is gitignored. `compose.yml` passes these through to the containers.

- `WEB_PORT` defaults to `5000` (`int(os.getenv("WEB_PORT", "5000"))`), so the app starts even if it is unset.
- Postgres and Redis connection vars (`POSTGRES_HOST`/`DB`/`USER`/`PASSWORD`, `REDIS_HOST`, `REDIS_PORT`) have in-code defaults matching the compose service names (`db`, `redis`, port `6379`).

## Gotchas

- `init.sql` runs only when the Postgres volume is empty — after a schema change, recreate the volume (`docker compose down -v`) for it to re-run.
