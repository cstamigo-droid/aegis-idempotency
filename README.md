# aegis-idempotency

[![PyPI version](https://img.shields.io/pypi/v/aegis-idempotency)](https://pypi.org/project/aegis-idempotency/)
[![Python versions](https://img.shields.io/pypi/pyversions/aegis-idempotency)](https://pypi.org/project/aegis-idempotency/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **AEGIS is the reliability layer that makes AI agents safe to run in production.**

Async Python SDK for the **AEGIS HITL Reliability Layer** — exactly-once execution and human approval for every AI agent action.

---

## The problem

AI agents that take real-world actions (send an email, charge a card, modify a database) fail in non-obvious ways in production:

- **Retries cause duplicates** — two emails sent, two charges fired, two records created.
- **No human checkpoint** — an agent can act on a hallucination with no way to intercept it.
- **No audit trail** — when something goes wrong, you have no record of what the agent did and why.

AEGIS solves all three with one `pip install`.

---

## Quickstart — Hosted API (free tier)

```bash
pip install aegis-idempotency
```

```python
import asyncio
from aegis_hitl import AegisClient

# 1. Sign up at https://aegis-idempotency-production.up.railway.app/docs
#    POST /api/v1/accounts/signup → returns your sk_live_... API key

async def main():
    async with AegisClient(
        base_url="https://aegis-idempotency-production.up.railway.app",
        api_key="sk_live_...",   # your AEGIS API key
        thread_id="order-42",   # unique identifier for this agent run
    ) as client:

        # Idempotent — retries won't fire the action twice
        response = await client.approve(
            "idempotency-key-2026-001",
            payload={"action": "send_email", "to": "user@example.com"},
        )

        if response.status_code == 202:
            print("Action approved and queued.")
        elif response.status_code == 409:
            print("Duplicate — already processed. Safe to ignore.")

asyncio.run(main())
```

**Free tier:** 100 events/month, no credit card required.
[View plans →](https://aegis-idempotency-production.up.railway.app/api/v1/billing/plans)

---

## Quickstart — Self-hosted

```bash
# 1. Clone and start the AEGIS server
docker compose up        # API :8000 · Redis :6379
alembic upgrade head     # DB migrations
```

```python
async with AegisClient(
    base_url="http://localhost:8000",
    tenant_id="your-tenant-id",
    thread_id="order-42",
) as client:
    response = await client.approve("idempotency-key-001")
```

---

## Three guarantees

| Guarantee | What it means |
|---|---|
| **Exactly-once** | Every call carries an `Idempotency-Key`. Retries, crashes, and 500 concurrent requests — actions fire **once**. State machine: `PENDING → COMMITTED → FAILED`. |
| **HITL gate** | Block any agent action until a human (or policy) explicitly approves. Thread-safe, tenant-isolated, Bearer-token-enforced. |
| **Safe retries** | Automatic exponential backoff on `5xx`. No retry on `4xx`. Auto-generated `X-Request-Id` for tracing. |

---

## API Reference

### `AegisClient` constructor

| Parameter | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | `"http://localhost:8000"` | AEGIS server URL |
| `api_key` | `str \| None` | `None` | API key for hosted usage (`sk_live_...`) — sent as `Authorization: Bearer` |
| `tenant_id` | `str \| None` | `None` | Tenant ID for self-hosted usage |
| `thread_id` | `str \| None` | `None` | Default thread/conversation ID |
| `timeout` | `float` | `10.0` | HTTP timeout in seconds |
| `max_retries` | `int` | `3` | Max retries on `5xx` |
| `client` | `httpx.AsyncClient \| None` | `None` | Inject an external httpx client (testing) |

### Methods

| Method | Description |
|---|---|
| `approve(key, *, thread_id, payload)` | POST `/hitl/approve` — approve an agent action |
| `reject(key, *, thread_id, payload)` | POST `/hitl/reject` — reject an agent action |
| `execute(action, key, *, thread_id, payload)` | Dispatch to approve or reject |
| `get_status(request_id)` | GET `/hitl/status/{request_id}` — current state |

### Status codes

| Code | Meaning |
|---|---|
| `202` | Accepted and queued |
| `409` | Duplicate key — already processed (safe to ignore) |
| `429` | Monthly quota exceeded — upgrade your plan |
| `5xx` | Server error — client retries automatically |

---

## Works with any agent framework

```python
# LangGraph node example
async def review_node(state: AgentState) -> AgentState:
    async with AegisClient(
        base_url="https://aegis-idempotency-production.up.railway.app",
        api_key=AEGIS_KEY,
        thread_id=state["run_id"],
    ) as client:
        r = await client.approve(state["idempotency_key"], payload=state["action"])
        if r.status_code != 202:
            return {**state, "status": "rejected"}
    return {**state, "status": "approved"}
```

Works with **LangGraph, CrewAI, AutoGen, n8n**, or plain Python.

---

## Testing without a server

```python
import httpx, pytest
from aegis_hitl import AegisClient

@pytest.mark.asyncio
async def test_approve():
    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(202, json={"ok": True})),
        base_url="http://test",
    )
    async with AegisClient(api_key="sk_live_test", thread_id="th1", client=mock_client) as client:
        r = await client.approve("key-001")
    assert r.status_code == 202
```

---

## About AEGIS

AEGIS is a production reliability layer for AI agents: exactly-once execution, human approval gates,
per-event billing, Prometheus metrics, and tenant isolation — validated with 500 concurrent requests
on real PostgreSQL.

- **Hosted API:** [aegis-idempotency-production.up.railway.app/docs](https://aegis-idempotency-production.up.railway.app/docs)
- **PyPI:** [pypi.org/project/aegis-idempotency](https://pypi.org/project/aegis-idempotency/)

## License

MIT — see [LICENSE](LICENSE).
