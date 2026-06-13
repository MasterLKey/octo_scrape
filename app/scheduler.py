"""
APScheduler-based job scheduler.

The scheduler runs a single recurring job (run_scrape) at a configurable
interval. Before each execution it checks whether the current local time
falls within the configured daily time window; if not, the scrape is skipped.

The schedule is hot-reloadable: call reconfigure() with updated settings
to reschedule the job without restarting the container.
"""

import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.scraper import run_scrape

logger = logging.getLogger(__name__)

JOB_ID = "octopus_scrape"

# Module-level scheduler instance (initialised in main.py startup)
scheduler = AsyncIOScheduler()


async def _scrape_job(window_start: datetime.time, window_end: datetime.time) -> None:
    """APScheduler calls this on each tick; enforces the daily time window."""
    now = datetime.datetime.now().time().replace(second=0, microsecond=0)

    if window_start <= window_end:
        in_window = window_start <= now <= window_end
    else:
        # Window spans midnight e.g. 22:00 – 06:00
        in_window = now >= window_start or now <= window_end

    if not in_window:
        logger.debug("Outside time window (%s – %s), skipping scrape", window_start, window_end)
        return

    logger.info("Time window check passed — starting scrape")
    await run_scrape()


def reconfigure(
    interval_minutes: int,
    window_start: datetime.time,
    window_end: datetime.time,
    enabled: bool,
) -> None:
    """
    Add or replace the scrape job with the supplied settings.
    If enabled=False, the job is removed entirely.
    Safe to call at any time while the scheduler is running.
    """
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)

    if not enabled:
        logger.info("Scheduler disabled — no job scheduled")
        return

    trigger = IntervalTrigger(minutes=interval_minutes)
    scheduler.add_job(
        _scrape_job,
        trigger=trigger,
        id=JOB_ID,
        kwargs={"window_start": window_start, "window_end": window_end},
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "Scheduler configured: every %d min, window %s–%s",
        interval_minutes,
        window_start,
        window_end,
    )
