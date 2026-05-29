"""Generate src/config_data.py from PKULaw API data files.

Usage: python scripts/generate_config_data.py /tmp/pkulaw_cluster_full.json /tmp/pkulaw_form_full.json
"""

import json
import sys
from pathlib import Path


def build_flat_map(items: list[dict]) -> dict[str, str]:
    result = {}
    for item in items:
        result[item["name"]] = item.get("id", "")
    return result


def build_tree(items: list[dict]) -> dict:
    result = {}
    for item in items:
        name = item["name"]
        vid = item.get("id", "")
        children = item.get("children") or []
        if children:
            result[name] = {"id": vid, "children": build_tree(children)}
        else:
            result[name] = vid
    return result


def build_hierarchical_map(items: list[dict]) -> dict[str, str]:
    result = {}
    for item in items:
        name = item["name"]
        vid = item.get("id", "")
        result[name] = vid
        for child in item.get("children") or []:
            child_name = child["name"]
            child_id = child.get("id", "")
            result[child_name] = child_id
            for grandchild in child.get("children") or []:
                result[grandchild["name"]] = grandchild.get("id", "")
    return result


def main():
    cluster_path = Path(sys.argv[1])
    form_path = Path(sys.argv[2])
    output_path = Path(__file__).resolve().parent.parent / "src" / "config_data.py"

    with open(cluster_path) as f:
        cluster_data = json.load(f)
    with open(form_path) as f:
        form_data = json.load(f)

    lines = [
        '"""Auto-generated PKULaw API field mappings.',
        "",
        f"Generated from: {cluster_path.name}, {form_path.name}",
        "DO NOT EDIT -- regenerate with: python scripts/generate_config_data.py",
        '"""',
        "",
    ]

    # Field definitions from form
    lines.append("FIELD_DEFINITIONS = {")
    for field in form_data:
        fn = field["fieldName"]
        lines.append(f'    "{fn}": {{')
        lines.append(f'        "show_text": "{field.get("showText", "")}",')
        lines.append(f'        "type": "{field.get("type", "")}",')
        lines.append(f'        "order": {field.get("order", 0)},')
        lines.append("    },")
    lines.append("}")
    lines.append("")

    # Cluster dimension mappings
    lines.append("CLUSTER_DIMENSIONS = {")
    for dim in cluster_data:
        dim_id = dim["id"]
        dim_title = dim["title"]
        values = dim.get("list") or []
        lines.append(f'    "{dim_id}": {{')
        lines.append(f'        "title": "{dim_title}",')
        if values:
            flat = build_hierarchical_map(values)
            lines.append(f'        "values": {json.dumps(flat, ensure_ascii=False)},')
        else:
            lines.append('        "values": {},')
        lines.append("    },")
    lines.append("}")
    lines.append("")

    # CategoryNew tree (full hierarchy)
    cat_dim = next(d for d in cluster_data if d["id"] == "CategoryNew")
    cat_tree = build_tree(cat_dim.get("list") or [])
    tree_str = _format_dict(cat_tree, indent=0)
    lines.append("CATEGORY_TREE = " + tree_str)
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {output_path} ({output_path.stat().st_size} bytes)")


def _format_dict(d: dict, indent: int) -> str:
    prefix = "    " * indent
    if not d:
        return "{}"

    parts = []
    for key, value in d.items():
        if isinstance(value, dict):
            if "children" in value and isinstance(value["children"], dict):
                inner = _format_dict(value["children"], indent + 2)
                parts.append(
                    f'{prefix}    "{key}": {{"id": "{value["id"]}", "children": {inner}}},'
                )
            elif all(isinstance(v, str) for v in value.values()):
                items = ", ".join(f'"{k}": "{v}"' for k, v in value.items())
                parts.append(f'{prefix}    "{key}": {{{items}}},')
            else:
                inner = _format_dict(value, indent + 1)
                parts.append(f'{prefix}    "{key}": {inner},')
        else:
            parts.append(f'{prefix}    "{key}": "{value}",')

    return "{\n" + "\n".join(parts) + f"\n{prefix}}}"


if __name__ == "__main__":
    main()
