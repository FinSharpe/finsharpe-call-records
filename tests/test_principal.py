"""Principal type is recorded, never inferred.

Orchestrator Access reaches providers under the Service Identity and is metered
upstream as Credits. A record that does not say so would read, later, as one
impossibly heavy Grant-Holder.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp.server.auth.auth import AccessToken

from finsharpe_call_records import PrincipalType, principal_from_claims

from .conftest import drain


@pytest.fixture
def as_principal(monkeypatch):
    """Make every call in the test look like it carried a given set of claims.

    Substitutes a real ``AccessToken`` rather than a stand-in, because FastMCP
    itself reads this token for things unrelated to telemetry.
    """
    import fastmcp.server.dependencies as deps

    def _apply(claims: dict[str, Any] | None):
        token = (
            AccessToken(
                token="verified-elsewhere",
                client_id=claims.get("client_id", ""),
                scopes=["tradekit:use"],
                claims=claims,
            )
            if claims is not None
            else None
        )
        monkeypatch.setattr(deps, "get_access_token", lambda: token)

    return _apply


GRANT_HOLDER_CLAIMS = {
    "sub": "user_0007",
    "principal_type": "grant_holder",
    "grant_id": "grant_abc",
    "client_id": "Claude",
    "jti": "jti_123",
}

SERVICE_CLAIMS = {
    "sub": "orchestrator-service",
    "principal_type": "service_identity",
    "grant_id": "service",
    "client_id": "orchestrator",
    "jti": "jti_456",
}


async def test_grant_holder_call_is_attributed_to_their_grant(
    client, sink, as_principal
):
    as_principal(GRANT_HOLDER_CLAIMS)

    await client.call_tool("echo", {"symbol": "INFY"})
    await drain(sink)

    record = sink.records[0]
    assert record.principal_type is PrincipalType.GRANT_HOLDER
    assert record.principal_id == "user_0007"
    assert record.grant_id == "grant_abc"
    assert record.client_id == "Claude"
    assert record.token_id == "jti_123"


async def test_service_identity_call_is_marked_as_such(client, sink, as_principal):
    as_principal(SERVICE_CLAIMS)

    await client.call_tool("echo", {"symbol": "INFY"})
    await drain(sink)

    record = sink.records[0]
    assert record.principal_type is PrincipalType.SERVICE_IDENTITY
    assert record.principal_id == "orchestrator-service"


def test_absent_principal_type_claim_falls_back_to_grant_holder():
    """A token minted before the claim existed is still real user traffic."""
    principal = principal_from_claims({"sub": "user_1", "grant_id": "g1"})
    assert principal.principal_type is PrincipalType.GRANT_HOLDER


def test_unrecognised_principal_type_falls_back_to_grant_holder():
    principal = principal_from_claims({"sub": "user_1", "principal_type": "wat"})
    assert principal.principal_type is PrincipalType.GRANT_HOLDER
