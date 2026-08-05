"""A broken sink must not fail, delay, or alter a tool call.

This is the guarantee Grant-Holders are owed: observation cannot reduce the
reliability of what they pay for. Per ADR-0006 no decision depends on a Call
Record, so there is never a reason for one to be on the critical path.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastmcp import Client

from finsharpe_call_records import HttpCallRecordSink

from .conftest import FakeSink, build_server


async def _call(sink) -> str:
    async with Client(build_server(sink)) as client:
        result = await client.call_tool("echo", {"symbol": "INFY", "limit": 3})
    return result.content[0].text


async def test_erroring_sink_does_not_fail_the_tool_call():
    sink = FakeSink(raises=RuntimeError("sink exploded"))
    assert await _call(sink) == "INFY:3"


async def test_hanging_sink_does_not_delay_the_tool_call():
    # Far longer than any tolerance below: if emission were awaited, the call
    # could not possibly return in time.
    sink = FakeSink(hang_seconds=30)

    started = time.perf_counter()
    assert await _call(sink) == "INFY:3"
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0


async def test_unreachable_sink_does_not_fail_the_tool_call():
    """A real HTTP sink pointed at a port nothing is listening on."""
    sink = HttpCallRecordSink(
        "http://127.0.0.1:9/call-records", api_key="k", timeout=0.25
    )
    try:
        assert await _call(sink) == "INFY:3"
        # Let the doomed delivery task finish so it is not garbage-collected
        # mid-flight and reported as a pending-task warning.
        await asyncio.sleep(0.5)
    finally:
        await sink.aclose()


async def test_sink_that_returns_an_error_status_does_not_fail_the_tool_call():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "nope"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        sink = HttpCallRecordSink("http://sink.test/call-records", client=http)
        assert await _call(sink) == "INFY:3"
        await asyncio.sleep(0.1)


async def test_backlog_is_dropped_rather_than_queued_without_bound():
    """When the sink is wedged, records are discarded, not accumulated forever."""
    from finsharpe_call_records import CallRecordMiddleware

    middleware = CallRecordMiddleware(
        provider="testprovider", sink=FakeSink(hang_seconds=30), max_in_flight=2
    )

    from fastmcp import FastMCP

    mcp = FastMCP("testprovider")

    @mcp.tool
    def echo(symbol: str) -> str:
        """Echo."""
        return symbol

    mcp.add_middleware(middleware)

    async with Client(mcp) as client:
        for _ in range(5):
            await client.call_tool("echo", {"symbol": "INFY"})

    assert middleware.dropped >= 1


async def test_error_outcome_is_recorded_for_a_non_tool_exception():
    """Anything that is not a ToolError is recorded as ``error``, then re-raised."""
    from finsharpe_call_records import CallRecordMiddleware
    from finsharpe_call_records.record import Outcome

    sink = FakeSink()
    middleware = CallRecordMiddleware(provider="testprovider", sink=sink)

    class _Message:
        name = "echo"
        arguments = {"symbol": "INFY"}

    class _Context:
        message = _Message()

    async def call_next(_context):
        raise RuntimeError("infrastructure broke")

    with pytest.raises(RuntimeError):
        await middleware.on_call_tool(_Context(), call_next)

    await asyncio.sleep(0.05)
    assert [r.outcome for r in sink.records] == [Outcome.ERROR]
