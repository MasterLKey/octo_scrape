import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ScheduleConfig

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


async def _get_config(session: AsyncSession) -> ScheduleConfig:
    result = await session.execute(select(ScheduleConfig).where(ScheduleConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        import datetime
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


def _cookie_summary(session_cookies_json: str | None) -> dict:
    """Return summary info about stored cookies."""
    if not session_cookies_json:
        return {"count": 0, "status": "none"}
    try:
        cookies = json.loads(session_cookies_json)
        if not isinstance(cookies, list) or not cookies:
            return {"count": 0, "status": "invalid"}
        return {"count": len(cookies), "status": "ok"}
    except Exception:
        return {"count": 0, "status": "invalid"}


@router.get("/session", response_class=HTMLResponse)
async def session_page(request: Request, db: AsyncSession = Depends(get_db)):
    config = await _get_config(db)
    summary = _cookie_summary(config.session_cookies)
    return templates.TemplateResponse(
        "session.html",
        {
            "request": request,
            "summary": summary,
            "saved": request.query_params.get("saved"),
            "cleared": request.query_params.get("cleared"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/session", response_class=HTMLResponse)
async def save_session(
    request: Request,
    cookies_json: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Validate JSON
    try:
        parsed = json.loads(cookies_json.strip())
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array")
        if not parsed:
            raise ValueError("Cookie list is empty")
    except Exception as exc:
        return RedirectResponse(
            url=f"/session?error={str(exc)[:120]}", status_code=303
        )

    config = await _get_config(db)
    config.session_cookies = json.dumps(parsed)
    await db.commit()

    logger.info("Session cookies saved (%d cookies)", len(parsed))
    return RedirectResponse(url="/session?saved=1", status_code=303)


@router.post("/session/clear", response_class=HTMLResponse)
async def clear_session(db: AsyncSession = Depends(get_db)):
    config = await _get_config(db)
    config.session_cookies = None
    await db.commit()
    logger.info("Session cookies cleared")
    return RedirectResponse(url="/session?cleared=1", status_code=303)
