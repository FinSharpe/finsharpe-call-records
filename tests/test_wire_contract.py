"""The record format is the shared artifact; unknown fields are additive.

Providers deploy independently, so several library versions are always live at
once. A record from a newer emitter must survive a round trip through an older
reader, and vice versa.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from finsharpe_call_records import (
    API_KEY_HEADER,
    CALL_RECORD_FORMAT_VERSION,
    CallRecord,
    HttpCallRecordSink,
    Outcome,
    PrincipalType,
)


def _record(**overrides) -> CallRecord:
    base = dict(
        occurred_at=datetime.now(UTC),
        principal_id="user_1",
        principal_type=PrincipalType.GRANT_HOLDER,
        grant_id="grant_1",
        client_id="Claude",
        token_id="jti_1",
        provider="tradekit",
        tool_name="scan",
        arguments={"symbol": "INFY"},
        duration_ms=12.5,
        outcome=Outcome.SUCCESS,
    )
    base.update(overrides)
    return CallRecord(**base)


def test_an_unknown_field_survives_the_round_trip():
    """A field a future emitter adds is carried, not dropped."""
    record = CallRecord.model_validate(
        {**_record().model_dump(mode="json"), "result_bytes": 4096}
    )
    assert record.model_dump(mode="json")["result_bytes"] == 4096


def test_a_record_from_an_older_emitter_still_parses():
    """Only the fields that existed at format version 1 are required."""
    record = CallRecord.model_validate(
        {
            "format_version": 1,
            "occurred_at": "2026-08-05T10:00:00Z",
            "provider": "tradekit",
            "tool_name": "scan",
            "duration_ms": 1.0,
            "outcome": "success",
        }
    )
    assert record.principal_type is PrincipalType.GRANT_HOLDER
    assert record.arguments == {}


def test_the_serialised_payload_names_its_format_version():
    assert _record().model_dump(mode="json")["format_version"] == (
        CALL_RECORD_FORMAT_VERSION
    )


async def test_http_sink_posts_the_record_with_the_ingest_key():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = request.read().decode()
        return httpx.Response(202)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sink = HttpCallRecordSink(
            "http://sink.test/api/call-records", api_key="secret", client=http
        )
        await sink.send(_record())

    assert seen["headers"][API_KEY_HEADER] == "secret"
    assert '"tool_name":"scan"' in seen["body"].replace(" ", "")


@pytest.mark.parametrize("outcome", list(Outcome))
def test_every_outcome_serialises_as_a_plain_string(outcome):
    assert _record(outcome=outcome).model_dump(mode="json")["outcome"] == outcome.value
