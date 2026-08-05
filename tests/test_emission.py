"""A tool call produces exactly one Call Record with the expected fields."""

from __future__ import annotations

import pytest

from finsharpe_call_records import CALL_RECORD_FORMAT_VERSION, Outcome, PrincipalType

from .conftest import drain


async def test_one_call_produces_exactly_one_record(client, sink):
    await client.call_tool("echo", {"symbol": "INFY", "limit": 3})
    await drain(sink)

    assert len(sink.records) == 1


async def test_record_carries_tool_name_arguments_duration_and_outcome(client, sink):
    await client.call_tool("echo", {"symbol": "INFY", "limit": 3})
    await drain(sink)

    record = sink.records[0]
    assert record.tool_name == "echo"
    assert record.arguments == {"symbol": "INFY", "limit": 3}
    assert record.outcome is Outcome.SUCCESS
    assert record.duration_ms >= 0
    assert record.provider == "testprovider"
    assert record.occurred_at is not None


async def test_every_record_carries_a_format_version(client, sink):
    await client.call_tool("echo", {"symbol": "INFY"})
    await drain(sink)

    assert sink.records[0].format_version == CALL_RECORD_FORMAT_VERSION
    assert "format_version" in sink.records[0].model_dump(mode="json")


async def test_a_failing_tool_still_produces_a_record(client, sink):
    with pytest.raises(Exception):
        await client.call_tool("explode", {"symbol": "INFY"})
    await drain(sink)

    assert len(sink.records) == 1
    assert sink.records[0].tool_name == "explode"
    assert sink.records[0].outcome is Outcome.FAILED


async def test_unattributed_call_defaults_to_grant_holder(client, sink):
    """No token on the call (auth off) — attribution is empty, type is not."""
    await client.call_tool("echo", {"symbol": "INFY"})
    await drain(sink)

    record = sink.records[0]
    assert record.principal_type is PrincipalType.GRANT_HOLDER
    assert record.principal_id is None
    assert record.grant_id is None
