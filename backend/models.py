"""
models.py
---------
Pydantic models describe the "shape" of data going in and out of our API.
FastAPI uses these to automatically validate incoming requests and to
generate the interactive docs at /docs.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class ShortenRequest(BaseModel):
    """What the frontend sends us when creating a new short link."""
    long_url: str = Field(..., description="The original, full-length URL")
    custom_alias: Optional[str] = Field(
        None, description="Optional custom short code chosen by the user"
    )
    expiry_days: Optional[int] = Field(
        None, ge=1, le=3650, description="Optional: link expires after N days"
    )


class ShortenResponse(BaseModel):
    """What we send back after successfully creating a short link."""
    long_url: str
    short_code: str
    short_url: str
    qr_code_url: str
    created_at: str
    expires_at: Optional[str] = None


class ClickInfo(BaseModel):
    clicked_at: str
    referrer: Optional[str] = None
    device_type: Optional[str] = None


class LinkStats(BaseModel):
    """Full analytics for a single short link."""
    long_url: str
    short_code: str
    short_url: str
    created_at: str
    expires_at: Optional[str] = None
    is_expired: bool
    click_count: int
    recent_clicks: List[ClickInfo] = []
    device_breakdown: dict = {}
    referrer_breakdown: dict = {}


class LinkSummary(BaseModel):
    """One row in the 'all links' dashboard table."""
    long_url: str
    short_code: str
    short_url: str
    created_at: str
    expires_at: Optional[str] = None
    is_expired: bool
    click_count: int


class MessageResponse(BaseModel):
    message: str
