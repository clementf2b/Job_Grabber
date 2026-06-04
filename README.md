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

# scrape (default: LinkedIn + MichaelPage + CTgoodjobs, 3 pages each)
python main.py "software engineer"

# more pages, specific sources
python main.py "iOS developer" --pages 5 --sources linkedin,ctgoodjobs

# open the frontend
open index.html
```

## Frontend features
- Default view: all software engineering roles (C++, Java, Swift, Go, React, …)
- Keyword search across title + description
- Period filter: 24h / 3 days / 1 week / 1 month
- Source filter pills
- Sort by newest / salary / company
- Expandable job cards with Apply button
- Dark / Light theme toggle (persisted in localStorage)
