import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ScheduleConfig, ScrapeRecord
from app.scraper import build_html_diff, run_scrape

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 25


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * PAGE_SIZE

    total_result = await db.execute(select(func.count()).select_from(ScrapeRecord))
    total = total_result.scalar_one()

    records_result = await db.execute(
        select(ScrapeRecord)
        .order_by(ScrapeRecord.created_at.desc())
        .offset(offset)
        .limit(PAGE_SIZE)
    )
    records = records_result.scalars().all()

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # Determine session status for the banner
    cfg_result = await db.execute(select(ScheduleConfig).where(ScheduleConfig.id == 1))
    config = cfg_result.scalar_one_or_none()
    has_cookies = bool(config and config.session_cookies)

    # Check if most recent record was a session expiry
    last_expired = (
        records[0].status in ("session_expired",)
        if records else False
    )

    if not has_cookies:
        session_status = "none"
    elif last_expired:
        session_status = "expired"
    else:
        session_status = "ok"

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "records": records,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "session_status": session_status,
        },
    )


@router.post("/scrape/trigger", response_class=HTMLResponse)
async def trigger_scrape(request: Request):
    """Fire a manual scrape in the background and redirect to dashboard."""
    asyncio.create_task(run_scrape())
    return HTMLResponse(
        '<meta http-equiv="refresh" content="2;url=/">Scrape triggered — redirecting…',
        status_code=200,
    )


@router.get("/scrape/{record_id}/snapshot", response_class=HTMLResponse)
async def view_snapshot(record_id: int, db: AsyncSession = Depends(get_db)):
    """Return the raw HTML snapshot for a scrape record."""
    result = await db.execute(select(ScrapeRecord).where(ScrapeRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return HTMLResponse(content=record.html_snapshot or "<p>No snapshot stored.</p>")


@router.get("/scrape/{record_id}/diff", response_class=HTMLResponse)
async def view_diff(record_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Show a diff between this scrape and the one immediately before it."""
    result = await db.execute(select(ScrapeRecord).where(ScrapeRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    prev_result = await db.execute(
        select(ScrapeRecord)
        .where(ScrapeRecord.id < record_id, ScrapeRecord.status == "success")
        .order_by(ScrapeRecord.id.desc())
        .limit(1)
    )
    prev_record = prev_result.scalar_one_or_none()

    if not prev_record or not prev_record.html_snapshot:
        diff_html = "<p>No previous snapshot available to diff against.</p>"
    elif not record.html_snapshot:
        diff_html = "<p>This record has no HTML snapshot.</p>"
    else:
        diff_html = build_html_diff(prev_record.html_snapshot, record.html_snapshot)

    return templates.TemplateResponse(
        "diff.html",
        {"request": request, "record": record, "diff_html": diff_html},
    )
