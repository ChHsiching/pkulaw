# CLI Refactoring Execution Plan

## Phase 1: Foundation (config + cli + log)

### Task 1.1: Create `src/config.py` — parameter mappings
- Hard-code all Chinese→API id mappings (CategoryNew tree, TrialStep, CaseGrade, CourtGrade, DocumentAttr, etc.)
- Define field types (text/select/checkbox/daterange/pickselect)
- Define field metadata (which fields support scope, combine, etc.)
- Provide lookup functions: `resolve_category("刑事>危害公共安全罪")` → `"001002"`

### Task 1.2: Create `src/log.py` — structured logging
- Python `logging` module with custom formatter
- Format: `[timestamp] LEVEL message`
- Both file and console handlers
- Log file rotation (keep last 10MB)
- Helper functions: `log_progress()`, `log_error()`, `log_save()`

### Task 1.3: Create `src/cli.py` — argument parsing
- argparse with 3 subcommands: estimate, crawl, status
- All CLI flags from spec
- JSON query file parser (`--query file.json`)
- Convert CLI flags + JSON → unified SearchConfig object
- Validate inputs (check field names exist, values valid)

### Task 1.4: Create `pkulaw.py` — CLI entry point
- Import cli, dispatch to subcommand
- Handle Ctrl+C gracefully
- `if __name__ == "__main__"` guard

### Task 1.5: Create `pyproject.toml` — pip install support
- Entry point: `pkulaw = "pkulaw:main"`
- Dependencies from requirements.txt

**Test**: `python pkulaw.py --help`, `python pkulaw.py estimate --help`, `python pkulaw.py status` (shows empty)

---

## Phase 2: Estimate command

### Task 2.1: Implement search query builder
- Take SearchConfig → build API fieldNodes + clusterFilters
- Support all field types: text, select, checkbox, daterange, pickselect
- Handle combine logic (and/or/not)
- Handle scope for FullText field

### Task 2.2: Implement recursive partitioning algorithm
- Get total from search API for given query
- If total ≤ 1000, return directly
- Otherwise, try each partition dimension:
  - LastInstanceDate (year): split into year ranges
  - CaseGrade: split by reference level
  - CategoryNew subcategories: split by crime category
  - CourtGrade: split by court level
  - Any other relevant dimension
- For each partition, recursively estimate
- Choose the strategy that yields highest coverage
- Also try multi-dimension combinations

### Task 2.3: Implement `estimate` subcommand
- Authenticate
- Run partitioning algorithm
- Print detailed report with year distribution, partition tree, estimated coverage, time estimate

**Test**: `python pkulaw.py estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"` — should show ~308K total and estimated coverage

---

## Phase 3: Crawl command (refactor existing)

### Task 3.1: Refactor `src/crawler.py`
- Extract search phase into separate function with SearchConfig input
- Use partitioning algorithm from Phase 2 for search
- Keep existing fetch logic (auto-restart, error handling)
- Integrate with new log module
- Save query metadata to search_results.json

### Task 3.2: Add CSV export to `src/exporter.py`
- New `export_csv()` function
- UTF-8 BOM header
- Dynamic columns (same as Excel)
- Sanitize newlines and quotes in values

### Task 3.3: Implement `crawl` subcommand
- Parse parameters → SearchConfig
- Run search phase (with partitioning)
- Run fetch phase (with auto-restart)
- Export in requested formats
- Split if chunk-size specified

### Task 3.4: Remove old files
- Delete `src/search.py` (replaced by crawler.py's search phase)
- Delete `src/auth.py` (integrated into crawler.py)
- Delete `main.py` (replaced by pkulaw.py)
- Clean up imports

**Test**: Run a small crawl with `--max-pages 1` to verify end-to-end

---

## Phase 4: Status command + polish

### Task 4.1: Implement `status` subcommand
- Read log file (last 20 lines)
- Read progress.json, search_results.json, pkulaw_cases.json
- Check if crawl process is running
- Display structured status report

### Task 4.2: Update README.md
- Document new CLI interface
- Document JSON query file format
- Add examples for common queries

### Task 4.3: Integration testing
- Run estimate with various parameter combinations
- Run small crawl (1-2 partitions)
- Run status during and after crawl
- Verify all output formats
- Verify resume works (Ctrl+C mid-crawl, restart)

### Task 4.4: Git cleanup
- Remove old split_excel.py (replaced by --chunk-size)
- Remove check_status.sh (replaced by pkulaw status)
- Remove old docs/spec.md and docs/plan.md
- Final commit

---

## Estimated effort

| Phase | Tasks | Time |
|-------|-------|------|
| Phase 1: Foundation | 5 tasks | ~2 hours |
| Phase 2: Estimate | 3 tasks | ~2 hours |
| Phase 3: Crawl refactor | 4 tasks | ~3 hours |
| Phase 4: Status + polish | 4 tasks | ~1.5 hours |
| **Total** | **16 tasks** | **~8.5 hours** |

## Dependency graph

```
Phase 1 (config → cli → log → entry → pyproject)
    ↓
Phase 2 (query builder → partitioning → estimate command)
    ↓
Phase 3 (refactor crawler → CSV export → crawl command → cleanup)
    ↓
Phase 4 (status → README → integration test → git cleanup)
```

Each phase depends on the previous one. Tasks within a phase can be partially parallelized.
