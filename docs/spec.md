# PKULaw Crawler - Spec Design Document

## 1. Project Overview

A Python web crawler for extracting judicial case data from PKULaw (北大法宝) database, targeting protest-related (抗诉) criminal cases at the second instance (二审) and retrial (再审) levels. Output is training data — 500 cases saved as both JSON and Excel.

## 2. Site Architecture Analysis

### 2.1 Search Page
- URL: `https://www.pkulaw.com/advanced/case`
- Type: Vue.js SPA (client-rendered)
- API Base: `/searchingapi/`

### 2.2 Authentication
- Mechanism: Keycloak OAuth2 with IP-based auto-login (school network)
- Token: JWT Bearer token stored in `localStorage.access_token`
- Token TTL: ~30 minutes, auto-refreshed by the SPA

### 2.3 Search API
- Endpoint: `POST /searchingapi/adv/list/pfnl`
- Content-Type: `application/json`
- Required Headers: `Authorization: Bearer <token>`

#### Request Body Structure
```json
{
  "orderbyExpression": "SortNum Desc,LastInstanceDate Desc",
  "pageIndex": 0,
  "pageSize": 20,
  "fieldNodes": [
    {
      "type": "text",
      "order": 1,
      "combineAs": 2,
      "fieldName": "FullText",
      "showText": "全文",
      "subCombineAs": 2,
      "fieldItems": [{
        "values": "抗诉",
        "valuesCombineAs": 2,
        "extra": {"values": "", "combineAs": 2},
        "matchType": 1,
        "matchSpan": 1,
        "matchSpanGap": 0,
        "fieldScope": {"fieldName": "", "showText": ""},
        "order": 0,
        "filterNodes": []
      }],
      "matchTypeEnabled": false,
      "matchSpanEnabled": true,
      "matchSpans": null
    },
    {
      "type": "select",
      "order": 6,
      "combineAs": 2,
      "fieldName": "TrialStep",
      "showText": "审理程序",
      "fieldItems": [{
        "items": [
          {"text": "二审", "path": "002", "name": "二审", "value": "002"},
          {"text": "再审", "path": "003", "name": "再审", "value": "003"}
        ],
        "combineAs": 2,
        "order": 0,
        "filterNodes": []
      }]
    }
  ],
  "clusterFilters": {"CategoryNew": "001"},
  "groupBy": {}
}
```

#### Response Structure
```json
{
  "total": 308828,
  "data": [
    {
      "gid": "...",
      "title": "...",
      "summaries": [{"type": "text", "text": "..."}],
      "caseGrade": [{"name": "...", "value": "..."}],
      "sections": [...]
    }
  ]
}
```

### 2.4 Case Detail Page
- URL Pattern: `https://www.pkulaw.com/pfnl/{gid}.html?keyword=抗诉`
- Type: Server-rendered HTML (~400KB per page)
- No authentication required for detail page access

#### Data Fields
**Metadata Fields (box structure):**
- 案由、案号、文书类型、公开类型、审理法院、审结日期
- 案件类型、审理程序、案例发文、案例编号、发布日期
- 来源、刑罚、指控罪名、判定罪名

**Content Sections:**
- 关键词、裁判要点、基本案情、裁判结果、裁判理由、相关法条

**System Fields:**
- 【法宝引证码】、【时效性】

**Full Text:**
- Complete judicial document body, saved as plain text (HTML tags stripped)

### 2.5 Field Reference (API Field Names)
| fieldName    | showText  | type       |
|-------------|-----------|------------|
| FullText    | 全文       | text       |
| TrialStep   | 审理程序    | select     |
| CategoryNew | 案由       | pickselect |
| Title       | 标题       | text       |
| CaseFlag    | 案号       | text       |
| LastInstanceCourt | 审理法院 | select   |
| LastInstanceDate  | 审结日期 | daterange |
| CaseClass   | 案件类型    | select     |
| DocumentAttr | 文书类型   | checkbox   |
| CaseGrade   | 参照级别    | select     |

### 2.6 Category Values
| ID   | Name    |
|------|---------|
| 001  | 刑事    |
| 002  | 民事    |
| 005  | 行政    |
| 006  | 执行    |
| 007  | 国家赔偿 |

### 2.7 TrialStep Values
| ID   | Name    |
|------|---------|
| 002  | 二审    |
| 003  | 再审    |

## 3. Technical Design

### 3.1 Architecture: Hybrid Mode (Approach B)

```
Phase 1: Auth
  Playwright → open search page → extract Bearer token from localStorage

Phase 2: Search
  Python requests → POST /searchingapi/adv/list/pfnl with Bearer token
  → paginate through 500 results (25 pages × 20 per page)

Phase 3: Extract Details
  Python requests → GET /pfnl/{gid}.html for each case
  → BeautifulSoup → parse metadata + content sections + full text

Phase 4: Output
  → JSON file (structured data)
  → Excel file (.xlsx, single sheet with all fields including full text)
```

### 3.2 Module Structure
```
law-web-crawler/
├── src/
│   ├── __init__.py
│   ├── auth.py          # Playwright auth, token extraction
│   ├── search.py        # Search API client, pagination
│   ├── parser.py        # HTML parsing, data extraction
│   ├── exporter.py      # JSON + Excel export
│   └── crawler.py       # Main orchestrator
├── output/              # Generated data files
├── docs/
│   └── spec.md          # This file
├── requirements.txt
└── main.py              # Entry point
```

### 3.3 Authentication Module (`auth.py`)
- Launch headless Chromium via Playwright
- Navigate to `https://www.pkulaw.com/advanced/case`
- Wait for SPA to load and auto-authenticate via IP
- Extract `access_token` from `localStorage`
- Extract cookies for detail page access
- Return token + cookies dict
- Auto-refresh: if token expires (401 response), re-authenticate

### 3.4 Search Module (`search.py`)
- Build search request body with user criteria
- Pagination: `pageIndex` from 0 to 24 (25 pages × 20 = 500 cases)
- Rate limit: 1 second between requests
- Error handling: retry on network errors (max 3 retries)
- Return list of `gid` values + basic metadata

### 3.5 Parser Module (`parser.py`)
- Parse case detail HTML with BeautifulSoup + lxml
- Extract metadata from `.box` elements (key-value pairs)
- Extract content sections (关键词, 裁判要点, 基本案情, etc.)
- Extract full document text as plain text (strip all HTML tags)
- Missing fields default to empty string `""`
- Return structured dict per case

### 3.6 Exporter Module (`exporter.py`)
- JSON export: `output/pkulaw_cases.json` — array of case objects
- Excel export: `output/pkulaw_cases.xlsx` — single sheet, all fields in columns
  - Metadata columns: 案由, 案号, 审理法院, 审结日期, etc.
  - Content columns: 关键词, 裁判要点, 基本案情, 裁判结果, 裁判理由, 相关法条
  - Full text column: 完整全文
  - System columns: 法宝引证码, 时效性, 标题, URL

### 3.7 Main Orchestrator (`crawler.py`)
- Coordinate all modules
- Progress reporting (X/500 cases processed)
- Resume: JSON file `output/progress.json` tracks fetched GIDs
- Save intermediate results every 50 cases

## 4. Search Criteria (Fixed)
- FullText: `抗诉`
- TrialStep: `二审` OR `再审`
- CategoryNew: `刑事` (cluster filter)
- Sort: `SortNum Desc,LastInstanceDate Desc`
- Limit: 500 cases (top results)

## 5. Output Schema

### 5.1 JSON Structure (`output/pkulaw_cases.json`)
```json
[
  {
    "gid": "08df102e7c10f2066a543669b10e941d8dc16d235c90ef87bdfb",
    "url": "https://www.pkulaw.com/pfnl/....html",
    "title": "指导性案例248号：金某等组织卖淫案",
    "metadata": {
      "法宝引证码": "CLI.1.304262",
      "时效性": "尚未施行",
      "案由": "",
      "案号": "",
      "文书类型": "",
      "公开类型": "",
      "审理法院": "",
      "审结日期": "",
      "案件类型": "",
      "审理程序": "",
      "刑罚": "",
      "指控罪名": "",
      "判定罪名": ""
    },
    "content": {
      "关键词": "",
      "裁判要点": "",
      "基本案情": "",
      "裁判结果": "",
      "裁判理由": "",
      "相关法条": ""
    },
    "full_text": "plain text content with all HTML tags removed..."
  }
]
```

### 5.2 Excel Structure (`output/pkulaw_cases.xlsx`)
Flattened: one row per case, columns are gid, url, title, all metadata keys, all content keys, full_text.

## 6. Non-Functional Requirements
- Rate limiting: 1 second between API requests
- Resume: `output/progress.json` tracks fetched GIDs, skip on restart
- Progress: `[12/500] 案例标题...`
- Error recovery: retry failed requests up to 3 times with exponential backoff
- Token refresh: auto-detect 401 → re-launch Playwright → new token
- Plain text: all extracted text has HTML tags stripped
- Missing fields: default to empty string `""`
