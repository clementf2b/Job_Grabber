#!/usr/bin/env python3
"""
JobGrab API server — exposes a scrape-url endpoint for the browser UI
and auto-refreshes all job data every 8 hours.

Run with:  uvicorn server:app --reload --port 8000

Environment variables:
  JOBGRAB_KEYWORD   keyword to scrape (default: "software engineer")
  JOBGRAB_PAGES     pages per source  (default: 40)
  JOBGRAB_PERIOD    time filter days  (default: 0 = no filter)
  JOBGRAB_LOCATION  location string   (default: "Hong Kong")
  JOBGRAB_INTERVAL  refresh interval in hours (default: 24)
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from scrapers import SCRAPERS, DOMAIN_SCRAPERS

JOBS_FILE = Path("jobs.json")
SUPPORTED  = ", ".join(sorted({cls.name for cls in DOMAIN_SCRAPERS.values()}))


def _load_jobs() -> list:
    """Read jobs.json from disk, returning [] on any error."""
    try:
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_jobs(jobs: list) -> None:
    """Atomically write a list of job dicts to jobs.json."""
    tmp = JOBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(JOBS_FILE)

# ── Config from environment ──────────────────────────────────────────────
KEYWORD  = os.environ.get("JOBGRAB_KEYWORD",  "software engineer")
LOCATION = os.environ.get("JOBGRAB_LOCATION", "Hong Kong")
PAGES    = int(os.environ.get("JOBGRAB_PAGES",   "40"))
PERIOD   = int(os.environ.get("JOBGRAB_PERIOD",  "0"))
INTERVAL = int(os.environ.get("JOBGRAB_INTERVAL", "24"))  # hours

# ── Shared state ─────────────────────────────────────────────────────────
_refresh_lock:   asyncio.Lock          # initialised in lifespan
_active_task:    asyncio.Task | None = None   # currently running refresh task
_last_refresh:   float | None = None
_next_refresh:   float | None = None
_refresh_status: str = "idle"          # "idle" | "running" | "cancelled" | "ok" | "error"


async def run_all_scrapers() -> list:
    """Run all scrapers concurrently and return merged, deduplicated job list."""
    async def _scrape(name, cls):
        try:
            scraper = cls(keyword=KEYWORD, location=LOCATION,
                          max_pages=PAGES, period_days=PERIOD)
            jobs = await scraper.run()
            print(f"[scheduler] [{name}] {len(jobs)} jobs")
            return jobs
        except asyncio.CancelledError:
            print(f"[scheduler] [{name}] cancelled")
            raise
        except Exception as e:
            print(f"[scheduler] [{name}] ERROR: {e}")
            return []

    results = await asyncio.gather(*[
        _scrape(name, cls) for name, cls in SCRAPERS.items()
    ], return_exceptions=True)
    merged = [
        job
        for batch in results
        if isinstance(batch, list)
        for job in batch
    ]
    return list({(j.url or f"{j.title}|{j.company}"): j for j in merged}.values())


async def refresh_jobs() -> bool:
    """Fetch all jobs and atomically write to jobs.json. Returns success."""
    global _last_refresh, _next_refresh, _refresh_status, _active_task
    if _refresh_lock.locked():
        print("[scheduler] refresh already running, skipping")
        return False

    async with _refresh_lock:
        _refresh_status = "running"
        _active_task = asyncio.current_task()
        print(f"[scheduler] starting refresh (keyword='{KEYWORD}', pages={PAGES})")
        try:
            jobs = await run_all_scrapers()
            _write_jobs([j.to_dict() for j in jobs])
            _last_refresh   = time.time()
            _next_refresh   = _last_refresh + INTERVAL * 3600
            _refresh_status = "ok"
            print(f"[scheduler] done — {len(jobs)} jobs saved.")
            return True
        except asyncio.CancelledError:
            print("[scheduler] refresh cancelled by user")
            _refresh_status = "cancelled"
            return False
        except Exception as e:
            print(f"[scheduler] FAILED: {e}")
            _refresh_status = "error"
            return False
        finally:
            _active_task = None


async def _scheduler_loop():
    """Background task: wait for the interval, then refresh indefinitely."""
    global _next_refresh
    # Seed next_refresh on startup (don't scrape immediately — let existing data load)
    _next_refresh = time.time() + INTERVAL * 3600
    print(f"[scheduler] first auto-refresh in {INTERVAL}h")
    while True:
        now = time.time()
        wait = max(0.0, _next_refresh - now)
        await asyncio.sleep(wait)
        await refresh_jobs()


# ── FastAPI app ───────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _refresh_lock
    _refresh_lock = asyncio.Lock()          # must be created inside the event loop
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="JobGrab API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    url: HttpUrl


@app.get("/status")
async def get_status():
    """Return scheduler state for the UI."""
    return {
        "last_refresh":   _last_refresh,
        "next_refresh":   _next_refresh,
        "refresh_status": _refresh_status,
        "interval_hours": INTERVAL,
        "keyword":        KEYWORD,
    }


@app.post("/refresh")
async def trigger_refresh():
    """Manually trigger a full refresh immediately."""
    if _refresh_lock.locked():
        return {"ok": False, "error": "Refresh already in progress"}
    asyncio.create_task(refresh_jobs())
    return {"ok": True, "message": "Refresh started"}


@app.post("/cancel")
async def cancel_refresh():
    """Cancel a running refresh."""
    global _refresh_status
    if not _refresh_lock.locked() or _active_task is None:
        return {"ok": False, "error": "No refresh in progress"}
    _active_task.cancel()
    _refresh_status = "cancelled"
    return {"ok": True, "message": "Refresh cancelled"}


@app.post("/scrape-url")
async def scrape_url(req: ScrapeRequest):
    url  = str(req.url)
    host = urlparse(url).netloc
    cls  = DOMAIN_SCRAPERS.get(host)
    if not cls:
        return {"ok": False, "error": f"No scraper registered for '{host}'. Supported: {SUPPORTED}."}

    scraper = cls(keyword="", location=LOCATION)
    try:
        job = await scraper.run_single(url)
    except NotImplementedError:
        return {"ok": False, "error": f"{cls.name} does not support single-URL scraping yet."}
    except Exception as e:
        return {"ok": False, "error": f"Scraper error: {e}"}

    if not job:
        return {"ok": False, "error": "Could not extract job data. The page may require login."}

    job_dict = job.to_dict()

    jobs = _load_jobs()

    if any(j.get("url") == job_dict["url"] for j in jobs):
        return {"ok": False, "error": "This job is already in your feed.", "job": job_dict}

    jobs.insert(0, job_dict)
    _write_jobs(jobs)

    return {"ok": True, "job": job_dict}
