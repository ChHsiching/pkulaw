# PKULaw CLI Crawler — Iteration 5: Multi-Value CategoryNew + Crawl Control

## Problem

The crawler's query builder (`src/query.py:98`) only sends the **first** CategoryNew value to the API, silently dropping all others. This makes it impossible to crawl multiple crime types in a single query — requiring N separate runs for N crime types.

Additionally, `config_data.py` only contains 3-level CategoryNew entries (472 total). The live PKULaw API has 4+ levels (1661 total). 8 of the 20 requested crime types are at the 4th level and cannot be resolved.

## Verified API Behavior

Tested live against PKULaw API (2026-05-30):

| Format | Request | Result |
|--------|---------|--------|
| `clusterFilters: {"CategoryNew": "001"}` | Single top-level value | total=13,238,909 |
| `clusterFilters: {"CategoryNew": "001002050,001005002"}` | Comma-separated multi-value | total=4,323,198 |
| `fieldNodes` with pickselect + multiple items | Multi-value as fieldNode | total=4,323,198 |

Both formats produce identical results. **Comma-separated clusterFilters is chosen** for simplicity — one-line change.

## Changes

### 1. Regenerate `src/config_data.py`

Fetch full CategoryNew tree (1661 entries, 4 levels deep) from live API endpoint `/searchingapi/adv/cluster/pfnl`. Update `CLUSTER_DIMENSIONS` with all entries so `resolve_value("CategoryNew", name)` resolves all 20 crime names.

Script: `scripts/refresh_categories.py` — reusable for future updates.

### 2. Fix `src/query.py` line 98

```python
# Before (broken — drops all values after first)
cluster_filters["CategoryNew"] = ids[0]

# After (sends all values as comma-separated string)
cluster_filters["CategoryNew"] = ",".join(ids)
```

### 3. Add `--max-cases` to crawl subcommand

New CLI flag in `src/cli.py` (crawl subcommand only):

```python
crawl.add_argument("--max-cases", type=int, default=0, help="Stop after fetching N total cases (0=unlimited)")
```

Behavior:
- `--max-cases 2000` means "I want 2000 total cases for this query"
- Counts include previously fetched cases from resume — if user already has 500 and sets `--max-cases 2000`, fetches 1500 more
- Only limits the **fetch phase** — search phase always runs fully (fast, API-only)
- When limit reached, fetch phase stops, export proceeds normally with whatever was collected
- `0` (default) means unlimited — fetch everything

Wiring in `src/crawler.py`:
- `run_fetch` accepts `max_cases` parameter
- Before fetching each case, check `len(fetched_gids) >= max_cases`
- If limit reached, print summary and return results

### 4. Ctrl+C interrupt summary

In `pkulaw.py`, replace the current `except KeyboardInterrupt` handler with a summary:

```
=== 采集中断 ===
已搜索：2,716,683 条
已采集：1,500 / 2,716,683 (0.1%)
有效数据：1,203 条 (>500字)
本次新增：1,500 条
输出：output/pkulaw_cases.json

重新运行相同命令即可继续采集。
```

Implementation: catch `KeyboardInterrupt` in `cmd_crawl` (not just `main`). At interrupt time, read stats from `search_results.json` (total), `progress.json` (fetched count), `pkulaw_cases.json` (valid count, size), print summary. Progress is already saved every 500 cases by `_save_all()`.

### 5. Tests

- `build_api_body` with multi-value CategoryNew → cluster filter contains all IDs comma-separated
- `run_fetch` with `max_cases` → stops at limit, returns results
- Ctrl+C summary → mocked data files, verify output format

## What Does NOT Change

- `src/partition.py` — partitions by unconstrained dimensions; CategoryNew is constrained, so it's skipped
- `src/auth.py` — no changes
- `src/exporter.py` — no changes
- Existing resume mechanism — `progress.json` + `search_results.json` already supports it

## 20 Crime Type IDs

After config_data refresh, these resolve via `resolve_value("CategoryNew", name)`:

| Name | ID | Level |
|------|----|-------|
| 危险驾驶罪 | 001002050 | 3 |
| 交通肇事罪 | 001002037 | 3 |
| 盗窃罪 | 001005002 | 3 |
| 诈骗罪 | 001005003 | 3 |
| 合同诈骗罪 | 001003008004 | 4 |
| 故意伤害罪 | 001004003 | 3 |
| 强奸罪 | 001004005 | 3 |
| 非法拘禁罪 | 001004008 | 3 |
| 抢劫罪 | 001005001 | 3 |
| 抢夺罪 | 001005004 | 3 |
| 敲诈勒索罪 | 001005010 | 3 |
| 妨害公务罪 | 001006001001 | 4 |
| 聚众斗殴罪 | 001006001020 | 4 |
| 寻衅滋事罪 | 001006001021 | 4 |
| 掩饰、隐瞒犯罪所得、犯罪所得收益罪 | 001006002018 | 4 |
| 走私、贩卖、运输、制造毒品罪 | 001006007 | 3 |
| 非法持有毒品罪 | 001006007002 | 4 |
| 容留他人吸毒罪 | 001006007011 | 4 |
| 信用卡诈骗罪 | 001003005006 | 4 |
| 故意毁坏财物罪 | 001005011 | 3 |

## Target Crawl Command

```bash
pkulaw crawl --trial-step "一审" --category "危险驾驶罪,交通肇事罪,盗窃罪,诈骗罪,合同诈骗罪,故意伤害罪,强奸罪,非法拘禁罪,抢劫罪,抢夺罪,敲诈勒索罪,妨害公务罪,聚众斗殴罪,寻衅滋事罪,掩饰、隐瞒犯罪所得、犯罪所得收益罪,走私、贩卖、运输、制造毒品罪,非法持有毒品罪,容留他人吸毒罪,信用卡诈骗罪,故意毁坏财物罪"
```

Expected result: ~2,716,683 cases matching 一审 + 20 crime types.
