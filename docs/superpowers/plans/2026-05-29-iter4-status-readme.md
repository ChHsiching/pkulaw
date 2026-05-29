# Issue #5: Status Command + README Update + Final Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the project's deliverability — enhance the status command to spec §3.3, update README to reflect the new CLI, and perform final cleanup.

**Architecture:** The status command reads data files (search_results.json, progress.json, pkulaw_cases.json, crawl.log) from the output directory and formats a structured report. No network calls. The README is a full rewrite replacing the old `main.py`-centric docs with the new `pkulaw` CLI interface.

**Tech Stack:** Python 3.14, pytest, subprocess (process detection)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `pkulaw.py` | Modify | Rewrite `cmd_status` to match spec §3.3 format |
| `tests/test_status.py` | Create | Tests for enhanced cmd_status |
| `README.md` | Modify | Full rewrite for new CLI interface |
| `src/cli.py` | Modify | Add `--output-dir` to status subcommand |

**NOT deleted:** `src/auth.py` — the Issue #5 body incorrectly lists it for deletion. It is actively imported by `src/crawler.py`, `src/partition.py`, and `pkulaw.py`. Deleting it would break the entire project.

**Already deleted in Issue #4:** `main.py`, `split_excel.py`, `check_status.sh`, `src/search.py` — no action needed.

---

## Key Data Format Reference

```python
# search_results.json (new format from Issue #4)
{
  "query": {
    "fieldNodes": [
      {"field": "FullText", "value": "抗诉"},
      {"field": "TrialStep", "values": ["002", "003"]}
    ],
    "started_at": "2026-05-28T08:30:00",
    "completed_at": "2026-05-28T08:45:00"
  },
  "partition_strategy": {"dimensions": [...], "sort_orders": [...], "total_groups": 108},
  "total_unique": 12827,
  "results": [{"gid": "...", "title": "..."}]
}

# search_results.json (old format — backward compatible)
[{"gid": "...", "title": "..."}]

# progress.json
{"fetched_gids": ["gid1", "gid2", ...]}

# pkulaw_cases.json
[{"gid": "...", "title": "...", "full_text": "..."}, ...]
```

---

### Task 1: Enhance `cmd_status` in `pkulaw.py`

**Files:**
- Modify: `pkulaw.py` (rewrite `cmd_status`, lines 177–226)
- Modify: `src/cli.py` (add `--output-dir` to status subcommand)
- Create: `tests/test_status.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_status.py`:

```python
"""Tests for pkulaw.py cmd_status — enhanced status command."""

import json

from pkulaw import cmd_status


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


class TestCmdStatusNoData:
    def test_shows_no_active_task(self, tmp_path, capsys):
        cmd_status(output_dir=tmp_path / "nonexistent")
        output = capsys.readouterr().out
        assert "无活跃任务" in output

    def test_empty_output_dir(self, tmp_path, capsys):
        (tmp_path / "output").mkdir()
        cmd_status(output_dir=tmp_path / "output")
        output = capsys.readouterr().out
        assert "PKULaw 爬取状态" in output


class TestCmdStatusSearchResults:
    def test_shows_query_from_new_format(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(d / "search_results.json", {
            "query": {"fieldNodes": [{"field": "FullText", "value": "抗诉"}]},
            "total_unique": 500,
            "results": [],
        })
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "全文" in output
        assert "抗诉" in output
        assert "500" in output

    def test_handles_old_list_format(self, tmp_path, capsys):
        d = tmp_path / "out"
        results = [{"gid": f"g{i}", "title": f"C{i}"} for i in range(200)]
        _write_json(d / "search_results.json", results)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "200" in output

    def test_shows_select_field_names(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(d / "search_results.json", {
            "query": {"fieldNodes": [
                {"field": "FullText", "value": "抗诉"},
                {"field": "TrialStep", "values": ["002", "003"]},
            ]},
            "total_unique": 100,
            "results": [],
        })
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "审理程序" in output
        assert "二审" in output


class TestCmdStatusProgress:
    def test_shows_fetch_progress(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(d / "search_results.json", {
            "query": {"fieldNodes": []},
            "total_unique": 1000,
            "results": [],
        })
        _write_json(d / "progress.json", {
            "fetched_gids": [f"g{i}" for i in range(500)],
        })
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "500" in output
        assert "1,000" in output
        assert "50.0%" in output


class TestCmdStatusResultsFile:
    def test_shows_valid_data_count(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(d / "search_results.json", {
            "query": {"fieldNodes": []},
            "total_unique": 10,
            "results": [],
        })
        _write_json(d / "progress.json", {"fetched_gids": [f"g{i}" for i in range(5)]})
        cases = [
            {"gid": f"g{i}", "full_text": "x" * 600 if i < 3 else "short"}
            for i in range(5)
        ]
        _write_json(d / "pkulaw_cases.json", cases)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "有效数据" in output
        assert "60.0%" in output

    def test_shows_file_size(self, tmp_path, capsys):
        d = tmp_path / "out"
        _write_json(d / "search_results.json", {
            "query": {"fieldNodes": []},
            "total_unique": 5,
            "results": [],
        })
        _write_json(d / "progress.json", {"fetched_gids": ["g1"]})
        _write_json(d / "pkulaw_cases.json", [{"gid": "g1", "full_text": "t"}])
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "输出文件" in output


class TestCmdStatusLog:
    def test_shows_last_log_lines(self, tmp_path, capsys):
        d = tmp_path / "out"
        d.mkdir(parents=True, exist_ok=True)
        (d / "search_results.json").write_text("[]")
        log_lines = [f"[2026-05-29 01:28:{i:02d}] INFO line {i}" for i in range(25)]
        (d / "crawl.log").write_text("\n".join(log_lines))
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "最近日志" in output
        assert "line 24" in output

    def test_no_log_shows_nothing(self, tmp_path, capsys):
        d = tmp_path / "out"
        d.mkdir(parents=True, exist_ok=True)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "最近日志" not in output


class TestCmdStatusProcess:
    def test_shows_stopped_when_no_process(self, tmp_path, capsys):
        d = tmp_path / "out"
        d.mkdir(parents=True, exist_ok=True)
        cmd_status(output_dir=d)
        output = capsys.readouterr().out
        assert "已停止" in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_status.py -v
```

Expected: FAIL — `TypeError: cmd_status() got an unexpected keyword argument 'output_dir'`

- [ ] **Step 3: Add `--output-dir` to status subcommand**

In `src/cli.py`, replace line 74:

```python
    sub.add_parser("status", help="Show crawl status")
```

with:

```python
    status = sub.add_parser("status", help="Show crawl status")
    status.add_argument("--output-dir", default="output", help="Output directory")
```

- [ ] **Step 4: Rewrite `cmd_status` in `pkulaw.py`**

Replace the existing `cmd_status` function (lines 177–226) with:

```python
def cmd_status(output_dir: Path | None = None) -> None:
    """Show crawl status from existing data files."""
    import json
    import subprocess
    from datetime import datetime

    from src.config import FIELD_DEFINITIONS
    from src.query import reverse_lookup

    if output_dir is None:
        output_dir = Path("output")
    else:
        output_dir = Path(output_dir)

    print(f"\n=== PKULaw 爬取状态 ===")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if not output_dir.exists():
        print("无活跃任务（output/ 目录不存在）\n")
        return

    # --- Search results ---
    search_total = 0
    cache_path = output_dir / "search_results.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            search_total = len(data)
        elif isinstance(data, dict):
            search_total = data.get("total_unique", len(data.get("results", [])))
            query_nodes = data.get("query", {}).get("fieldNodes", [])
            if query_nodes:
                conditions = []
                for node in query_nodes:
                    field = node["field"]
                    label = FIELD_DEFINITIONS.get(field, {}).get("show_text", field)
                    if "value" in node:
                        conditions.append(f"{label}：{node['value']}")
                    elif "values" in node:
                        names = [reverse_lookup(field, v) or v for v in node["values"]]
                        conditions.append(f"{label}：{', '.join(names)}")
                    elif "range" in node:
                        conditions.append(f"{label}：{node['range'][0]} ~ {node['range'][-1]}")
                print("检索条件：")
                for cond in conditions:
                    print(f"  {cond}")
                print()

        if search_total > 0:
            print(f"搜索缓存：{search_total:,} 条（已完成 ✓）")

    # --- Progress ---
    fetched_count = 0
    progress_path = output_dir / "progress.json"
    if progress_path.exists():
        pdata = json.loads(progress_path.read_text(encoding="utf-8"))
        fetched_count = len(pdata.get("fetched_gids", []))

    if search_total > 0 and fetched_count > 0:
        pct = fetched_count / search_total * 100
        remaining = search_total - fetched_count
        print(f"已采集：{fetched_count:,} / {search_total:,} ({pct:.1f}%)")

    # --- Results file ---
    results_path = output_dir / "pkulaw_cases.json"
    if results_path.exists() and results_path.stat().st_size > 0:
        cases = json.loads(results_path.read_text(encoding="utf-8"))
        if cases:
            valid = sum(1 for c in cases if len(c.get("full_text", "")) > 500)
            valid_pct = valid / len(cases) * 100 if cases else 0
            size_mb = results_path.stat().st_size / 1024 / 1024
            if search_total > 0 and fetched_count > 0:
                remaining = search_total - fetched_count
                print(f"有效数据：{valid:,} 条 (>500字, {valid_pct:.1f}%)")
                print(f"剩余：{remaining:,} 条")
            print(f"输出文件：{len(cases):,} 条 ({results_path}, {size_mb:.0f}MB)")

    # --- Process status ---
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        pkulaw_procs = [
            line for line in result.stdout.split("\n")
            if "pkulaw" in line and "grep" not in line
        ]
        if pkulaw_procs:
            parts = pkulaw_procs[0].split()
            pid = parts[1]
            mem_kb = int(parts[5])
            mem_mb = mem_kb / 1024
            print(f"\n进程：运行中 (PID: {pid}, 内存: {mem_mb:.1f}MB)")
        else:
            print("\n进程：已停止")
    except Exception:
        print("\n进程：未知")

    # --- Log ---
    log_path = output_dir / "crawl.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        tail = lines[-20:]
        print(f"\n最近日志（{log_path} 最后 {len(tail)} 行）：")
        for line in tail:
            print(f"  {line}")

    print()
```

Also update `main()` to pass output_dir from args. In `main()`, replace the status branch (line 253):

```python
        if args.command == "status":
            cmd_status()
```

with:

```python
        if args.command == "status":
            cmd_status(output_dir=args.output_dir)
```

Add the `from pathlib import Path` import at the top of pkulaw.py if not already present (it's already imported inside functions, but Path is used in cmd_status's type hint). Add `from pathlib import Path` to the top-level imports of pkulaw.py.

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_status.py -v
```

Expected: All new tests pass.

- [ ] **Step 6: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: All 118+ tests pass.

- [ ] **Step 7: Commit**

```bash
git add pkulaw.py src/cli.py tests/test_status.py
git commit -m "feat: enhance status command with structured report matching spec"
```

---

### Task 2: Update README.md

**Files:**
- Modify: `README.md` (full rewrite)

This is a documentation task. No TDD cycle — verify by reading the rendered output.

- [ ] **Step 1: Rewrite README.md**

Replace the entire content of `README.md` with:

```markdown
# PKULaw CLI Crawler

从 [北大法宝](https://www.pkulaw.com) 司法案例数据库批量爬取案例，用于学术研究。

## 功能

- **递归分区搜索** — 自动选择最优分区维度，突破 API 分页上限
- **参数化检索** — CLI 参数或 JSON 查询文件，支持全文关键词、审理程序、案件类别等 25 个检索字段
- **断点续爬** — 进度实时持久化，中断后重新运行自动跳过已采集案例
- **自动容错** — 浏览器崩溃、认证失败等异常自动恢复
- **多格式导出** — JSON、Excel (.xlsx)、CSV，UTF-8 编码
- **状态监控** — `pkulaw status` 实时查看爬取进度

## 环境要求

- Python 3.10+
- Chromium（默认 `/usr/bin/chromium`）
- 学校内网访问 pkulaw.com（IP 自动认证）

## 安装

```bash
pip install -r requirements.txt
pip install -e .
```

## 使用

### 数据量估算

估算符合检索条件的数据量（不实际爬取）：

```bash
pkulaw estimate --full-text "抗诉" --trial-step "二审,再审" --category "刑事"
```

### 数据爬取

搜索 + 采集 + 导出一步完成：

```bash
# 基本用法
pkulaw crawl --full-text "抗诉" --category "刑事"

# 指定输出格式和每页条数
pkulaw crawl --full-text "抗诉" --format json,csv --max-pages 10

# 后台运行
nohup python -u pkulaw.py crawl --full-text "抗诉" > output/crawl.log 2>&1 &
```

### 查看状态

```bash
pkulaw status
```

输出示例：

```
=== PKULaw 爬取状态 ===
时间：2026-05-29 01:30:00

检索条件：
  全文：抗诉 | 审理程序：二审, 再审 | 案由：刑事

搜索缓存：12,827 条（已完成 ✓）
已采集：10,500 / 12,827 (81.9%)
有效数据：9,472 条 (>500字, 90.2%)
剩余：2,327 条
输出文件：13,069 条 (output/pkulaw_cases.json, 161MB)

进程：运行中 (PID: 657768, 内存: 1.2GB)
```

### JSON 查询文件

复杂查询条件写入 JSON 文件：

```bash
pkulaw crawl --query query.json
```

`query.json` 格式：

```json
{
  "fieldNodes": [
    {"field": "FullText", "value": "抗诉"},
    {"field": "TrialStep", "values": ["二审", "再审"]},
    {"field": "CategoryNew", "values": ["刑事"]}
  ],
  "settings": {
    "delay": 0.5,
    "max_pages": 10,
    "format": ["json", "xlsx"],
    "output_dir": "output"
  }
}
```

CLI 参数与 JSON 文件可组合使用，CLI 参数覆盖 JSON 中的同名字段。

### CLI 参数

| 参数 | 字段 | 说明 |
|------|------|------|
| `--full-text` | FullText | 全文关键词 |
| `--title` | Title | 标题关键词 |
| `--category` | CategoryNew | 案由分类（支持层级，逗号分隔） |
| `--trial-step` | TrialStep | 审理程序（二审/再审/...） |
| `--court-grade` | CourtGrade | 法院级别 |
| `--case-grade` | CaseGrade | 参照级别 |
| `--date-range` | LastInstanceDate | 审结日期范围 (2020-2025) |
| `--format` | — | 输出格式 (json,xlsx,csv)，默认 json,xlsx |
| `--delay` | — | 请求间隔秒数，默认 0.5 |
| `--max-pages` | — | 每个分区最大页数，默认 10 |
| `--output-dir` | — | 输出目录，默认 output |

## 输出

文件保存在 `output/` 目录：

| 文件 | 说明 |
|------|------|
| `pkulaw_cases.json` | 全部案例（JSON） |
| `pkulaw_cases.xlsx` | 全部案例（Excel） |
| `pkulaw_cases.csv` | 全部案例（CSV, UTF-8 BOM） |
| `search_results.json` | 搜索结果缓存 + 查询元数据 |
| `progress.json` | 已采集 gid 列表（断点续爬） |
| `crawl.log` | 爬取日志 |

### 数据结构

每条案例包含：

- **基础字段**：`gid`、`url`、`title`
- **元数据字段**：`案由`、`案号`、`审理法院`、`审结日期`、`审理程序` 等 18 个
- **【】段落字段**：动态提取所有 `【标签名】` 下的内容
- **`full_text`**：案例正文全文

## 项目结构

```
├── pkulaw.py                    # CLI 入口
├── pyproject.toml               # pip install 支持
├── src/
│   ├── cli.py                   # argparse 命令解析
│   ├── config.py                # 参数映射表（中文→API id）
│   ├── config_data.py           # 自动生成的 API 映射数据
│   ├── crawler.py               # 搜索（分区）+ 采集（容错）
│   ├── parser.py                # HTML 解析（动态【】提取）
│   ├── exporter.py              # JSON / Excel / CSV 导出
│   ├── auth.py                  # 浏览器认证 + API 调用
│   ├── query.py                 # SearchConfig → API body
│   ├── partition.py             # 递归分区算法
│   ├── log.py                   # 日志配置
│   └── refetch.py               # 失败案例重爬
├── tests/                       # 测试
└── docs/
    └── spec-v2.md               # 设计规格
```

## 工作原理

### 搜索策略

API 对每次查询限制返回约 1000 条。爬虫使用 **递归分区** 策略：

1. 先查询总量，如果超过阈值则按维度（年份 → 参照级别 → 案由 → ...）递归拆分
2. 对每个分区使用 4 种排序（LastInstanceDate/SortNum × Asc/Desc）
3. 通过 gid 去重确保不重复

### 容错机制

- **浏览器会话崩溃**：新建 page tab，失败则重启浏览器
- **连续 5 次错误**：关闭浏览器，15s 后重建
- **单个案例失败**：跳过并记录到日志
- **进度持久化**：每 500 条自动保存，重启后从断点继续

## 已知限制

- API 分页限制导致无法获取全部数据（单分区 ≤ 4000 条）
- 需要学校内网环境进行认证
- JWT token 有效期约 30 分钟（浏览器 cookie 保持会话）

## 许可

本项目仅供学术研究使用。数据来源于北大法宝数据库，使用时请遵守相关许可协议。
```

- [ ] **Step 2: Verify README renders correctly**

```bash
# Quick sanity check — no broken markdown
grep -c "```" README.md  # Should be even number
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for new CLI interface (estimate/crawl/status)"
```

---

### Task 3: Final cleanup + verify

- [ ] **Step 1: Verify .gitignore is complete**

```bash
cat .gitignore
```

Confirm it includes: `__pycache__/`, `*.pyc`, `output/`, `.venv/`, `.claude/`, `.remember/`, `.env`, `dist/`, `build/`. Current file covers all — no changes needed.

- [ ] **Step 2: Verify no stale imports or broken references**

```bash
.venv/bin/python -c "
from src.crawler import run_search, run_fetch
from src.exporter import export_csv, export_excel, export_json
from src.auth import authenticate, launch_browser, search_api
from src.partition import partition_query
from src.query import build_api_body, reverse_lookup
from pkulaw import cmd_estimate, cmd_crawl, cmd_status, main
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: All 118+ tests pass.

- [ ] **Step 4: Commit if any fixes were needed, otherwise skip**

Only commit if actual changes were made in Steps 1–3.

---

### Task 4: Merge to develop + close Issue #5

- [ ] **Step 1: Verify clean state**

```bash
git status
```

Expected: clean working tree on `feature/iter4-status` branch.

- [ ] **Step 2: Merge to develop with --no-ff**

```bash
git checkout develop
git merge --no-ff feature/iter4-status -m "feat: Issue #5 — status command enhancement + README rewrite + final polish"
```

- [ ] **Step 3: Push to remote**

```bash
git push origin develop
```

- [ ] **Step 4: Close Issue #5**

```bash
gh issue close 5 --comment "Iteration 4 complete. See commit history for details."
```

---

## Self-Review

### 1. Spec Coverage

| Spec Requirement | Task |
|---|---|
| §3.3 检索条件 from search_results.json query fieldNodes | Task 1 (cmd_status) |
| §3.3 搜索缓存 total_unique + completion status | Task 1 |
| §3.3 已采集 / 总量 + 百分比 | Task 1 |
| §3.3 有效数据 (>500字) + 百分比 | Task 1 |
| §3.3 剩余条数 | Task 1 |
| §3.3 输出文件 + 大小 | Task 1 |
| §3.3 进程状态 (PID + memory) | Task 1 |
| §3.3 最近日志 last 20 lines | Task 1 |
| Issue: update README | Task 2 |
| Issue: verify .gitignore | Task 3 |
| Issue: verify imports | Task 3 |

**Gaps noted:**
- `--chunk-size` flag exists in CLI but is not wired to export logic. This is a separate feature, not part of this issue's scope.
- Integration tests (Issue task list: "端到端集成测试") require school intranet access. These are manual verification steps, not automatable in CI.
- `src/auth.py` is listed for deletion in Issue #5 body — this is incorrect. It remains active. Noted in plan header.

### 2. Placeholder Scan

No TBD, TODO, "implement later", or vague steps found.

### 3. Type Consistency

- `cmd_status(output_dir: Path | None = None)` — defined in Task 1, called from `main()` with `args.output_dir` (str), which is converted to Path inside cmd_status. Test passes `tmp_path` (Path). Consistent.
- `reverse_lookup(field, api_id)` — imported from `src.query`, returns `str | None`. Used in cmd_status with `or v` fallback. Consistent.
- `FIELD_DEFINITIONS` — imported from `src.config`, dict with "show_text" key. Consistent.
