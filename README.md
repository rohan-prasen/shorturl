# ShortURL

A small URL shortener built with Flask. You send it a long URL, it stores the URL in PostgreSQL, and it hands back a short code. When someone visits the short code, the service looks the code up and redirects them to the original URL. Redis sits in front of the database as a cache so repeat visits do not hit PostgreSQL every time.

This README walks a first-time visitor through the whole development setup: what the pieces are, how to configure them, and how to get the app running either with Docker or directly on your machine.

## How it works

The short code is not random. Every URL you save becomes a row in PostgreSQL, and the database gives that row an auto-incrementing integer `id`. The service encodes that integer into base62 (digits, lowercase letters, uppercase letters) to produce a compact code, and decodes the code back into the integer when someone visits it. So `id` 1 becomes `1`, `id` 100000 becomes a few characters, and the codes stay short even as the table grows.

There are three endpoints:

- `POST /shorten` takes a JSON body with a `url` field, saves it, and returns the short code and full short URL.
- `GET /<short_code>` looks up the code and sends a 302 redirect to the original URL. It checks Redis first and only falls back to PostgreSQL on a cache miss, then writes the result back into Redis.
- `GET /health` returns a small JSON object so you can check the server is up.

Three processes run together: the Flask web app, a PostgreSQL database for permanent storage, and a Redis instance for caching. The Docker Compose setup starts all three for you.

## Prerequisites

You can run this project two ways. Pick the one that matches what you already have installed.

For the Docker path (recommended, nothing to install locally except Docker):

- Docker and Docker Compose.

For the local path (run the Flask app on your machine, with the databases either local or in Docker):

- Python 3.12 or newer. The pinned version lives in `.python-version`.
- [uv](https://docs.astral.sh/uv/) for dependency management.
- A reachable PostgreSQL instance and a reachable Redis instance.

## Project layout

```
app/
  app.py          The whole Flask application: routes, base62 encode/decode, DB and cache clients
  init.sql        Creates the `urls` table; PostgreSQL runs it on first startup
  __init__.py     Package metadata and a stub console-script entry point (not the web server)
docker/
  dockerfile      Builds the web service image
compose.yml       Defines the web, db, and redis services and wires them together
pyproject.toml    Project metadata, dependencies, and dev tool config
uv.lock           The locked dependency set; the source of truth for installs
requirements.txt  A generated export of the dependencies, used only by the Docker build
.env.example      The list of environment variables you need to set
.pre-commit-config.yaml  Git hooks for whitespace, YAML checks, and ruff
```

## Configuration

All configuration comes from environment variables. The app reads them from a `.env` file at startup using python-dotenv. The file `.env.example` lists every key with empty values. Copy it and fill it in:

```bash
cp .env.example .env
```

The variables are:

- `WEB_PORT` is the port the Flask app listens on. It is required and has no default. If it is missing the app fails to start, so always set it.
- `REDIS_HOST` is the Redis hostname.
- `REDIS_PORT` is the Redis port.
- `POSTGRES_HOST` is the PostgreSQL hostname.
- `POSTGRES_DB` is the database name.
- `POSTGRES_USER` is the database user.
- `POSTGRES_PASSWORD` is the database password.

When you run with Docker Compose, the hostnames are the service names, `db` and `redis`, because the containers talk to each other over the internal Docker network. A working `.env` for the Docker path looks like this:

```
WEB_PORT=8000
REDIS_HOST=redis
REDIS_PORT=6379
POSTGRES_HOST=db
POSTGRES_DB=urlshortener
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

When you run the Flask app directly on your machine, point the hosts at wherever your databases actually live, usually `localhost`.

## Running with Docker (recommended)

This is the fastest way to get a working stack because it starts the web app, PostgreSQL, and Redis together.

1. Create your `.env` file as shown above.
2. Build the images and start everything:

   ```bash
   docker compose up --build
   ```

3. Compose waits for PostgreSQL and Redis to report healthy before it starts the web service. On first startup, PostgreSQL runs `app/init.sql`, which creates the `urls` table. The database files live in a named volume called `postgres_data`, so your data survives restarts.
4. The app is now reachable on the port you set in `WEB_PORT`, for example `http://localhost:8000`.

To stop the stack, press Ctrl+C, or run `docker compose down`. To stop it and also delete the database volume (so `init.sql` runs again from scratch next time), run `docker compose down -v`.

## Running locally without Docker

Use this path when you want to run and debug the Flask app on your machine. You still need PostgreSQL and Redis running somewhere the app can reach. A common setup is to run just the databases in Docker and the app on your host.

1. Install the dependencies. This creates a `.venv` and installs everything from the lock file:

   ```bash
   uv sync
   ```

2. Make sure PostgreSQL and Redis are running and that your `.env` points at them. If you have not created the `urls` table yet, load the schema into your database:

   ```bash
   psql "$DATABASE_URL" -f app/init.sql
   ```

   Replace the connection string with whatever your database needs, or run the SQL through your usual client.

3. Start the app:

   ```bash
   uv run python app/app.py
   ```

   The app binds to `0.0.0.0` on your `WEB_PORT`, so it is reachable at `http://localhost:<WEB_PORT>`.

Note: the `shorturl` command defined in `pyproject.toml` is only a placeholder that prints a greeting. It does not start the web server. Always run the app through `app/app.py`.

## Trying the API

Create a short URL. Send a POST with a JSON body:

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/very/long/path"}'
```

You get back the short code and the full short URL:

```json
{
  "short_url": "http://localhost:8000/1",
  "short_code": "1"
}
```

Visit the short code to be redirected. The `-L` flag tells curl to follow the redirect to the original URL:

```bash
curl -L http://localhost:8000/1
```

Check that the server is up:

```bash
curl http://localhost:8000/health
```

When you watch the web service logs during a redirect, you will see `CACHE HIT` or `CACHE MISS - querying database`, which tells you whether Redis or PostgreSQL served the lookup.

## Development workflow

Dependencies are managed with uv, and `uv.lock` is the source of truth. After changing dependencies in `pyproject.toml`, run `uv sync` to update your environment and the lock file.

Formatting and linting use ruff:

```bash
uv run ruff check --fix    # lint and auto-fix
uv run ruff format         # format
```

The repository ships a pre-commit configuration that runs ruff along with whitespace and YAML checks on every commit. Install the git hook once, then run it against all files to confirm your setup:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

pytest is installed as a dev dependency and ready to use, though there are no tests in the repository yet:

```bash
uv run pytest
```

## Known quirks and troubleshooting

A few things in the current code are worth knowing before they confuse you:

- The Redis port is read from an environment variable named `REDIST_PORT`, which has a typo. Because `REDIS_PORT` is never read for the port, the client falls back to the default `6379`. If you need a non-default Redis port, be aware of this when debugging.
- `compose.yml` points at `docker/Dockerfile` with a capital D, but the file on disk is `docker/dockerfile` in lowercase. This works on case-insensitive filesystems such as default macOS, but a case-sensitive Linux host will fail to find the file during the build.
- The timestamp column in `app/init.sql` is named `create_at`, missing the `d` from `created_at`.
- `init.sql` only runs when the PostgreSQL data volume is empty. If you change the schema, you need to recreate the volume with `docker compose down -v` for the new SQL to take effect.

If the web service starts and immediately exits, the most common cause is a missing `WEB_PORT`, since the app reads it with no fallback. Check your `.env` first.
