# PKULaw Crawler - Execution Plan

## Phase 0: Project Setup
- [ ] Create directory structure (`src/`, `output/`)
- [ ] Create `src/__init__.py`
- [ ] Create `main.py` entry point
- [ ] Install dependencies from `requirements.txt`
- [ ] Verify Playwright + Chromium work (`playwright install chromium`)

## Phase 1: Authentication Module (`src/auth.py`)
- [ ] 1.1 Write `get_auth_session()` function:
  - Launch headless Chromium via Playwright (`/usr/bin/chromium`)
  - Navigate to `https://www.pkulaw.com/advanced/case`
  - Wait for SPA to fully load (wait for `#app` content > 100KB)
  - Extract `localStorage.access_token` (Bearer token)
  - Extract all cookies via `context.cookies()`
  - Close browser
  - Return `(token: str, cookies: dict)`
- [ ] 1.2 Write `refresh_token(session)` function:
  - Detect 401 response → call `get_auth_session()` again
  - Return new session
- [ ] 1.3 Test: run auth module standalone, verify token extraction

## Phase 2: Search Module (`src/search.py`)
- [ ] 2.1 Write `build_search_body()` function:
  - Construct the full `fieldNodes` + `clusterFilters` JSON body
  - Accept `page_index` and `page_size` parameters
- [ ] 2.2 Write `search_cases(token, cookies, total_limit=500)` function:
  - Create `requests.Session` with Bearer token and cookies
  - Loop: `pageIndex` from 0, `pageSize` 20
  - On each iteration: POST to `/searchingapi/adv/list/pfnl`
  - Collect `gid` + `title` + `summaries` from each result
  - Stop when collected >= 500 or no more results
  - Rate limit: `time.sleep(1)` between requests
  - Retry on network errors (max 3, exponential backoff)
  - On 401: call `refresh_token()` and retry
- [ ] 2.3 Test: run search standalone, verify 500 GIDs collected

## Phase 3: Parser Module (`src/parser.py`)
- [ ] 3.1 Write `fetch_case_detail(session, gid)` function:
  - GET `https://www.pkulaw.com/pfnl/{gid}.html?keyword=抗诉`
  - Retry logic (max 3)
  - On 401: refresh token
  - Return raw HTML string
- [ ] 3.2 Write `parse_metadata(html)` function:
  - Parse with BeautifulSoup (lxml parser)
  - Find all `.box` elements, extract label-value pairs
  - Return dict: {案由: ..., 案号: ..., ...}
- [ ] 3.3 Write `parse_content_sections(html)` function:
  - Find content sections by their heading text (关键词, 裁判要点, etc.)
  - Extract text under each heading
  - Strip all HTML tags, clean whitespace
  - Return dict: {关键词: ..., 裁判要点: ..., ...}
- [ ] 3.4 Write `parse_full_text(html)` function:
  - Find the main content container (`.fulltext-wrap` or equivalent)
  - Strip all HTML tags
  - Clean up whitespace (collapse multiple newlines/spaces)
  - Return plain text string
- [ ] 3.5 Write `parse_case(html, gid)` function:
  - Calls 3.2, 3.3, 3.4
  - Assembles into unified dict with gid, url, title, metadata, content, full_text
  - Missing fields default to ""
- [ ] 3.6 Test: fetch and parse the example case, verify all fields extracted

## Phase 4: Exporter Module (`src/exporter.py`)
- [ ] 4.1 Write `export_json(cases, path)` function:
  - Write list of case dicts to JSON file
  - Ensure_ascii=False for Chinese characters
  - Indent=2 for readability
- [ ] 4.2 Write `export_excel(cases, path)` function:
  - Flatten each case dict (metadata/* → top-level, content/* → top-level)
  - Define column order: gid, url, title, 法宝引证码, 时效性, 案由, 案号, ...全文
  - Write to .xlsx via openpyxl
  - Auto-adjust column widths for short columns, leave long columns as-is
- [ ] 4.3 Test: export sample data, verify JSON and Excel are correct

## Phase 5: Main Orchestrator (`src/crawler.py`)
- [ ] 5.1 Write `ProgressTracker` class:
  - Load/save `output/progress.json` (set of fetched GIDs)
  - `is_fetched(gid) → bool`
  - `mark_fetched(gid)`
  - `get_count() → int`
- [ ] 5.2 Write `run()` function:
  1. Call auth module → get token + cookies
  2. Call search module → get 500 GIDs
  3. For each GID:
     - Skip if already in progress tracker
     - Fetch + parse case detail
     - Add to results list
     - Mark as fetched in progress tracker
     - Print progress: `[X/500] title...`
     - Every 50 cases: save intermediate JSON + Excel
     - `time.sleep(1)` between fetches
  4. Final export: save complete JSON + Excel
- [ ] 5.3 Write `main.py` entry point:
  - Import and call `crawler.run()`
  - Handle KeyboardInterrupt gracefully (save progress)

## Phase 6: Testing & Verification
- [ ] 6.1 Run full crawl (first 5 cases only as smoke test)
- [ ] 6.2 Verify JSON output structure matches spec
- [ ] 6.3 Verify Excel output opens correctly and all fields present
- [ ] 6.4 Verify resume works (stop after 3 cases, restart, confirm it picks up from 4th)
- [ ] 6.5 Run full 500-case crawl

## Dependencies
```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
```
Each phase depends on the previous. Phase 3 (parser) is the most complex — requires careful HTML analysis for different case types.

## Estimated Time
| Phase | Description | Est. Time |
|-------|-------------|-----------|
| 0 | Setup | 5 min |
| 1 | Auth module | 15 min |
| 2 | Search module | 15 min |
| 3 | Parser module | 30 min |
| 4 | Exporter module | 15 min |
| 5 | Orchestrator | 15 min |
| 6 | Testing | 20 min |
| — | Full crawl (500 × 1s) | ~10 min |
| **Total** | | ~2 hours |
