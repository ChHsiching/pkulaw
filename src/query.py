"""Convert SearchConfig to PKULaw API request body."""

from src.config import CATEGORY_VALUES, FIELD_DEFINITIONS, _dim_key

PAGE_SIZE = 100

DATE_RANGE_FIELDS = {
    f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "daterange"
}

_TEXT_FIELDS = {f for f, d in FIELD_DEFINITIONS.items() if d["type"] == "text"}


def reverse_lookup(field: str, api_id: str) -> str | None:
    """Look up the Chinese name for an API ID. Returns None if not found."""
    dim = _dim_key(field)
    values = CATEGORY_VALUES.get(dim, {})
    for name, vid in values.items():
        if vid == api_id:
            return name
    return None


def _build_text_node(field_name: str, value: str) -> dict:
    """Build a text-type fieldNode for keyword search fields."""
    show_text = FIELD_DEFINITIONS.get(field_name, {}).get("show_text", field_name)
    return {
        "type": "text",
        "order": 0,
        "combineAs": 2,
        "fieldName": field_name,
        "showText": show_text,
        "subCombineAs": 2,
        "fieldItems": [
            {
                "values": value,
                "valuesCombineAs": 2,
                "extra": {"values": "", "combineAs": 2},
                "matchType": 1,
                "matchSpan": 1,
                "matchSpanGap": 0,
                "fieldScope": {"fieldName": "", "showText": ""},
                "order": 0,
                "filterNodes": [],
            }
        ],
        "matchTypeEnabled": False,
        "matchSpanEnabled": True,
        "matchSpans": None,
    }


def _build_select_node(field_name: str, values: list[str]) -> dict:
    """Build a select/checkbox-type fieldNode for multi-value filter fields."""
    field_type = FIELD_DEFINITIONS.get(field_name, {}).get("type", "select")
    show_text = FIELD_DEFINITIONS.get(field_name, {}).get("show_text", field_name)
    items = []
    for vid in values:
        name = reverse_lookup(field_name, vid) or vid
        items.append({"text": name, "path": vid, "name": name, "value": vid})
    return {
        "type": field_type,
        "order": 0,
        "combineAs": 2,
        "fieldName": field_name,
        "showText": show_text,
        "fieldItems": [
            {
                "items": items,
                "combineAs": 2,
                "order": 0,
                "filterNodes": [],
            }
        ],
    }


def build_api_body(
    search_config: dict,
    page_index: int = 0,
    page_size: int = PAGE_SIZE,
    order_by: str = "LastInstanceDate Desc",
    group_by: dict | None = None,
    cluster_overrides: dict | None = None,
) -> dict:
    """Convert a SearchConfig dict to a PKULaw API request body."""
    field_nodes_api = []
    cluster_filters = {}

    for node in search_config.get("fieldNodes", []):
        field = node["field"]
        if field in DATE_RANGE_FIELDS:
            continue
        if field == "CategoryNew":
            ids = node.get("values", [])
            if ids:
                cluster_filters["CategoryNew"] = ids[0]
            continue
        if field in _TEXT_FIELDS:
            value = node.get("value", "")
            if value:
                field_nodes_api.append(_build_text_node(field, value))
        else:
            values = node.get("values", [])
            if values:
                field_nodes_api.append(_build_select_node(field, values))

    if cluster_overrides:
        cluster_filters.update(cluster_overrides)

    if "_groupBy" in search_config and not group_by:
        group_by = search_config["_groupBy"]

    return {
        "orderbyExpression": order_by,
        "pageIndex": page_index,
        "pageSize": page_size,
        "fieldNodes": field_nodes_api,
        "clusterFilters": cluster_filters,
        "groupBy": group_by or {},
    }
