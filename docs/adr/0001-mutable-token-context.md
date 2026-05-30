# ADR 0001: Mutable TokenContext for Token Propagation

## Status

Accepted

## Context

`search_api` reauthenticates when the PKULaw API token expires, but the refreshed token
is stored in a local `str` variable. Since `str` is immutable and `search_api` returns
`dict`, callers (notably `partition_query`) keep using the expired token for subsequent
API calls. During `partition_query`'s 7+ minute recursive partitioning, the token expires
mid-way and all child queries fail silently (API error treated as empty result).

## Decision

Introduce a `TokenContext` dataclass that wraps the token string. `search_api` mutates
`ctx.token` on reauthentication, so all holders of the same instance see the updated token.

```python
@dataclass
class TokenContext:
    token: str
```

## Alternatives Considered

### Return `tuple[dict, str]` from search_api

```python
def search_api(page, token, body) -> tuple[dict, str]:
    ...
    return data, token
```

Pros: No mutable state, functional style.
Cons: Requires updating all callers to unpack the tuple. `partition_query`'s recursive
calls would need to thread the token through every return. More API surface change.

### Mutable dict `{"token": t}`

Pros: No new type needed.
Cons: No type hints, less ergonomic (`ctx["token"]` vs `ctx.token`), easy to typo keys.

## Consequences

- `search_api` and `partition_query` signatures change to accept `TokenContext` instead of `str`.
- External entry points (`run_search`, `cmd_estimate`) keep accepting `str` and create `TokenContext` internally.
- All test mocks that simulate `search_fn` must pass `TokenContext` instead of raw string.
