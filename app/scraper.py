"""
Playwright-based scraper for the Octopus Energy Café Nero free drink offer.

Authentication strategy (updated June 2026):
  Octopus Energy migrated their dashboard to a proper OAuth 2.0 / PKCE flow
  protected by hCAPTCHA.  The previous localStorage JWT injection no longer
  works because the dashboard no longer reads from localStorage.

  The new approach uses *browser session cookies* exported from a real logged-in
  browser session (Chrome / Firefox + Cookie Editor extension).  Once you paste
  your cookies into the Session page in the web UI they are stored in the database
  and loaded into every Playwright browser context, giving the headless browser a
  fully authenticated session without needing to log in.

  Session cookies typically last several weeks.  When they expire the scraper
  records "session_expired" status and the dashboard shows a banner prompting you
  to refresh your cookies.

Scrape flow:
  1. Load session cookies from the database into the Playwright context.
  2. Navigate directly to the offer URL.
  3. Detect whether the page shows offer content or the login redirect.
  4. If offer detected: check for an enabled claim button and click it.
  5. Persist the rendered HTML snapshot and outcome in PostgreSQL.

JWT is still obtained for injecting into api.octopus.energy GraphQL requests
(some authenticated data may be served via request-level auth even with cookies).
"""

import datetime
import difflib
import json
import logging
import re
from typing import Optional

import httpx
from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import ScheduleConfig, ScrapeRecord

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.octopus.energy/v1/graphql/"

# Substrings matched case-insensitively against the rendered page text.
OFFER_KEYWORDS = [
    "caffè nero",
    "cafe nero",
    "free drink",
    "hot or cold drink",
    "free coffee",
    "claim by",
    "get free drink",
    "get your free drink",
    "accept offer",
    "get your free",
    "get offer",
    "claim reward",
    "more codes tomorrow",  # offer live but daily codes exhausted
    "claim",
    "redeem",
]

# CSS selector for enabled (claimable) offer card buttons.
CLAIMABLE_BUTTON_SELECTOR = (
    "[data-testid='offer-card']:not([disabled]) "
    "button[data-part='button-root']:not([disabled])"
)

# Text patterns that indicate we landed on the login page (not the offer page).
LOGIN_PAGE_SIGNALS = ["sign in", "email address", "password", "sign in to octopus"]


# ── Authentication ────────────────────────────────────────────────────────────

async def _obtain_kraken_token(client: httpx.AsyncClient) -> Optional[str]:
    """Exchange the Octopus Energy API key for a short-lived Kraken JWT."""
    api_key = settings.octopus_api_key
    if not api_key or api_key.startswith("sk_live_your"):
        logger.error(
            "OCTOPUS_API_KEY is not set. "
            "Generate one at: octopus.energy → Account → Personal details → API access"
        )
        return None

    mutation = """
    mutation obtainKrakenToken($input: ObtainJSONWebTokenInput!) {
      obtainKrakenToken(input: $input) {
        token
      }
    }
    """
    try:
        resp = await client.post(
            GRAPHQL_URL,
            json={"query": mutation, "variables": {"input": {"APIKey": api_key}}},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        logger.error("GraphQL request failed: %s", exc)
        return None

    raw = resp.text
    logger.info("GraphQL HTTP %s (%d chars): %s", resp.status_code, len(raw), raw[:200])

    if not raw.strip():
        logger.error("GraphQL returned empty response (status %s)", resp.status_code)
        return None

    try:
        data = resp.json()
    except Exception as exc:
        logger.error("GraphQL response is not valid JSON: %s — body: %s", exc, raw[:200])
        return None

    errors = data.get("errors")
    if errors:
        logger.error("GraphQL errors: %s", errors)
        return None

    token = (data.get("data") or {}).get("obtainKrakenToken", {}).get("token")
    if not token:
        logger.error("No token in GraphQL response: %s", data)
        return None

    logger.info("Kraken JWT obtained successfully")
    return token


# ── Session cookie helpers ────────────────────────────────────────────────────

async def _load_session_cookies() -> Optional[list]:
    """Read the stored session cookies JSON from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ScheduleConfig).where(ScheduleConfig.id == 1)
        )
        config = result.scalar_one_or_none()
        if config and config.session_cookies:
            try:
                cookies = json.loads(config.session_cookies)
                if isinstance(cookies, list) and cookies:
                    logger.info("Loaded %d session cookies from DB", len(cookies))
                    return cookies
            except Exception as exc:
                logger.error("Failed to parse session cookies JSON: %s", exc)
    return None


def _normalise_cookies(raw_cookies: list) -> list:
    """
    Convert cookies exported by Cookie Editor (or similar) into the format
    Playwright's add_cookies() expects.

    Cookie Editor exports use 'expirationDate' (float epoch); Playwright uses
    'expires' (int epoch).  We also ensure domain and path are present.
    """
    normalised = []
    for c in raw_cookies:
        if not isinstance(c, dict):
            continue
        name = c.get("name") or c.get("Name")
        value = c.get("value") or c.get("Value") or ""
        if not name:
            continue

        cookie: dict = {
            "name": name,
            "value": value,
            "domain": c.get("domain") or c.get("Domain") or ".octopus.energy",
            "path": c.get("path") or c.get("Path") or "/",
        }

        # Expiry: accept either 'expires' (int) or 'expirationDate' (float)
        exp = c.get("expires") or c.get("expirationDate")
        if exp is not None:
            try:
                cookie["expires"] = int(float(exp))
            except (TypeError, ValueError):
                pass

        if c.get("httpOnly") is not None:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if c.get("secure") is not None:
            cookie["secure"] = bool(c["secure"])
        if c.get("sameSite"):
            # Playwright accepts "Strict" | "Lax" | "None"
            ss = str(c["sameSite"]).capitalize()
            if ss in ("Strict", "Lax", "None"):
                cookie["sameSite"] = ss

        normalised.append(cookie)
    return normalised


# ── Playwright scrape ─────────────────────────────────────────────────────────

async def _playwright_scrape(
    jwt_token: Optional[str],
    session_cookies: Optional[list],
) -> tuple[str, bool, bool, bool]:
    """
    Render the offer page in a headless browser.

    If session_cookies are provided they are loaded into the browser context so
    the page renders as a logged-in user.  Otherwise we fall back to the JWT
    localStorage injection (which may not work if Octopus has updated their auth).

    Returns:
        (rendered_html, offer_detected, offer_accepted, session_expired)
        session_expired is True when the page shows the login form despite
        cookies being provided (cookies have expired).
    """
    target_url = settings.offer_url
    logger.info("Target URL: %s", target_url)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--enable-unsafe-swiftshader",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            viewport={"width": 1280, "height": 720},
        )

        # Patch out the webdriver flag
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )

        # ── Session cookie injection ───────────────────────────────────────────
        if session_cookies:
            try:
                normalised = _normalise_cookies(session_cookies)
                await context.add_cookies(normalised)
                logger.info("Playwright: %d session cookies loaded into context", len(normalised))
            except Exception as exc:
                logger.error("Failed to load session cookies into Playwright: %s", exc)

        page = await context.new_page()

        # Inject JWT into api.octopus.energy requests (supplements cookie auth)
        if jwt_token:
            async def inject_auth(route):
                await route.continue_(
                    headers={**route.request.headers, "Authorization": f"JWT {jwt_token}"}
                )
            await page.route("**api.octopus.energy**", inject_auth)

        page.on("console", lambda msg: (
            logger.warning("Browser [%s]: %s", msg.type, msg.text)
            if msg.type in ("error", "warning")
            else None
        ))

        try:
            if session_cookies:
                # With cookies: go directly to the offer page (no two-step needed)
                logger.info("Playwright: navigating directly to offer page (cookie auth)")
                await page.goto(target_url, wait_until="load", timeout=90_000)
            else:
                # Fallback: try localStorage JWT injection (may not work on new dashboard)
                logger.info("Playwright: no cookies — trying localStorage JWT injection")
                await page.goto("https://octopus.energy/", wait_until="domcontentloaded", timeout=30_000)
                if jwt_token:
                    await page.evaluate(f"localStorage.setItem('token', {repr(jwt_token)})")
                    logger.info("Playwright: JWT injected into localStorage as 'token'")
                logger.info("Playwright: navigating to %s", target_url)
                await page.goto(target_url, wait_until="load", timeout=90_000)

            # Wait for React to finish rendering
            try:
                await page.wait_for_selector(
                    "main, [role='main'], h1, h2, article, section",
                    timeout=20_000,
                )
            except Exception:
                logger.warning("Main-content selector timed out; proceeding anyway")

            await page.wait_for_timeout(8_000)

            html = await page.content()
            page_text = (await page.evaluate("document.body.innerText")).lower()
            final_url = page.url

            logger.info(
                "Playwright: page rendered — %d chars HTML, %d chars visible text, URL: %s",
                len(html), len(page_text), final_url[:80],
            )
            logger.info("Page text preview: %s", page_text[:800])

            # ── Detect if we landed on the login page ─────────────────────────
            on_login_page = (
                "auth.octopus.energy" in final_url
                or "login" in final_url
                or (
                    len(page_text) < 300
                    and all(sig in page_text for sig in ["sign in", "password"])
                )
            )

            session_expired = False
            if on_login_page:
                if session_cookies:
                    logger.warning(
                        "Landed on login page despite having session cookies — "
                        "cookies have expired. Please refresh them via the Session page."
                    )
                    session_expired = True
                else:
                    logger.warning(
                        "Landed on login page. No session cookies configured. "
                        "Visit the Session page in the web UI to add your browser cookies."
                    )
                return html, False, False, session_expired

            # ── Offer detection ────────────────────────────────────────────────
            detected_keyword = next(
                (kw for kw in OFFER_KEYWORDS if kw in page_text), None
            )
            offer_detected = detected_keyword is not None
            offer_accepted = False

            if offer_detected:
                logger.info("Offer detected (keyword: '%s')", detected_keyword)

                claimable = page.locator(CLAIMABLE_BUTTON_SELECTOR)
                claimable_count = await claimable.count()
                logger.info("Enabled claim buttons found: %d", claimable_count)

                if claimable_count > 0:
                    btn_text = (await claimable.first.inner_text()).strip()
                    logger.info("Clicking claim button: '%s'", btn_text)
                    await claimable.first.click()
                    await page.wait_for_timeout(6_000)
                    html = await page.content()
                    offer_accepted = True
                    logger.info("Offer claimed! Post-click page captured.")
                else:
                    logger.info(
                        "Offer is live but all claim buttons are disabled "
                        "(codes exhausted — 'More codes tomorrow')"
                    )
            else:
                logger.info(
                    "No offer content found in rendered page text "
                    "(offer may not be active or the page didn't render correctly)"
                )

            return html, offer_detected, offer_accepted, False

        finally:
            await browser.close()


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_previous_html(session: AsyncSession) -> Optional[str]:
    result = await session.execute(
        select(ScrapeRecord.html_snapshot)
        .where(ScrapeRecord.status == "success")
        .order_by(ScrapeRecord.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_scrape() -> ScrapeRecord:
    """Execute one full scrape cycle and persist the result."""
    logger.info("Scrape started at %s", datetime.datetime.utcnow().isoformat())

    record = ScrapeRecord(created_at=datetime.datetime.utcnow(), status="error")

    async with AsyncSessionLocal() as session:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                jwt_token = await _obtain_kraken_token(client)

            if not jwt_token:
                logger.warning(
                    "Could not obtain Kraken JWT (API key invalid or not set). "
                    "Proceeding with session cookies only."
                )

            # Load session cookies from DB
            session_cookies = await _load_session_cookies()

            html, offer_detected, offer_accepted, session_expired = (
                await _playwright_scrape(jwt_token, session_cookies)
            )

            record.html_snapshot = html
            record.offer_detected = offer_detected
            record.offer_accepted = offer_accepted

            if session_expired:
                record.status = "session_expired"
                record.error_message = (
                    "Session cookies have expired. "
                    "Please refresh them on the Session page."
                )
            elif not session_cookies and not offer_detected:
                record.status = "no_session"
                record.error_message = (
                    "No session cookies configured. "
                    "Add your browser cookies on the Session page to enable scraping."
                )
            else:
                prev_html = await _get_previous_html(session)
                record.page_changed = (
                    prev_html is not None and prev_html.strip() != html.strip()
                )
                record.status = "success"

            logger.info(
                "Scrape complete — detected=%s accepted=%s changed=%s status=%s",
                offer_detected, offer_accepted, record.page_changed, record.status,
            )

        except Exception as exc:
            logger.exception("Unexpected scrape error: %s", exc)
            record.error_message = str(exc)

        session.add(record)
        await session.commit()
        await session.refresh(record)

    return record


# ── HTML diff utility ─────────────────────────────────────────────────────────

def build_html_diff(old_html: str, new_html: str) -> str:
    """Return an HTML-formatted context diff of two page snapshots."""
    differ = difflib.HtmlDiff(wrapcolumn=120)
    return differ.make_table(
        old_html.splitlines(),
        new_html.splitlines(),
        fromdesc="Previous snapshot",
        todesc="Current snapshot",
        context=True,
        numlines=5,
    )
