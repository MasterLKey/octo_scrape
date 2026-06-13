import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ScheduleConfig
from app.routers import schedule as schedule_router
from app.routers import scrapes as scrapes_router
from app.routers import session as session_router
from app.scheduler import reconfigure, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Starting Octo Scrape…")
    scheduler.start()

    # Load schedule config from DB and apply to scheduler
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ScheduleConfig).where(ScheduleConfig.id == 1))
        config = result.scalar_one_or_none()

    if config:
        reconfigure(
            interval_minutes=config.interval_minutes,
            window_start=config.window_start,
            window_end=config.window_end,
            enabled=config.enabled,
        )
    else:
        logger.warning("No schedule config found in DB — scheduler idle until configured via GUI")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down scheduler…")
    scheduler.shutdown(wait=False)


app = FastAPI(title="Octo Scrape", lifespan=lifespan)

app.include_router(scrapes_router.router)
app.include_router(schedule_router.router)
app.include_router(session_router.router)
