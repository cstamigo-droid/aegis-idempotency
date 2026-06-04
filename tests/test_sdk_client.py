"""Unit tests for aegis_hitl.AegisClient — no server, no Docker."""
import asyncio
import pytest
import httpx
from aegis_hitl import AegisClient


def _make_transport(status: int = 202) -> httpx.MockTransport:
    """Return a MockTransport that always responds with the given status."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"ok": True})
    return httpx.MockTransport(handler)


# ── approve ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_posts_to_correct_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        response = await client.approve("key-001")

    assert response.status_code == 202
    assert captured["path"] == "/api/v1/hitl/approve"
    assert captured["headers"]["tenant-id"] == "t1"
    assert captured["headers"]["thread-id"] == "th1"
    assert captured["headers"]["idempotency-key"] == "key-001"
    assert "x-request-id" in captured["headers"]


# ── reject ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_posts_to_correct_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        response = await client.reject("key-002")

    assert response.status_code == 202
    assert captured["path"] == "/api/v1/hitl/reject"


# ── execute ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_approve_dispatches_correctly():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        await client.execute("approve", "key-003")

    assert captured["path"] == "/api/v1/hitl/approve"


@pytest.mark.asyncio
async def test_execute_reject_dispatches_correctly():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        await client.execute("reject", "key-004")

    assert captured["path"] == "/api/v1/hitl/reject"


@pytest.mark.asyncio
async def test_execute_invalid_action_raises_value_error():
    mock_client = httpx.AsyncClient(
        transport=_make_transport(), base_url="http://test"
    )
    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        with pytest.raises(ValueError, match="approve.*reject"):
            await client.execute("delete", "key-005")


# ── tenant/thread resolution ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_per_call_tenant_thread_overrides_constructor():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tenant"] = request.headers.get("tenant-id")
        captured["thread"] = request.headers.get("thread-id")
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="default-t", thread_id="default-th", client=mock_client) as client:
        await client.approve("key-006", tenant_id="override-t", thread_id="override-th")

    assert captured["tenant"] == "override-t"
    assert captured["thread"] == "override-th"


@pytest.mark.asyncio
async def test_missing_tenant_id_raises_value_error():
    mock_client = httpx.AsyncClient(
        transport=_make_transport(), base_url="http://test"
    )
    async with AegisClient(thread_id="th1", client=mock_client) as client:
        with pytest.raises(ValueError, match="tenant_id"):
            await client.approve("key-007")


@pytest.mark.asyncio
async def test_missing_thread_id_raises_value_error():
    mock_client = httpx.AsyncClient(
        transport=_make_transport(), base_url="http://test"
    )
    async with AegisClient(tenant_id="t1", client=mock_client) as client:
        with pytest.raises(ValueError, match="thread_id"):
            await client.approve("key-008")


# ── X-Request-Id generation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_x_request_id_is_auto_generated():
    ids = []

    def handler(request: httpx.Request) -> httpx.Response:
        ids.append(request.headers.get("x-request-id"))
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="t1", thread_id="th1", client=mock_client) as client:
        await client.approve("key-009")
        await client.approve("key-010")

    assert ids[0] is not None
    assert ids[1] is not None
    assert ids[0] != ids[1]  # each call generates a unique request-id


# ── injected client lifecycle ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_injected_client_not_closed_on_exit():
    """AegisClient must NOT close an externally-provided httpx.AsyncClient."""
    transport = _make_transport()
    external = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(tenant_id="t1", thread_id="th1", client=external) as client:
        await client.approve("key-011")

    # external client must still be usable after AegisClient exits
    assert not external.is_closed
    await external.aclose()


# ── backoff / retry ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backoff_retries_on_5xx():
    """Client retries up to max_retries times on 5xx responses."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500, json={"error": "server error"})
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(
        tenant_id="t1", thread_id="th1", client=mock_client, max_retries=3
    ) as client:
        import unittest.mock
        with unittest.mock.patch("aegis_hitl.client.asyncio.sleep"):
            response = await client.approve("key-backoff-1")

    assert response.status_code == 202
    assert call_count == 3  # failed twice, succeeded on third attempt


@pytest.mark.asyncio
async def test_no_retry_on_4xx():
    """Client does NOT retry on 4xx (e.g. 409 Conflict is a business response)."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(409, json={"error": "duplicate"})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async with AegisClient(
        tenant_id="t1", thread_id="th1", client=mock_client, max_retries=3
    ) as client:
        response = await client.approve("key-backoff-2")

    assert response.status_code == 409
    assert call_count == 1  # no retry on 4xx
