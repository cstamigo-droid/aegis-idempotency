# aegis-idempotency

[![PyPI version](https://img.shields.io/pypi/v/aegis-idempotency)](https://pypi.org/project/aegis-idempotency/)
[![Python versions](https://img.shields.io/pypi/pyversions/aegis-idempotency)](https://pypi.org/project/aegis-idempotency/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Async Python client for the **AEGIS HITL Reliability Layer** — exactly-once human-in-the-loop approvals for AI agents.

## What problem does it solve?

AI agents that take consequential actions (send emails, execute trades, modify databases) need a human checkpoint before acting. Naively calling an approval endpoint is unsafe: network retries and crashes can trigger the same action twice.

`aegis-idempotency` solves this with **strict idempotency** — every approve/reject call carries an `Idempotency-Key` that the server uses to deduplicate across retries. You can retry safely; the action executes exactly once.

Key guarantees:
- **Exactly-once execution** — duplicate calls return `409 Conflict`, never re-trigger the action.
- **Safe retries with exponential backoff** — automatic retry on `5xx`, no retry on `4xx`.
- **Unique request tracing** — every call gets an auto-generated `X-Request-Id`.

## Installation

```bash
pip install aegis-idempotency
```

> **Note:** The PyPI distribution is `aegis-idempotency`; the import name is `aegis_hitl`.

## Quickstart

```python
import asyncio
from aegis_hitl import AegisClient

async def main():
    async with AegisClient(
        base_url="http://localhost:8000",
        tenant_id="tenant-abc",
        thread_id="thread-xyz",
    ) as client:
        # Approve an agent action — idempotent, safe to retry
        response = await client.approve(
            "idempotency-key-2026-001",
            payload={"action": "send_email", "to": "user@example.com"},
        )

        if response.status_code == 202:
            print("Action approved and queued.")
        elif response.status_code == 409:
            print("Duplicate — action was already processed.")

asyncio.run(main())
```

## API Reference

### `AegisClient` constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | `"http://localhost:8000"` | Base URL of the AEGIS server |
| `tenant_id` | `str \| None` | `None` | Default tenant ID (required per call if not set here) |
| `thread_id` | `str \| None` | `None` | Default thread/conversation ID |
| `timeout` | `float` | `10.0` | HTTP timeout in seconds |
| `max_retries` | `int` | `3` | Max retries on `5xx` responses |
| `api_prefix` | `str` | `"/api/v1"` | API prefix path |
| `client` | `httpx.AsyncClient \| None` | `None` | Inject an external httpx client (for testing) |

### Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `approve(key, *, tenant_id, thread_id, payload)` | POST `/hitl/approve` with idempotency key | `httpx.Response` |
| `reject(key, *, tenant_id, thread_id, payload)` | POST `/hitl/reject` with idempotency key | `httpx.Response` |
| `execute(action, key, *, tenant_id, thread_id, payload)` | Dispatch to approve or reject based on `action` string | `httpx.Response` |
| `get_status(request_id)` | GET `/hitl/status/{request_id}` | `httpx.Response` |

### Response status codes

| Code | Meaning |
|------|---------|
| `202` | Action accepted and queued for processing |
| `409` | Duplicate key — action already processed (idempotency hit) |
| `5xx` | Server error — client will retry up to `max_retries` times |

## Testing without a server

`AegisClient` accepts an injected `httpx.AsyncClient`, making it easy to test with `httpx.MockTransport`:

```python
import httpx
import pytest
from aegis_hitl import AegisClient

@pytest.mark.asyncio
async def test_approve():
    def handler(request):
        return httpx.Response(202, json={"ok": True})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    )
    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        r = await client.approve("key-001")
    assert r.status_code == 202
```

## About AEGIS

`aegis-idempotency` is the client SDK for the **AEGIS platform** — a reliability layer for AI agents that ensures human approval, exactly-once execution, and full audit trail for any consequential agent action. The server/core component is a separate private service.

## License

MIT — see [LICENSE](LICENSE).
