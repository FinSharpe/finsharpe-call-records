"""Where Call Records go.

A sink's ``send`` is allowed to be slow, to raise, and to hang. Nothing here
guarantees otherwise — the fire-and-forget guarantee lives in the middleware,
which never awaits a send on the tool-call path. Keeping the guarantee there
rather than here means a sink implementation cannot accidentally break it.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx

from finsharpe_call_records.record import CallRecord

#: Header carrying the shared ingest secret. The sink endpoint is not a public
#: API; without this anyone could forge records against a Grant-Holder.
API_KEY_HEADER = "X-Call-Record-Key"

DEFAULT_TIMEOUT_SECONDS = 2.0


@runtime_checkable
class CallRecordSink(Protocol):
    """Anything that can accept a Call Record."""

    async def send(self, record: CallRecord) -> None: ...


class NullSink:
    """Discards records. What a provider gets when no sink URL is configured.

    Installed rather than skipping the middleware entirely, so that "is the
    middleware registered?" stays a question about the server and not about the
    environment it happens to be booted in.
    """

    async def send(self, record: CallRecord) -> None:  # noqa: ARG002
        return None


class HttpCallRecordSink:
    """POSTs one record per call to the sink's ingest endpoint."""

    def __init__(
        self,
        url: str,
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers[API_KEY_HEADER] = api_key
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def send(self, record: CallRecord) -> None:
        payload: dict[str, Any] = record.model_dump(mode="json")
        response = await self._get_client().post(
            self._url, json=payload, headers=self._headers, timeout=self._timeout
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
