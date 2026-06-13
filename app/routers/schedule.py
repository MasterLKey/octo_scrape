import datetime
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ScheduleConfig
from app.scheduler import reconfigure

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


async def _get_config(session: AsyncSession) -> ScheduleConfig:
    result = await session.execute(select(ScheduleConfig).where(ScheduleConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = ScheduleConfig(
            id=1,
            interval_minutes=60,
            window_start=datetime.time(8, 0),
            window_end=datetime.time(22, 0),
            enabled=False,
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)
    return config


@router.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request, db: AsyncSession = Depends(get_db)):
    config = await _get_config(db)
    return templates.TemplateResponse(
        "schedule.html",
        {
            "request": request,
            "config": config,
            "window_start": config.window_start.strftime("%H:%M"),
            "window_end": config.window_end.strftime("%H:%M"),
            "config_url": settings.offer_url,
        },
    )


@router.post("/schedule", response_class=HTMLResponse)
async def update_schedule(
    request: Request,
    interval_minutes: int = Form(...),
    window_start: str = Form(...),
    window_end: str = Form(...),
    enabled: str = Form(default="off"),
    db: AsyncSession = Depends(get_db),
):
    config = await _get_config(db)

    start_time = datetime.datetime.strptime(window_start, "%H:%M").time()
    end_time = datetime.datetime.strptime(window_end, "%H:%M").time()
    is_enabled = enabled == "on"

    config.interval_minutes = max(1, interval_minutes)
    config.window_start = start_time
    config.window_end = end_time
    config.enabled = is_enabled

    await db.commit()
    await db.refresh(config)

    reconfigure(
        interval_minutes=config.interval_minutes,
        window_start=config.window_start,
        window_end=config.window_end,
        enabled=config.enabled,
    )

    logger.info(
        "Schedule updated: every %d min, %s–%s, enabled=%s",
        config.interval_minutes,
        config.window_start,
        config.window_end,
        config.enabled,
    )

    return RedirectResponse(url="/schedule?saved=1", status_code=303)
