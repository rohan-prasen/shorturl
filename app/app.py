import os
import string

import psycopg2
import redis
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

load_dotenv()

web_port = int(os.getenv("WEB_PORT", "5000"))

app = FastAPI()

# Defining all the alphanumeric set of elements
ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase

# Connect to redis for faster lookups
cache = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)


class ShortenRequest(BaseModel):
    url: str


def get_db():
    """Connect to PostgreSQL for permanent storage."""
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "db"),
        database=os.environ.get("POSTGRES_DB", "urlshortener"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )


def base62_encode(num):
    """Convert a database ID into a short alphanumeric string."""
    if num == 0:
        return ALPHABET[0]
    result = []
    while num > 0:
        num, remainder = divmod(num, 62)
        result.append(ALPHABET[remainder])
    return "".join(reversed(result))


def base62_decode(code):
    """Convert a short code back into the original database ID."""
    num = 0
    for char in code:
        num = num * 62 + ALPHABET.index(char)
    return num


def rate_limit(request: Request, max_requests=10, window=60):
    """Limit each client IP to max_requests per window seconds via Redis."""
    # Get the client's IP address
    client_ip = request.client.host if request.client else "unknown"
    # Create a unique Redis key for this IP
    key = f"rate_limit:{client_ip}"
    # Check current request count
    current = cache.get(key)
    if current and int(current) >= max_requests:
        return JSONResponse(
            {"error": "Rate limit exceeded. Try again later."}, status_code=429
        )
    # Increment counter and set expiration atomically
    pipe = cache.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    pipe.execute()
    return None


@app.post("/shorten")
def shorten_url(body: ShortenRequest, request: Request):
    # Enforce the per-IP rate limit before doing any work
    limited = rate_limit(request, max_requests=10, window=60)
    if limited is not None:
        return limited

    # Grab the long URL from the request body
    if not body.url:
        return JSONResponse({"error": "Missing url field"}, status_code=400)

    long_url = body.url

    # Save to PostgreSQL - the database assigns an auto-incrementing ID
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO urls (long_url) VALUES (%s) RETURNING id", (long_url,))
    url_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    # Encode the database ID into a short code
    short_code = base62_encode(url_id)

    # Cache the mapping for fast redirects later
    cache.set(short_code, long_url)

    return JSONResponse(
        {
            "short_url": f"http://localhost:{web_port}/{short_code}",
            "short_code": short_code,
        },
        status_code=201,
    )


@app.get("/health")
def health():
    """Simple endpoint to check whether the server is running."""
    return {"status": "healthy"}


@app.get("/{short_code}")
def redirect_url(short_code: str):
    # Check the fast cache first
    long_url = cache.get(short_code)

    if long_url:
        print("CACHE HIT", flush=True)
        return RedirectResponse(long_url, status_code=302)

    # Cache miss - fall back to the database
    print("CACHE MISS - querying database", flush=True)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT long_url FROM urls WHERE id = %s", (base62_decode(short_code),))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if not result:
        return JSONResponse({"error": "Short URL not found"}, status_code=404)

    # Found it in the database - cache it for next time
    long_url = result[0]
    cache.set(short_code, long_url)

    return RedirectResponse(long_url, status_code=302)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=web_port)
