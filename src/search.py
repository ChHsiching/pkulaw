import time
import json

import requests

from src.auth import get_auth_session

BASE_URL = "https://www.pkulaw.com"
SEARCH_ENDPOINT = "/searchingapi/adv/list/pfnl"
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry


def build_search_body(page_index: int, page_size: int = 20) -> dict:
    return {
        "orderbyExpression": "SortNum Desc,LastInstanceDate Desc",
        "pageIndex": page_index,
        "pageSize": page_size,
        "fieldNodes": [
            {
                "type": "text",
                "order": 1,
                "combineAs": 2,
                "fieldName": "FullText",
                "showText": "全文",
                "subCombineAs": 2,
                "fieldItems": [
                    {
                        "values": "抗诉",
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
            },
            {
                "type": "select",
                "order": 6,
                "combineAs": 2,
                "fieldName": "TrialStep",
                "showText": "审理程序",
                "fieldItems": [
                    {
                        "items": [
                            {"text": "二审", "path": "002", "name": "二审", "value": "002"},
                            {"text": "再审", "path": "003", "name": "再审", "value": "003"},
                        ],
                        "combineAs": 2,
                        "order": 0,
                        "filterNodes": [],
                    }
                ],
            },
        ],
        "clusterFilters": {"CategoryNew": "001"},
        "groupBy": {},
    }


def _make_session(token: str, cookies: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
    )
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="www.pkulaw.com")
    return session


def search_cases(
    token: str,
    cookies: dict,
    total_limit: int = 500,
    page_size: int = 20,
    delay: float = 1.0,
) -> list[dict]:
    """Search and return up to total_limit cases with gid, title, summaries."""
    session = _make_session(token, cookies)
    results = []
    page_index = 0

    while len(results) < total_limit:
        body = build_search_body(page_index, page_size)

        for attempt in range(MAX_RETRIES):
            try:
                resp = session.post(
                    f"{BASE_URL}{SEARCH_ENDPOINT}",
                    json=body,
                    timeout=30,
                    verify=False,
                )

                if resp.status_code == 401:
                    print("Token expired, refreshing...")
                    new_token, new_cookies = get_auth_session()
                    session = _make_session(new_token, new_cookies)
                    continue

                resp.raise_for_status()
                data = resp.json()
                break

            except (requests.RequestException, json.JSONDecodeError) as e:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"Search error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    print(f"  Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Search failed after {MAX_RETRIES} retries") from e
        else:
            raise RuntimeError("Search failed: all retries exhausted on auth refresh")

        total = data.get("total", 0)
        items = data.get("data", [])
        if not items:
            break

        for item in items:
            if len(results) >= total_limit:
                break
            results.append(
                {
                    "gid": item["gid"],
                    "title": item.get("title", ""),
                    "summaries": [
                        s.get("text", "") for s in item.get("summaries", [])
                    ],
                }
            )

        print(
            f"Page {page_index + 1}: got {len(items)} cases "
            f"(total so far: {len(results)}/{total_limit}, "
            f"API total: {total})"
        )

        page_index += 1
        if len(results) < total_limit:
            time.sleep(delay)

    return results


if __name__ == "__main__":
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    token, cookies = get_auth_session()
    print(f"Authenticated. Starting search...")
    cases = search_cases(token, cookies, total_limit=5)
    print(f"\nGot {len(cases)} cases:")
    for c in cases:
        print(f"  {c['title'][:60]} (gid: {c['gid'][:20]}...)")
