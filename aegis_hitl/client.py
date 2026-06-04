import asyncio
import uuid
import httpx
from typing import Any


class AegisClient:
    """HTTP client for the AEGIS HITL Reliability Layer.

    Usage::

        async with AegisClient(
            base_url="http://localhost:8000",
            tenant_id="t1",
            thread_id="thr1",
        ) as client:
            response = await client.approve("idempotency-key-123")
            assert response.status_code == 202

    tenant_id and thread_id can be overridden per call.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        tenant_id: str | None = None,
        thread_id: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        api_prefix: str = "/api/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.thread_id = thread_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_prefix = api_prefix.rstrip("/")
        self._external_client = client
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AegisClient":
        self._client = self._external_client or httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._client and not self._external_client:
            await self._client.aclose()
        self._client = None
        return False

    def _resolve(self, tenant_id: str | None, thread_id: str | None) -> tuple[str, str]:
        t = tenant_id or self.tenant_id
        th = thread_id or self.thread_id
        if not t:
            raise ValueError("tenant_id is required (set on constructor or per call)")
        if not th:
            raise ValueError("thread_id is required (set on constructor or per call)")
        return t, th

    def _headers(
        self,
        tenant_id: str,
        thread_id: str,
        idempotency_key: str,
    ) -> dict[str, str]:
        return {
            "Tenant-Id": tenant_id,
            "Thread-Id": thread_id,
            "Idempotency-Key": idempotency_key,
            "X-Request-Id": str(uuid.uuid4()),
        }

    async def _post(
        self,
        path: str,
        idempotency_key: str,
        tenant_id: str | None,
        thread_id: str | None,
        payload: dict[str, Any] | None,
    ) -> httpx.Response:
        if not self._client:
            raise RuntimeError("AegisClient must be used as an async context manager.")
        t, th = self._resolve(tenant_id, thread_id)
        headers = self._headers(t, th, idempotency_key)
        delays = [0.5, 1.0, 2.0]
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            full_path = f"{self.api_prefix}{path}"
            response = await self._client.post(full_path, headers=headers, json=payload or {})
            if response.status_code < 500:
                return response
            last_response = response
            if attempt < self.max_retries:
                await asyncio.sleep(delays[min(attempt, len(delays) - 1)])
        return last_response  # type: ignore[return-value]

    async def approve(
        self,
        idempotency_key: str,
        *,
        tenant_id: str | None = None,
        thread_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """POST /hitl/approve. Returns raw httpx.Response (202 ok, 409 duplicate)."""
        return await self._post("/hitl/approve", idempotency_key, tenant_id, thread_id, payload)

    async def reject(
        self,
        idempotency_key: str,
        *,
        tenant_id: str | None = None,
        thread_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """POST /hitl/reject. Returns raw httpx.Response (202 ok, 409 duplicate)."""
        return await self._post("/hitl/reject", idempotency_key, tenant_id, thread_id, payload)

    async def execute(
        self,
        action: str,
        idempotency_key: str,
        *,
        tenant_id: str | None = None,
        thread_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Dispatch to approve or reject based on action string."""
        if action not in {"approve", "reject"}:
            raise ValueError(f"action must be 'approve' or 'reject', got {action!r}")
        return await self._post(
            f"/hitl/{action}", idempotency_key, tenant_id, thread_id, payload
        )

    async def get_status(self, request_id: str) -> httpx.Response:
        """GET /hitl/status/{request_id}."""
        if not self._client:
            raise RuntimeError("AegisClient must be used as an async context manager.")
        return await self._client.get(f"{self.api_prefix}/hitl/status/{request_id}")
