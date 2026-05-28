# PKULaw Crawler - Project Context

## Domain Language

| Term | Meaning |
|------|---------|
| GID | Global ID — unique case identifier in PKULaw, used to construct detail page URLs |
| pfnl | Library code for "司法案例" (judicial cases) — used in all API paths |
| FullText | API field name for full-text search |
| TrialStep | API field name for trial procedure (审理程序) |
| CategoryNew | API field name for case category (案由分类) — "001" = 刑事 |
| clusterFilters | API parameter for category-level filtering (applied post-search) |
| fieldNodes | API parameter array for search criteria (full-text, procedure, etc.) |
| Case Detail Page | Server-rendered HTML at `/pfnl/{gid}.html`, ~400KB, contains all case data |
| Bearer Token | JWT from Keycloak OAuth2, stored in localStorage, ~30min TTL |
| IP Auth | School network auto-login — no username/password needed |

## Key Architecture Decisions

- **ADR-1**: Hybrid mode (Playwright for auth only, requests for data). Reason: 10x faster than full browser automation for 500 pages.
- **ADR-2**: Plain text output (strip HTML). Reason: data is for model training, HTML markup adds noise.
- **ADR-3**: Single Excel sheet with all fields. Reason: training data pipeline, not for human browsing.
- **ADR-4**: Progress file for resume. Reason: 500 pages × 1s = ~10min, interruptions likely.
- **ADR-5**: Token refresh via Playwright re-launch. Reason: simpler than implementing OAuth2 refresh flow, overhead is acceptable (~10s every 30min).

## Data Flow

```
Playwright (auth) → token
  ↓
requests (search API, paginated) → 500 GIDs
  ↓
requests (detail pages, one per GID) → 500 HTML blobs
  ↓
BeautifulSoup (parse) → 500 structured dicts
  ↓
openpyxl (Excel) + json.dump (JSON) → output files
```
