"""
database.py
-----------
Everything related to talking to our SQLite database lives here.
We use plain sqlite3 (no ORM) so it's easy to read and understand.

The database file (shortener.db) will be created automatically,
in the same folder as this file, the first time you run the app.
"""

import sqlite3
import os

# Put the database file next to this script, so it always works
# no matter which folder you run "uvicorn main:app" from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shortener.db")


def get_db_connection():
    """
    Opens a new connection to the SQLite database.
    row_factory = sqlite3.Row lets us access columns by name,
    e.g. row["long_url"] instead of row[0].
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints (off by default in SQLite)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Creates all the tables we need, if they don't already exist.
    Safe to call every time the app starts.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # ---- links table -------------------------------------------------
    # Stores every shortened link that has ever been created.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            long_url      TEXT NOT NULL,
            short_code    TEXT NOT NULL UNIQUE,
            is_custom     INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL,
            expires_at    TEXT,
            click_count   INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ---- clicks table --------------------------------------------------
    # Every single click on a short link gets one row here.
    # This is what powers the analytics dashboard.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clicks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            short_code    TEXT NOT NULL,
            clicked_at    TEXT NOT NULL,
            referrer      TEXT,
            user_agent    TEXT,
            device_type   TEXT,
            ip_address    TEXT,
            FOREIGN KEY (short_code) REFERENCES links (short_code)
        )
    """)

    # Helpful indexes so lookups stay fast even with lots of data.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_short_code ON links (short_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clicks_short_code ON clicks (short_code)")

    conn.commit()
    conn.close()
    print(f"Database ready at: {DB_PATH}")
