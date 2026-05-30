"""PKULaw API field definitions and Chinese-to-API ID resolution."""

from src.config_data import CATEGORY_TREE, CLUSTER_DIMENSIONS, FIELD_DEFINITIONS

__all__ = [
    "FIELD_DEFINITIONS",
    "CATEGORY_TREE",
    "CATEGORY_VALUES",
    "CLI_TO_FIELD_MAP",
    "FIELD_CLI_NAMES",
    "resolve_value",
    "resolve_values",
    "validate_field_values",
]

CATEGORY_VALUES: dict[str, dict[str, str]] = {
    dim_id: dim_data["values"] for dim_id, dim_data in CLUSTER_DIMENSIONS.items()
}

CLI_TO_FIELD_MAP: dict[str, str] = {
    "--full-text": "FullText",
    "--title": "Title",
    "--case-flag": "CaseFlag",
    "--gist": "CaseGist",
    "--party": "Party",
    "--judge": "Judge",
    "--lawyer": "AgentLawyer",
    "--law-firm": "AgentLawOffice",
    "--category": "CategoryNew",
    "--trial-step": "TrialStep",
    "--court-grade": "CourtGrade",
    "--court": "LastInstanceCourt",
    "--case-grade": "CaseGrade",
    "--case-class": "CaseClass",
    "--doc-type": "DocumentAttr",
    "--result": "TrialStepCount",
    "--topic": "SubjectClassSpecialType",
    "--punishment": "CriminalPunish",
    "--accusation": "Accusation",
    "--date-range": "LastInstanceDate",
    "--issue-date-range": "IssueDate",
    "--public-type": "NoPublicReason",
    "--judge-type": "JudgeType",
    "--guiding-case-no": "GuidingCaseNO",
    "--source-note": "SourceNote",
}

_FIELD_TO_DIMENSION: dict[str, str] = {
    "CriminalPunish": "PenaltyCodes",
}

FIELD_CLI_NAMES: dict[str, str] = {
    v: k.lstrip("-").replace("-", "_") for k, v in CLI_TO_FIELD_MAP.items()
}

_HIERARCHICAL_FIELDS = {
    "CategoryNew",
    "CaseClass",
    "CaseGrade",
    "CriminalPunish",
    "PenaltyCodes",
    "DocumentAttr",
    "CaseElements",
}

_TEXT_FIELDS = {f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "text"}


def _dim_key(field: str) -> str:
    """Map a field name to its CLUSTER_DIMENSIONS key."""
    return _FIELD_TO_DIMENSION.get(field, field)


def resolve_value(field: str, path: str) -> str:
    """Resolve a Chinese name or hierarchical path to an API ID."""
    if field in _TEXT_FIELDS:
        return path

    dim = _dim_key(field)
    parts = path.split(">")

    if dim in _HIERARCHICAL_FIELDS and len(parts) > 1:
        return _resolve_hierarchical(dim, parts)

    values = CATEGORY_VALUES.get(dim, {})
    if not values:
        if field in FIELD_DEFINITIONS:
            return path
        raise ValueError(f"Unknown field '{field}'")

    if path in values:
        return values[path]

    if path in values.values():
        return path

    raise ValueError(f"Unknown value '{path}' for field '{field}'")


def _resolve_hierarchical(field: str, parts: list[str]) -> str:
    """Walk a tree or flat map to resolve a hierarchical path."""
    if field == "CategoryNew":
        return _resolve_category_tree(parts)

    flat = CATEGORY_VALUES.get(field, {})
    if not flat:
        return ">".join(parts)

    full_path = ">".join(parts)
    if full_path in flat:
        return flat[full_path]

    if parts[-1] in flat:
        return flat[parts[-1]]

    raise ValueError(f"'{full_path}' not found in {field}")


def _resolve_category_tree(parts: list[str]) -> str:
    """Walk the CATEGORY_TREE to resolve a hierarchical CategoryNew path."""
    current = CATEGORY_TREE
    for i, part in enumerate(parts):
        if isinstance(current, dict):
            if part in current:
                entry = current[part]
            else:
                flat = CATEGORY_VALUES.get("CategoryNew", {})
                if part in flat:
                    return flat[part]
                raise ValueError(f"'{part}' not found in CategoryNew at level {i + 1}")

            if isinstance(entry, str):
                if i == len(parts) - 1:
                    return entry
                raise ValueError(f"'{part}' is a leaf but path continues")
            elif isinstance(entry, dict):
                if "id" in entry and "children" in entry:
                    if i == len(parts) - 1:
                        return entry["id"]
                    current = entry["children"]
                else:
                    raise ValueError(f"Unexpected structure at '{part}'")
            else:
                raise ValueError(f"Unexpected type at '{part}'")
        else:
            raise ValueError(f"Cannot navigate into non-dict at '{part}'")
    return ""


def resolve_values(field: str, comma_path: str) -> list[str]:
    """Resolve comma-separated paths to a list of API IDs."""
    return [resolve_value(field, p.strip()) for p in comma_path.split(",")]


def validate_field_values(field: str, values: list[str]) -> None:
    """Validate that all values are valid API IDs for the given field."""
    if field in _TEXT_FIELDS:
        return

    dim = _dim_key(field)
    valid_ids = set(CATEGORY_VALUES.get(dim, {}).values())
    if not valid_ids:
        return

    for v in values:
        if v not in valid_ids:
            raise ValueError(
                f"Invalid value '{v}' for field '{field}'. "
                f"Valid: {sorted(valid_ids)[:10]}..."
            )
