"""FastMCP middleware that emits one Call Record per tool call.

The whole surface of this library is emission. There is deliberately no
sampling, no Usage Signature computation, no Allowance checking and no
retention policy here: those change often and per-provider, while the record
format must not. A provider adopts telemetry by adding a dependency and calling
:func:`install_call_records` once.

**Emission is fire-and-forget.** The record is built after the tool has already
returned and handed to a background task that is never awaited. A sink that is
slow, erroring, or unreachable therefore cannot fail, delay, or alter a tool
call — which is safe precisely because ADR-0006 puts no decision on the request
path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from finsharpe_call_records.principal import Principal, principal_from_claims
from finsharpe_call_records.record import (
    CALL_RECORD_FORMAT_VERSION,
    CallRecord,
    Outcome,
)
from finsharpe_call_records.sink import CallRecordSink

logger = logging.getLogger("finsharpe.call_records")

#: Ceiling on undelivered records held in memory. Reached only when the sink is
#: down or wedged, at which point dropping is the correct behaviour — records
#: are evidence, not something a tool call is allowed to queue behind.
DEFAULT_MAX_IN_FLIGHT = 512


class CallRecordMiddleware(Middleware):
    """Emit a Call Record for every ``tools/call`` on this server."""

    def __init__(
        self,
        *,
        provider: str,
        sink: CallRecordSink,
        max_in_flight: int = DEFAULT_MAX_IN_FLIGHT,
    ) -> None:
        self.provider = provider
        self.sink = sink
        self.max_in_flight = max_in_flight
        self._in_flight: set[asyncio.Task[None]] = set()
        self._dropped = 0

    @property
    def dropped(self) -> int:
        """Records discarded because the sink could not keep up."""
        return self._dropped

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        started_at = datetime.now(UTC)
        clock = time.perf_counter()

        try:
            result = await call_next(context)
        except ToolError:
            # The caller was handed an error they can read and react to.
            self._emit(context, started_at, clock, Outcome.FAILED)
            raise
        except Exception:
            self._emit(context, started_at, clock, Outcome.ERROR)
            raise

        self._emit(context, started_at, clock, Outcome.SUCCESS)
        return result

    # -- emission ----------------------------------------------------------

    def _emit(
        self,
        context: MiddlewareContext,
        started_at: datetime,
        clock: float,
        outcome: Outcome,
    ) -> None:
        """Build and schedule a record. Never raises; never blocks."""
        try:
            record = self._build(context, started_at, clock, outcome)
        except Exception:
            logger.exception("Failed to build a Call Record; dropping it")
            return

        try:
            self._schedule(record)
        except RuntimeError:
            # No running loop (e.g. a synchronous stdio harness). Emission is
            # best-effort by design, so this is a debug note, not a failure.
            logger.debug("No running event loop; dropped a Call Record")

    def _build(
        self,
        context: MiddlewareContext,
        started_at: datetime,
        clock: float,
        outcome: Outcome,
    ) -> CallRecord:
        message = context.message
        arguments = getattr(message, "arguments", None)
        return CallRecord(
            format_version=CALL_RECORD_FORMAT_VERSION,
            occurred_at=started_at,
            provider=self.provider,
            tool_name=getattr(message, "name", "unknown"),
            arguments=dict(arguments) if arguments else {},
            duration_ms=(time.perf_counter() - clock) * 1000,
            outcome=outcome,
            **_principal_fields(_current_principal()),
        )

    def _schedule(self, record: CallRecord) -> None:
        if len(self._in_flight) >= self.max_in_flight:
            self._dropped += 1
            logger.warning(
                "Call Record sink backlog at %d; dropped %d record(s) so far",
                self.max_in_flight,
                self._dropped,
            )
            return
        task = asyncio.create_task(self._deliver(record))
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)

    async def _deliver(self, record: CallRecord) -> None:
        try:
            await self.sink.send(record)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Call Record for tool '%s' not delivered: %s", record.tool_name, exc
            )


def _current_principal() -> Principal:
    """Read the verified access token's claims, if this call carried one."""
    try:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
    except Exception:
        return Principal()
    if token is None:
        return Principal()
    return principal_from_claims(getattr(token, "claims", None))


def _principal_fields(principal: Principal) -> dict[str, Any]:
    return {
        "principal_id": principal.principal_id,
        "principal_type": principal.principal_type,
        "grant_id": principal.grant_id,
        "client_id": principal.client_id,
        "token_id": principal.token_id,
    }
