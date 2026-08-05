"""Shared fixtures: a throwaway FastMCP server, an in-memory client, a fake sink.

Library behaviour is tested here rather than through a live provider — that is
the reason the library exists. Each provider keeps its own much thinner test
that its server has the middleware registered at all.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from finsharpe_call_records import CallRecord, install_call_records


class FakeSink:
    """Collects records in memory. Optionally broken, optionally wedged."""

    def __init__(
        self,
        *,
        raises: BaseException | None = None,
        hang_seconds: float | None = None,
    ) -> None:
        self.records: list[CallRecord] = []
        self.raises = raises
        self.hang_seconds = hang_seconds

    async def send(self, record: CallRecord) -> None:
        if self.hang_seconds is not None:
            await asyncio.sleep(self.hang_seconds)
        if self.raises is not None:
            raise self.raises
        self.records.append(record)


async def drain(sink: FakeSink, *, expected: int = 1, timeout: float = 2.0) -> None:
    """Wait for fire-and-forget delivery to land.

    Emission is deliberately not awaited by the tool call, so a test that
    asserts immediately after ``call_tool`` is racing the delivery task.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while len(sink.records) < expected:
        if asyncio.get_running_loop().time() > deadline:
            return
        await asyncio.sleep(0.01)


@pytest.fixture
def sink() -> FakeSink:
    return FakeSink()


def build_server(sink: Any, *, provider: str = "testprovider") -> FastMCP:
    """A one-tool server with the middleware registered."""
    mcp = FastMCP(provider)

    @mcp.tool
    def echo(symbol: str, limit: int = 5) -> str:
        """Echo a symbol back."""
        return f"{symbol}:{limit}"

    @mcp.tool
    def explode(symbol: str) -> str:
        """Always fails."""
        raise ValueError(f"no such symbol {symbol}")

    install_call_records(mcp, provider=provider, sink=sink)
    return mcp


@pytest.fixture
def server(sink: FakeSink) -> FastMCP:
    return build_server(sink)


@pytest.fixture
async def client(server: FastMCP):
    async with Client(server) as c:
        yield c
