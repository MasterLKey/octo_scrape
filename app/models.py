import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, Time
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ScrapeRecord(Base):
    __tablename__ = "scrape_records"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False)
    html_snapshot = Column(Text, nullable=True)
    offer_detected = Column(Boolean, default=False, nullable=False)
    offer_accepted = Column(Boolean, default=False, nullable=False)
    page_changed = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="success", nullable=False)  # "success" | "error"
    error_message = Column(Text, nullable=True)


class ScheduleConfig(Base):
    """Single-row settings table. Always use id=1."""

    __tablename__ = "schedule_config"

    id = Column(Integer, primary_key=True, default=1)
    interval_minutes = Column(Integer, default=60, nullable=False)
    window_start = Column(Time, default=datetime.time(8, 0), nullable=False)
    window_end = Column(Time, default=datetime.time(22, 0), nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)
    # JSON array of browser cookies (exported via Cookie Editor extension).
    # When set, Playwright loads these into its context so the scraper runs
    # as an authenticated user — bypassing the OAuth / hCAPTCHA login flow.
    session_cookies = Column(Text, nullable=True)
