"""
main.py
-------
This is the FastAPI backend for our URL Shortener project.

Run it with:
    uvicorn main:app --reload

Then open http://127.0.0.1:8000/docs to see the interactive API docs
that FastAPI generates automatically for you.
"""

import io
import time
from datetime import datetime
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse

import qrcode

from database import get_db_connection, init_db
from utils import (
    encode_base62,
    generate_random_code,
    is_valid_url,
    is_valid_alias,
    detect_device_type,
    calculate_expiry,
    is_expired,
)
from models import ShortenRequest, ShortenResponse, LinkStats, LinkSummary, MessageResponse


# ---------------------------------------------------------------------------
# APP SETUP
# ---------------------------------------------------------------------------
app = FastAPI(
    title="URL Shortener API",
    description="A simple but feature-rich URL shortener built with FastAPI + SQLite.",
    version="1.0.0",
)

# The base URL used to build short links. Change this if you deploy the
# project somewhere other than your own laptop.
BASE_URL = "http://127.0.0.1:8000"

# CORS: allow the frontend (which may be opened as a local file, or served
# from any port like Live Server's 5500) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # beginner-friendly: allow everything
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Runs once when the server starts. Creates the DB tables if needed."""
    init_db()


# ---------------------------------------------------------------------------
# SIMPLE IN-MEMORY RATE LIMITER (advanced feature #1)
# ---------------------------------------------------------------------------
# We don't want one person spamming the /api/shorten endpoint thousands of
# times a minute. This is a very simple "sliding window" rate limiter that
# lives in memory (good enough for a learning project; a real production
# app would use Redis instead).
RATE_LIMIT = 20          # max requests
RATE_WINDOW_SECONDS = 60  # per this many seconds

_request_log: dict[str, deque] = defaultdict(deque)


def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    log = _request_log[client_ip]

    # Drop timestamps older than the window
    while log and now - log[0] > RATE_WINDOW_SECONDS:
        log.popleft()

    if len(log) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Limit is {RATE_LIMIT} per {RATE_WINDOW_SECONDS} seconds. Try again shortly.",
        )

    log.append(now)


# ---------------------------------------------------------------------------
# ROOT / HEALTH CHECK
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"])
def read_root():
    return {
        "message": "URL Shortener API is running.",
        "docs": f"{BASE_URL}/docs",
    }


# ---------------------------------------------------------------------------
# CREATE A SHORT LINK
# ---------------------------------------------------------------------------
@app.post("/api/shorten", response_model=ShortenResponse, tags=["Links"])
def shorten_url(payload: ShortenRequest, request: Request):
    check_rate_limit(request)

    long_url = payload.long_url.strip()
    if not is_valid_url(long_url):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a valid URL. Make sure it starts with http:// or https://",
        )

    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    expires_at = calculate_expiry(payload.expiry_days)

    # ---- Case 1: user wants a custom alias (e.g. "my-sale") --------------
    if payload.custom_alias:
        alias = payload.custom_alias.strip()
        if not is_valid_alias(alias):
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="Custom alias must be 3-20 characters: letters, numbers, - or _ only.",
            )

        existing = cursor.execute(
            "SELECT id FROM links WHERE short_code = ?", (alias,)
        ).fetchone()
        if existing:
            conn.close()
            raise HTTPException(
                status_code=409,
                detail=f"The alias '{alias}' is already taken. Please choose another.",
            )

        short_code = alias
        cursor.execute(
            """INSERT INTO links (long_url, short_code, is_custom, created_at, expires_at)
               VALUES (?, ?, 1, ?, ?)""",
            (long_url, short_code, created_at, expires_at),
        )
        conn.commit()

    # ---- Case 2: auto-generate a short code -------------------------------
    else:
        # Insert first (without knowing the code yet) so we get a real
        # auto-increment ID from SQLite, then base62-encode that ID.
        cursor.execute(
            """INSERT INTO links (long_url, short_code, is_custom, created_at, expires_at)
               VALUES (?, ?, 0, ?, ?)""",
            (long_url, "PENDING", created_at, expires_at),
        )
        new_id = cursor.lastrowid
        short_code = encode_base62(new_id)

        # COLLISION HANDLING (advanced feature #2):
        # Base62-encoding a unique auto-increment ID can never collide with
        # another base62-encoded ID. But it *could* theoretically collide
        # with someone's custom alias that happens to look the same
        # (e.g. alias "1a"). We defend against that edge case here by
        # retrying with a random suffix if needed.
        attempts = 0
        while cursor.execute(
            "SELECT id FROM links WHERE short_code = ? AND id != ?", (short_code, new_id)
        ).fetchone():
            attempts += 1
            short_code = f"{encode_base62(new_id)}{generate_random_code(2)}"
            if attempts > 5:
                # Practically impossible to reach, but fail safely if it ever did.
                conn.rollback()
                conn.close()
                raise HTTPException(status_code=500, detail="Could not generate a unique short code. Please try again.")

        cursor.execute(
            "UPDATE links SET short_code = ? WHERE id = ?", (short_code, new_id)
        )
        conn.commit()

    conn.close()

    return ShortenResponse(
        long_url=long_url,
        short_code=short_code,
        short_url=f"{BASE_URL}/{short_code}",
        qr_code_url=f"{BASE_URL}/api/qr/{short_code}",
        created_at=created_at,
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# REDIRECT (this is the whole point of a URL shortener!)
# ---------------------------------------------------------------------------
@app.get("/{short_code}", tags=["Redirect"])
def redirect_to_long_url(short_code: str, request: Request):
    conn = get_db_connection()
    cursor = conn.cursor()

    link = cursor.execute(
        "SELECT * FROM links WHERE short_code = ?", (short_code,)
    ).fetchone()

    if not link:
        conn.close()
        raise HTTPException(status_code=404, detail="Short link not found.")

    if is_expired(link["expires_at"]):
        conn.close()
        raise HTTPException(status_code=410, detail="This link has expired.")

    # ---- Log the click (this is what powers the analytics dashboard) -----
    user_agent = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "Direct / Unknown")
    client_ip = request.client.host if request.client else "unknown"

    cursor.execute(
        """INSERT INTO clicks (short_code, clicked_at, referrer, user_agent, device_type, ip_address)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            short_code,
            datetime.utcnow().isoformat(),
            referrer,
            user_agent,
            detect_device_type(user_agent),
            client_ip,
        ),
    )
    cursor.execute(
        "UPDATE links SET click_count = click_count + 1 WHERE short_code = ?",
        (short_code,),
    )
    conn.commit()
    conn.close()

    # 302 (temporary redirect) is used deliberately over 301 (permanent):
    # if we used 301, browsers would CACHE the redirect and stop asking our
    # server at all on repeat visits — which means we'd stop being able to
    # count clicks. 302 keeps every click flowing through our server.
    return RedirectResponse(url=link["long_url"], status_code=302)


# ---------------------------------------------------------------------------
# LIST ALL LINKS (for the dashboard table)
# ---------------------------------------------------------------------------
@app.get("/api/links", response_model=list[LinkSummary], tags=["Links"])
def list_links(search: str = Query(None, description="Optional search by URL or code")):
    conn = get_db_connection()
    cursor = conn.cursor()

    if search:
        rows = cursor.execute(
            """SELECT * FROM links
               WHERE long_url LIKE ? OR short_code LIKE ?
               ORDER BY created_at DESC""",
            (f"%{search}%", f"%{search}%"),
        ).fetchall()
    else:
        rows = cursor.execute(
            "SELECT * FROM links ORDER BY created_at DESC"
        ).fetchall()

    conn.close()

    return [
        LinkSummary(
            long_url=row["long_url"],
            short_code=row["short_code"],
            short_url=f"{BASE_URL}/{row['short_code']}",
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            is_expired=is_expired(row["expires_at"]),
            click_count=row["click_count"],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# DETAILED STATS FOR ONE LINK
# ---------------------------------------------------------------------------
@app.get("/api/stats/{short_code}", response_model=LinkStats, tags=["Analytics"])
def get_link_stats(short_code: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    link = cursor.execute(
        "SELECT * FROM links WHERE short_code = ?", (short_code,)
    ).fetchone()
    if not link:
        conn.close()
        raise HTTPException(status_code=404, detail="Short link not found.")

    clicks = cursor.execute(
        """SELECT * FROM clicks WHERE short_code = ?
           ORDER BY clicked_at DESC LIMIT 20""",
        (short_code,),
    ).fetchall()

    device_breakdown = defaultdict(int)
    referrer_breakdown = defaultdict(int)
    for c in clicks:
        device_breakdown[c["device_type"] or "Unknown"] += 1
        referrer_breakdown[c["referrer"] or "Direct / Unknown"] += 1

    conn.close()

    return LinkStats(
        long_url=link["long_url"],
        short_code=link["short_code"],
        short_url=f"{BASE_URL}/{link['short_code']}",
        created_at=link["created_at"],
        expires_at=link["expires_at"],
        is_expired=is_expired(link["expires_at"]),
        click_count=link["click_count"],
        recent_clicks=[
            {"clicked_at": c["clicked_at"], "referrer": c["referrer"], "device_type": c["device_type"]}
            for c in clicks
        ],
        device_breakdown=dict(device_breakdown),
        referrer_breakdown=dict(referrer_breakdown),
    )


# ---------------------------------------------------------------------------
# OVERALL ANALYTICS (for the dashboard chart)
# ---------------------------------------------------------------------------
@app.get("/api/analytics/overview", tags=["Analytics"])
def analytics_overview():
    conn = get_db_connection()
    cursor = conn.cursor()

    total_links = cursor.execute("SELECT COUNT(*) AS c FROM links").fetchone()["c"]
    total_clicks = cursor.execute("SELECT COUNT(*) AS c FROM clicks").fetchone()["c"]

    top_links = cursor.execute(
        """SELECT short_code, long_url, click_count FROM links
           ORDER BY click_count DESC LIMIT 5"""
    ).fetchall()

    # Clicks per day for the last 7 days (for a simple line/bar chart)
    clicks_last_7_days = cursor.execute(
        """SELECT substr(clicked_at, 1, 10) AS day, COUNT(*) AS count
           FROM clicks
           WHERE clicked_at >= datetime('now', '-7 days')
           GROUP BY day
           ORDER BY day ASC"""
    ).fetchall()

    conn.close()

    return {
        "total_links": total_links,
        "total_clicks": total_clicks,
        "top_links": [
            {"short_code": r["short_code"], "long_url": r["long_url"], "click_count": r["click_count"]}
            for r in top_links
        ],
        "clicks_last_7_days": [
            {"day": r["day"], "count": r["count"]} for r in clicks_last_7_days
        ],
    }


# ---------------------------------------------------------------------------
# DELETE A LINK
# ---------------------------------------------------------------------------
@app.delete("/api/links/{short_code}", response_model=MessageResponse, tags=["Links"])
def delete_link(short_code: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    link = cursor.execute(
        "SELECT id FROM links WHERE short_code = ?", (short_code,)
    ).fetchone()
    if not link:
        conn.close()
        raise HTTPException(status_code=404, detail="Short link not found.")

    cursor.execute("DELETE FROM clicks WHERE short_code = ?", (short_code,))
    cursor.execute("DELETE FROM links WHERE short_code = ?", (short_code,))
    conn.commit()
    conn.close()

    return MessageResponse(message=f"Link '{short_code}' deleted successfully.")


# ---------------------------------------------------------------------------
# QR CODE GENERATION (advanced feature #3)
# ---------------------------------------------------------------------------
@app.get("/api/qr/{short_code}", tags=["Extras"])
def get_qr_code(short_code: str):
    conn = get_db_connection()
    link = conn.execute(
        "SELECT short_code FROM links WHERE short_code = ?", (short_code,)
    ).fetchone()
    conn.close()

    if not link:
        raise HTTPException(status_code=404, detail="Short link not found.")

    short_url = f"{BASE_URL}/{short_code}"
    qr_img = qrcode.make(short_url)

    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")
