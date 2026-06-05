#!/usr/bin/env python3
"""
JobGrab API server.

Run with:  uvicorn server:app --reload --port 8000

Environment variables:
  JOBGRAB_KEYWORDS  comma-separated keywords  (default: see below)
  JOBGRAB_PAGES     pages per source          (default: 40)
  JOBGRAB_PERIOD    time filter days          (default: 0 = no filter)
  JOBGRAB_LOCATION  location string           (default: "Hong Kong")
  JOBGRAB_INTERVAL  refresh interval hours    (default: 24)
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from scrapers import SCRAPERS, DOMAIN_SCRAPERS
from db import init_db, upsert_jobs, load_jobs, count_jobs

SUPPORTED = ", ".join(sorted({cls.name for cls in DOMAIN_SCRAPERS.values()}))

# ── Config ────────────────────────────────────────────────────────────────
_default_keywords = (
    "software engineer,software developer,software,"
    "quantitative developer,quant developer,quantitative analyst,"
    "c++,c++ developer,developer,engineer,builder"
)
KEYWORDS = [k.strip() for k in os.environ.get("JOBGRAB_KEYWORDS", _default_keywords).split(",") if k.strip()]
LOCATION = os.environ.get("JOBGRAB_LOCATION", "Hong Kong")
PAGES    = int(os.environ.get("JOBGRAB_PAGES",   "40"))
PERIOD   = int(os.environ.get("JOBGRAB_PERIOD",  "0"))
INTERVAL = int(os.environ.get("JOBGRAB_INTERVAL", "24"))

# ── Shared state ──────────────────────────────────────────────────────────
_refresh_lock:   asyncio.Lock          # initialised in lifespan
_active_task:    asyncio.Task | None = None
_last_refresh:   float | None = None
_next_refresh:   float | None = None
_refresh_status: str = "idle"          # "idle"|"running"|"cancelled"|"ok"|"error"

# SSE: set of per-client queues
_listeners: set[asyncio.Queue] = set()


async def _broadcast(event: dict) -> None:
    """Push a progress event to every connected SSE client."""
    for q in list(_listeners):
        await q.put(event)


# ── Scraping ──────────────────────────────────────────────────────────────

async def run_all_scrapers() -> list:
    """Run all scrapers × all keywords concurrently; emit SSE progress events."""
    total = len(KEYWORDS) * len(SCRAPERS)
    completed = 0

    board_names = [cls.name for cls in SCRAPERS.values()]
    await _broadcast({"type": "start", "total": total, "boards": board_names})

    async def _scrape(keyword, cls):
        nonlocal completed
        board = cls.name   # use display name (e.g. "LinkedIn") not dict key
        await _broadcast({"type": "task_start", "board": board, "keyword": keyword})
        try:
            scraper = cls(keyword=keyword, location=LOCATION,
                          max_pages=PAGES, period_days=PERIOD)
            jobs = await scraper.run()
            completed += 1
            await _broadcast({
                "type": "task_done", "board": board, "keyword": keyword,
                "count": len(jobs), "completed": completed, "total": total,
            })
            print(f"[scheduler] [{board}] '{keyword}' → {len(jobs)} jobs")
            return jobs
        except asyncio.CancelledError:
            await _broadcast({"type": "cancelled"})
            print(f"[scheduler] [{board}] '{keyword}' cancelled")
            raise
        except Exception as e:
            completed += 1
            await _broadcast({
                "type": "task_error", "board": board, "keyword": keyword,
                "error": str(e), "completed": completed, "total": total,
            })
            print(f"[scheduler] [{board}] '{keyword}' ERROR: {e}")
            return []

    tasks = [
        _scrape(kw, cls)
        for kw in KEYWORDS
        for cls in SCRAPERS.values()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = [
        job
        for batch in results
        if isinstance(batch, list)
        for job in batch
    ]
    deduped = list({(j.url or f"{j.title}|{j.company}"): j for j in merged}.values())
    return deduped


async def refresh_jobs() -> bool:
    global _last_refresh, _next_refresh, _refresh_status, _active_task
    if _refresh_lock.locked():
        print("[scheduler] refresh already running, skipping")
        return False

    async with _refresh_lock:
        _refresh_status = "running"
        _active_task = asyncio.current_task()
        print(f"[scheduler] starting refresh ({len(KEYWORDS)} keywords × {len(SCRAPERS)} boards)")
        try:
            jobs = await run_all_scrapers()

            await _broadcast({"type": "db_write", "count": len(jobs)})
            upsert_jobs(jobs)
            total = count_jobs()

            _last_refresh   = time.time()
            _next_refresh   = _last_refresh + INTERVAL * 3600
            _refresh_status = "ok"
            print(f"[scheduler] done — {len(jobs)} jobs upserted. total={total}")

            await _broadcast({"type": "done", "new": len(jobs), "total": total})
            return True
        except asyncio.CancelledError:
            print("[scheduler] refresh cancelled by user")
            _refresh_status = "cancelled"
            await _broadcast({"type": "cancelled"})
            return False
        except Exception as e:
            print(f"[scheduler] FAILED: {e}")
            _refresh_status = "error"
            await _broadcast({"type": "error", "error": str(e)})
            return False
        finally:
            _active_task = None


async def _scheduler_loop():
    global _next_refresh
    _next_refresh = time.time() + INTERVAL * 3600
    print(f"[scheduler] first auto-refresh in {INTERVAL}h")
    while True:
        now = time.time()
        wait = max(0.0, _next_refresh - now)
        await asyncio.sleep(wait)
        await refresh_jobs()


# ── App ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _refresh_lock
    init_db()
    _refresh_lock = asyncio.Lock()
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
    return {
        "last_refresh":   _last_refresh,
        "next_refresh":   _next_refresh,
        "refresh_status": _refresh_status,
        "interval_hours": INTERVAL,
        "keywords":       KEYWORDS,
    }


@app.get("/progress")
async def progress_stream():
    """SSE endpoint — streams scrape progress events to the browser."""
    q: asyncio.Queue = asyncio.Queue()
    _listeners.add(q)

    async def event_gen():
        # Send "ready" immediately so the client knows the connection is live
        # and can safely POST /refresh without missing the "start" event.
        yield f"data: {json.dumps({'type': 'ready'})}\n\n"
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "cancelled", "error"):
                    break
        finally:
            _listeners.discard(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/refresh")
async def trigger_refresh():
    if _refresh_lock.locked():
        return {"ok": False, "error": "Refresh already in progress"}
    asyncio.create_task(refresh_jobs())
    return {"ok": True, "message": "Refresh started"}


@app.post("/cancel")
async def cancel_refresh():
    global _refresh_status
    if not _refresh_lock.locked() or _active_task is None:
        return {"ok": False, "error": "No refresh in progress"}
    _active_task.cancel()
    _refresh_status = "cancelled"
    return {"ok": True, "message": "Refresh cancelled"}


@app.get("/jobs")
async def get_jobs(source: str | None = None):
    return load_jobs(source=source)


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

    existing = load_jobs()
    if any(j.get("url") == str(req.url) for j in existing):
        return {"ok": False, "error": "This job is already in your feed.", "job": job.to_dict()}

    upsert_jobs([job])
    return {"ok": True, "job": job.to_dict()}
