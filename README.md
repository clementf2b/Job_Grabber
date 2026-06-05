# JobGrab

Hong Kong multi-board job scraper with a terminal-style frontend.

## Sources
| Board | Status |
|---|---|
| LinkedIn | ✅ Working |
| MichaelPage HK | ✅ Working |
| CTgoodjobs | ✅ Working |
| JobsDB | ❌ Cloudflare blocked |
| Indeed | ❌ Cloudflare blocked |
| Glassdoor | ❌ Cloudflare blocked |

## Usage

```bash
# create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# install dependencies
pip install -r requirements.txt
python -m playwright install chromium
npm install
```

### Scrape jobs
```bash
# default: LinkedIn + MichaelPage + CTgoodjobs, up to 40 pages, no time filter
python main.py "software engineer"

# specific sources / page limit
python main.py "iOS developer" --pages 5 --sources linkedin,ctgoodjobs

# restrict to recent posts (e.g. last 7 days) — note: excludes reposted jobs
python main.py "software engineer" --period 7
```

### Run the frontend

Open two terminals:

```bash
# Terminal 1 — API server (enables paste-URL feature in the browser)
uvicorn server:app --reload --port 8000

# Terminal 2 — Vite dev server
npm run dev
```

The browser UI includes a **Paste URL** field — paste any LinkedIn job URL (e.g. from an email alert) and click Fetch to add it directly to the feed without re-scraping.

## Frontend features
- Default view: all software-related roles (software developer, engineer, programmer, mobile, DevOps, …)
- Keyword search across title + description
- Period filter: 24h / 3 days / 1 week / 1 month
- Source filter pills
- Sort by newest / salary / company
- Expandable job cards with Apply button
- Dark / Light theme toggle (persisted in localStorage)
