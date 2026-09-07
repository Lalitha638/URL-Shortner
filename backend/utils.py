"""
utils.py
--------
Small helper functions used by main.py:

1. Base62 encoding      -> turns a database row ID into a short code like "b7Nq"
2. Random code generator -> used as a fallback / for guessing collisions away
3. URL validation        -> makes sure users don't submit garbage
4. Device detection      -> very simple parsing of the User-Agent header
5. Expiry check          -> is a link past its expiry date?
"""

import re
import random
import string
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 1. BASE62 ENCODING
# ---------------------------------------------------------------------------
# Why base62 instead of just using the row ID directly (1, 2, 3, ...)?
#   - "1" as a short code is not very "short URL" looking, and it leaks
#     exactly how many links exist in your system (a minor info leak).
#   - Base62 uses 0-9, a-z, A-Z (62 symbols) instead of just 0-9 (10 symbols),
#     so the same number becomes a much shorter, URL-safe string.
#   - Example: database ID 125000  ->  base62 "wLc"
#
# This is a DETERMINISTIC encoding: the same ID always produces the same
# code, and we can decode it back if we ever need to.

BASE62_ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase
BASE = len(BASE62_ALPHABET)  # 62


def encode_base62(number: int) -> str:
    """Convert a positive integer (like a DB row id) into a base62 string."""
    if number == 0:
        return BASE62_ALPHABET[0]

    digits = []
    while number > 0:
        number, remainder = divmod(number, BASE)
        digits.append(BASE62_ALPHABET[remainder])

    # We built the digits backwards (least significant first), so reverse them.
    return "".join(reversed(digits))


def decode_base62(code: str) -> int:
    """Convert a base62 string back into the original integer (not used by
    the API directly, but handy for debugging / future features)."""
    number = 0
    for char in code:
        number = number * BASE + BASE62_ALPHABET.index(char)
    return number


# ---------------------------------------------------------------------------
# 2. RANDOM CODE (used for the very unlikely case of a collision, and for
#    fallback situations)
# ---------------------------------------------------------------------------
def generate_random_code(length: int = 6) -> str:
    return "".join(random.choices(BASE62_ALPHABET, k=length))


# ---------------------------------------------------------------------------
# 3. URL VALIDATION
# ---------------------------------------------------------------------------
URL_REGEX = re.compile(
    r"^(https?://)"                       # must start with http:// or https://
    r"([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}"      # domain, e.g. example.com
    r"(:\d+)?"                             # optional port
    r"(/[^\s]*)?$"                         # optional path/query
)


def is_valid_url(url: str) -> bool:
    if not url or len(url) > 2048:
        return False
    return bool(URL_REGEX.match(url.strip()))


# ---------------------------------------------------------------------------
# 4. CUSTOM ALIAS VALIDATION
# ---------------------------------------------------------------------------
ALIAS_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def is_valid_alias(alias: str) -> bool:
    return bool(ALIAS_REGEX.match(alias))


# ---------------------------------------------------------------------------
# 5. VERY SIMPLE DEVICE DETECTION FROM USER-AGENT
# ---------------------------------------------------------------------------
def detect_device_type(user_agent: str) -> str:
    if not user_agent:
        return "Unknown"
    ua = user_agent.lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "Mobile"
    if "tablet" in ua or "ipad" in ua:
        return "Tablet"
    return "Desktop"


# ---------------------------------------------------------------------------
# 6. EXPIRY HELPERS
# ---------------------------------------------------------------------------
def calculate_expiry(days: int | None):
    if not days or days <= 0:
        return None
    return (datetime.utcnow() + timedelta(days=days)).isoformat()


def is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    return datetime.utcnow() > datetime.fromisoformat(expires_at)
