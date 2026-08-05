# finsharpe-call-records

Call Record emission for FinSharpe MCP providers.

A **Call Record** is one observation of a single tool invocation at a provider,
attributed to the principal that made it. Records are the evidence a **Usage
Signature** is computed from, and the input to the **Allowance** check the
Authorization Server runs when it mints a token.

## Scope

Emission and nothing else. No sampling, no Usage Signature computation, no
limit checking, no retention. Those change often and per-provider; the record
format must not. Keeping this surface minimal is what makes providers
independently deployable and what makes adding the sixth MCP cheap.

This package is published for FinSharpe's own MCP providers. It is public
because its consumers are, not because it is offered for general use: outside
that use there is no stability guarantee, and the Python surface may change
between versions without ceremony. The artifact under compatibility discipline
is [the wire contract](#the-wire-contract) — the record format — not this API.

## Install

Consumed as a dependency — never vendored or copied — pinned to an **exact
commit sha**:

```toml
dependencies = [
    "finsharpe-call-records @ git+https://github.com/FinSharpe/finsharpe-call-records.git@bfd6eaa88616450291198086c4eb089d80af5c42",  # v0.1.1
]
```

Not a tag. A tag re-resolves on every build and can be force-moved, and provider
Dockerfiles run `pip install -e .` against a `uv.lock` that no Dockerfile copies
— so anything movable drifts silently, on a path that is fire-and-forget by
construction and therefore never turns anything red.

A direct reference costs the consuming project two things, both of which fail
only when its Docker image is built and neither of which any test reaches:

- **`git` in the image.** pip shells out to the git binary to clone this, and
  `python:*-slim` has none. Add it to the apt layer.
- **`allow-direct-references`.** hatchling refuses to generate metadata for a
  project declaring a direct reference. Invisible locally, because the consuming
  project is already installed editable.

  ```toml
  [tool.hatch.metadata]
  allow-direct-references = true
  ```

Both disappear when this library moves to PyPI and the pin becomes an exact
`==` version — decided in `finsharpe-agents` ADR-0008, tracked in
FinSharpe/finsharpe-agents#85.

## Use

```python
from fastmcp import FastMCP
from finsharpe_call_records import install_call_records

mcp = FastMCP("tradekit", ...)
install_call_records(mcp, provider="tradekit")
```

That is the entire integration. Registration is unconditional: a provider with
no sink configured still carries the middleware and emits into a `NullSink`, so
"does this server emit?" is a property of the server rather than of the
environment it happens to be booted in.

Each provider should also keep a test that fails when the middleware is missing
— a provider that installed the library but never registered it emits nothing
and is otherwise indistinguishable from a provider with no traffic:

```python
from finsharpe_call_records import find_call_record_middleware

def test_server_emits_call_records():
    from myprovider.app import mcp
    assert find_call_record_middleware(mcp) is not None
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CALL_RECORDS_SINK_URL` | *(unset)* | Ingest endpoint. Unset → records are built and discarded. |
| `CALL_RECORDS_API_KEY` | *(unset)* | Shared secret sent as `X-Call-Record-Key`. |
| `CALL_RECORDS_TIMEOUT_SECONDS` | `2.0` | Per-delivery HTTP timeout. |
| `CALL_RECORDS_MAX_IN_FLIGHT` | `512` | Undelivered records held before dropping. |

## Fire-and-forget

A sink that is slow, erroring, or unreachable must never fail, delay, or alter
a tool call. The record is built after the tool has already returned and handed
to a background task that is never awaited; when the backlog reaches
`CALL_RECORDS_MAX_IN_FLIGHT` records are dropped rather than queued. This is
safe precisely because ADR-0006 puts no decision on the request path.

## The wire contract

The record format is the real shared artifact. Providers deploy independently,
so several library versions are always live at once:

- every record carries `format_version`;
- new fields are **additive** — an unknown field is carried, never a reason to
  reject a record;
- a field is never repurposed.

| Field | Meaning |
|---|---|
| `format_version` | Record format version |
| `occurred_at` | When the call started (UTC) |
| `principal_id` | `sub` claim — Grant-Holder user id, or the Service Identity |
| `principal_type` | `grant_holder` \| `service_identity` |
| `grant_id` | The Grant the call was made under |
| `client_id` | OAuth client identity (self-asserted; never an access-control input) |
| `token_id` | Access token `jti` |
| `provider` | Which MCP served the call |
| `tool_name` | Tool invoked |
| `arguments` | Arguments as passed |
| `duration_ms` | How long the call took |
| `outcome` | `success` \| `failed` \| `error` |

`principal_type` is recorded, never inferred. Orchestrator Access reaches
providers under the **Service Identity** and is metered upstream as **Credits**;
marking it prevents a later analysis mistaking it for one impossibly heavy
Grant-Holder.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Library behaviour is tested against an in-memory FastMCP server with a fake
sink, not through a live provider — testing it once rather than once per
provider is the reason the library exists.
