# Issue #8: Refresh config_data — Complete 4-Level CategoryNew Tree

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regenerate `src/config_data.py` with the full 4-level CategoryNew tree (1,661 entries) so all 20 crime names resolve via `resolve_value("CategoryNew", name)`.

**Architecture:** Create `scripts/refresh_categories.py` that authenticates via Playwright, fetches the CategoryNew tree from the live PKULaw API endpoint `/searchingapi/adv/cluster/pfnl`, recursively flattens it into name→ID pairs, and regenerates `config_data.py`. The script imports the current config_data to preserve FIELD_DEFINITIONS and non-CategoryNew dimensions, then writes the updated file.

**Tech Stack:** Python, Playwright, PKULaw REST API

---

### Task 1: Create Feature Branch

- [ ] **Step 1: Create branch from develop**

```bash
git checkout develop
git pull origin develop
git checkout -b feature/iter5-config-refresh
```

Verify: `git branch --show-current` → `feature/iter5-config-refresh`

---

### Task 2: TDD — Write Tests for Tree Flattening Helpers (RED)

**Files:**
- Create: `tests/test_refresh_categories.py`

- [ ] **Step 1: Write tests for `flatten_tree` and `build_category_tree`**

Create `tests/test_refresh_categories.py`:

```python
"""Tests for scripts/refresh_categories.py helper functions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from refresh_categories import build_category_tree, flatten_tree

MOCK_TREE = [
    {
        "name": "刑事",
        "id": "001",
        "children": [
            {
                "name": "危害公共安全罪",
                "id": "001002",
                "children": [
                    {"name": "放火罪", "id": "001002001", "children": []},
                    {"name": "交通肇事罪", "id": "001002037", "children": []},
                ],
            },
            {
                "name": "破坏社会主义市场经济秩序罪",
                "id": "001003",
                "children": [
                    {
                        "name": "扰乱市场秩序罪",
                        "id": "001003008",
                        "children": [
                            {"name": "合同诈骗罪", "id": "001003008004", "children": []},
                        ],
                    },
                    {
                        "name": "金融诈骗罪",
                        "id": "001003005",
                        "children": [
                            {"name": "信用卡诈骗罪", "id": "001003005006", "children": []},
                        ],
                    },
                ],
            },
        ],
    }
]


class TestFlattenTree:
    def test_top_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["刑事"] == "001"

    def test_second_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["危害公共安全罪"] == "001002"

    def test_third_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["放火罪"] == "001002001"
        assert result["交通肇事罪"] == "001002037"

    def test_fourth_level(self):
        result = flatten_tree(MOCK_TREE)
        assert result["合同诈骗罪"] == "001003008004"
        assert result["信用卡诈骗罪"] == "001003005006"

    def test_entry_count(self):
        result = flatten_tree(MOCK_TREE)
        # 刑事, 危害公共安全罪, 放火罪, 交通肇事罪,
        # 破坏社会主义市场经济秩序罪, 扰乱市场秩序罪, 合同诈骗罪,
        # 金融诈骗罪, 信用卡诈骗罪
        assert len(result) == 9

    def test_empty_children(self):
        result = flatten_tree([{"name": "leaf", "id": "123", "children": []}])
        assert result == {"leaf": "123"}

    def test_no_children_key(self):
        result = flatten_tree([{"name": "leaf", "id": "456"}])
        assert result == {"leaf": "456"}


class TestBuildCategoryTree:
    def test_top_level_has_id_and_children(self):
        result = build_category_tree(MOCK_TREE)
        assert "刑事" in result
        assert result["刑事"]["id"] == "001"
        assert "children" in result["刑事"]

    def test_nested_children(self):
        result = build_category_tree(MOCK_TREE)
        assert "危害公共安全罪" in result["刑事"]["children"]

    def test_leaf_is_string_id(self):
        result = build_category_tree(MOCK_TREE)
        assert result["刑事"]["children"]["危害公共安全罪"]["children"]["放火罪"] == "001002001"

    def test_fourth_level_tree(self):
        result = build_category_tree(MOCK_TREE)
        l3 = result["刑事"]["children"]["破坏社会主义市场经济秩序罪"]["children"]["扰乱市场秩序罪"]
        assert l3["id"] == "001003008"
        assert l3["children"]["合同诈骗罪"] == "001003008004"

    def test_empty_input(self):
        assert build_category_tree([]) == {}
```

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `.venv/bin/python -m pytest tests/test_refresh_categories.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'refresh_categories'`

---

### Task 3: Implement refresh_categories.py Helper Functions (GREEN)

**Files:**
- Create: `scripts/refresh_categories.py`

- [ ] **Step 1: Create script with helper functions**

Create `scripts/refresh_categories.py`:

```python
"""Refresh CategoryNew tree from PKULaw live API.

Fetches the full 4-level category tree and regenerates src/config_data.py.

Usage: python scripts/refresh_categories.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DATA_PATH = PROJECT_ROOT / "src" / "config_data.py"

CLUSTER_API_URL = "/searchingapi/adv/cluster/pfnl"

CRIME_NAMES = [
    "危险驾驶罪", "交通肇事罪", "盗窃罪", "诈骗罪", "合同诈骗罪",
    "故意伤害罪", "强奸罪", "非法拘禁罪", "抢劫罪", "抢夺罪",
    "敲诈勒索罪", "妨害公务罪", "聚众斗殴罪", "寻衅滋事罪",
    "掩饰、隐瞒犯罪所得、犯罪所得收益罪", "走私、贩卖、运输、制造毒品罪",
    "非法持有毒品罪", "容留他人吸毒罪", "信用卡诈骗罪", "故意毁坏财物罪",
]


def flatten_tree(items: list[dict]) -> dict[str, str]:
    """Recursively flatten CategoryNew tree into name→ID pairs."""
    result = {}
    for item in items:
        result[item["name"]] = item.get("id", "")
        children = item.get("children") or []
        if children:
            result.update(flatten_tree(children))
    return result


def build_category_tree(items: list[dict]) -> dict:
    """Recursively build hierarchical tree dict."""
    result = {}
    for item in items:
        name = item["name"]
        vid = item.get("id", "")
        children = item.get("children") or []
        if children:
            result[name] = {"id": vid, "children": build_category_tree(children)}
        else:
            result[name] = vid
    return result


def fetch_category_tree(page, token: str) -> list[dict]:
    """Fetch full CategoryNew tree from PKULaw API."""
    data = page.evaluate(
        """async ([url, token]) => {
            const resp = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token,
                },
                body: JSON.stringify({"dimensionId": "CategoryNew"})
            });
            return await resp.json();
        }""",
        [CLUSTER_API_URL, token],
    )
    if isinstance(data, list) and data:
        dim = next((d for d in data if d.get("id") == "CategoryNew"), None)
        if dim:
            return dim.get("list") or []
    raise RuntimeError(f"Failed to fetch CategoryNew tree: {data}")


def _format_tree(d: dict, indent: int = 0) -> str:
    """Format a nested dict as Python source for CATEGORY_TREE."""
    prefix = "    " * indent
    if not d:
        return "{}"
    parts = []
    for key, value in d.items():
        if isinstance(value, dict):
            if "id" in value and "children" in value:
                inner = _format_tree(value["children"], indent + 2)
                parts.append(
                    f'{prefix}    "{key}": {{"id": "{value["id"]}", '
                    f'"children": {inner}}},'
                )
            else:
                inner = _format_tree(value, indent + 1)
                parts.append(f'{prefix}    "{key}": {inner},')
        else:
            parts.append(f'{prefix}    "{key}": "{value}",')
    return "{\n" + "\n".join(parts) + f"\n{prefix}}}"


def generate_config_data(new_values: dict[str, str], new_tree: dict) -> None:
    """Regenerate src/config_data.py with updated CategoryNew data."""
    from src.config_data import CLUSTER_DIMENSIONS, FIELD_DEFINITIONS

    updated_dims = {}
    for dim_id, dim_data in CLUSTER_DIMENSIONS.items():
        if dim_id == "CategoryNew":
            updated_dims[dim_id] = {"title": "案由", "values": new_values}
        else:
            updated_dims[dim_id] = dim_data

    lines = [
        '"""Auto-generated PKULaw API field mappings.',
        "",
        "Regenerated by: python scripts/refresh_categories.py",
        '"""',
        "",
    ]

    lines.append("FIELD_DEFINITIONS = {")
    for field_name, field_data in FIELD_DEFINITIONS.items():
        lines.append(f'    "{field_name}": {{')
        lines.append(f'        "show_text": "{field_data["show_text"]}",')
        lines.append(f'        "type": "{field_data["type"]}",')
        lines.append(f'        "order": {field_data["order"]},')
        lines.append("    },")
    lines.append("}")
    lines.append("")

    lines.append("CLUSTER_DIMENSIONS = {")
    for dim_id, dim_data in updated_dims.items():
        lines.append(f'    "{dim_id}": {{')
        lines.append(f'        "title": "{dim_data["title"]}",')
        lines.append(
            f'        "values": {json.dumps(dim_data["values"], ensure_ascii=False)},'
        )
        lines.append("    },")
    lines.append("}")
    lines.append("")

    tree_str = _format_tree(new_tree, indent=0)
    lines.append("CATEGORY_TREE = " + tree_str)
    lines.append("")

    CONFIG_DATA_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Updated {CONFIG_DATA_PATH} ({CONFIG_DATA_PATH.stat().st_size} bytes)")


def main():
    from src.auth import authenticate, close_browser, launch_browser

    print("Launching browser...")
    pw, browser, context, page = launch_browser()
    try:
        print("Authenticating...")
        token = authenticate(page)

        print("Fetching CategoryNew tree...")
        tree_data = fetch_category_tree(page, token)
        print(f"Got {len(tree_data)} top-level entries")

        values = flatten_tree(tree_data)
        print(f"Flattened to {len(values)} name-ID pairs")

        tree = build_category_tree(tree_data)
        print(f"Built tree with {len(tree)} top-level keys")

        missing = [n for n in CRIME_NAMES if n not in values]
        if missing:
            print(f"WARNING: {len(missing)} crime names still missing: {missing}")
        else:
            print("All 20 crime names resolved!")

        generate_config_data(values, tree)
        print("Done!")
    finally:
        close_browser(pw, browser)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run helper tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_refresh_categories.py -v`
Expected: All 13 tests PASS

---

### Task 4: Run Script Against Live API

**Files:**
- Modified by script: `src/config_data.py` (regenerated in-place)

- [ ] **Step 1: Execute the refresh script**

Run: `.venv/bin/python scripts/refresh_categories.py`
Expected output: `All 20 crime names resolved!` followed by `Done!`

- [ ] **Step 2: Verify entry count**

Run: `.venv/bin/python -c "
from src.config_data import CLUSTER_DIMENSIONS
cv = CLUSTER_DIMENSIONS['CategoryNew']['values']
print(f'CategoryNew entries: {len(cv)}')
assert len(cv) > 1600, f'Expected >1600, got {len(cv)}'
"`
Expected: `CategoryNew entries: 1661` (or close — the live API is the source of truth)

- [ ] **Step 3: Verify all 20 crime names resolve**

Run: `.venv/bin/python -c "
from src.config import resolve_value
names = [
    '危险驾驶罪','交通肇事罪','盗窃罪','诈骗罪','合同诈骗罪',
    '故意伤害罪','强奸罪','非法拘禁罪','抢劫罪','抢夺罪',
    '敲诈勒索罪','妨害公务罪','聚众斗殴罪','寻衅滋事罪',
    '掩饰、隐瞒犯罪所得、犯罪所得收益罪','走私、贩卖、运输、制造毒品罪',
    '非法持有毒品罪','容留他人吸毒罪','信用卡诈骗罪','故意毁坏财物罪',
]
for n in names:
    rid = resolve_value('CategoryNew', n)
    assert rid, f'{n} failed to resolve'
    print(f'  {n} -> {rid}')
print(f'All {len(names)} crime names resolved!')
"`
Expected: All 20 names print their IDs with no errors.

---

### Task 5: Add Crime Name Resolution Test

**Files:**
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add TestCrimeNameResolution class**

Append to the end of `tests/test_config.py`:

```python


class TestCrimeNameResolution:
    """All 20 target crime names must resolve to correct CategoryNew IDs."""

    CRIME_IDS = {
        "危险驾驶罪": "001002050",
        "交通肇事罪": "001002037",
        "盗窃罪": "001005002",
        "诈骗罪": "001005003",
        "合同诈骗罪": "001003008004",
        "故意伤害罪": "001004003",
        "强奸罪": "001004005",
        "非法拘禁罪": "001004008",
        "抢劫罪": "001005001",
        "抢夺罪": "001005004",
        "敲诈勒索罪": "001005010",
        "妨害公务罪": "001006001001",
        "聚众斗殴罪": "001006001020",
        "寻衅滋事罪": "001006001021",
        "掩饰、隐瞒犯罪所得、犯罪所得收益罪": "001006002018",
        "走私、贩卖、运输、制造毒品罪": "001006007",
        "非法持有毒品罪": "001006007002",
        "容留他人吸毒罪": "001006007011",
        "信用卡诈骗罪": "001003005006",
        "故意毁坏财物罪": "001005011",
    }

    def test_all_20_crime_names_resolve(self):
        for name, expected_id in self.CRIME_IDS.items():
            result = resolve_value("CategoryNew", name)
            assert result == expected_id, f"{name}: expected {expected_id}, got {result}"

    def test_crime_count_is_20(self):
        assert len(self.CRIME_IDS) == 20
```

- [ ] **Step 2: Run new test**

Run: `.venv/bin/python -m pytest tests/test_config.py::TestCrimeNameResolution -v`
Expected: 2 tests PASS

---

### Task 6: Full Test Suite + Commit

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (129 original + 13 helpers + 2 crime resolution = 144 total)

- [ ] **Step 2: Verify no gitignored files staged**

Run: `git status`
Expected: Only these files modified/created:
- `scripts/refresh_categories.py` (new)
- `tests/test_refresh_categories.py` (new)
- `tests/test_config.py` (modified)
- `src/config_data.py` (modified — regenerated)

- [ ] **Step 3: Commit**

```bash
git add scripts/refresh_categories.py tests/test_refresh_categories.py tests/test_config.py src/config_data.py
git commit -m "feat: refresh config_data with full 4-level CategoryNew tree

- Add scripts/refresh_categories.py to fetch CategoryNew from live API
- Regenerate src/config_data.py with all entries (4 levels)
- All 20 crime names now resolve via resolve_value
- Add unit tests for tree flattening helpers
- Add integration test for 20 crime name resolution

Closes #8"
```
