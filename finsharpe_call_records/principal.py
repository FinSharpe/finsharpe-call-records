"""Read the calling principal out of already-verified JWT claims.

The provider's ``JWTVerifier`` has run by the time middleware sees a tool call,
so this parses nothing and validates nothing — it reads the claims that
verification already established.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from finsharpe_call_records.record import PrincipalType

#: Claim naming the principal type. Set by the Authorization Server when it
#: mints the token; absent on tokens minted before this claim existed.
PRINCIPAL_TYPE_CLAIM = "principal_type"


@dataclass(frozen=True, slots=True)
class Principal:
    """The attribution half of a Call Record."""

    principal_id: str | None = None
    principal_type: PrincipalType = PrincipalType.GRANT_HOLDER
    grant_id: str | None = None
    client_id: str | None = None
    token_id: str | None = None


def _text(claims: Mapping[str, Any], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


def principal_from_claims(claims: Mapping[str, Any] | None) -> Principal:
    """Build a :class:`Principal` from JWT claims.

    An unrecognised or absent ``principal_type`` falls back to
    ``GRANT_HOLDER``. That is the safe default: the Service Identity's tokens
    are minted by code we control and always carry the claim, so the fallback
    only ever applies to real user traffic. Guessing the other way would let a
    misconfigured provider quietly excuse a heavy caller from every view.
    """
    if not claims:
        return Principal()

    raw_type = _text(claims, PRINCIPAL_TYPE_CLAIM)
    try:
        principal_type = PrincipalType(raw_type) if raw_type else PrincipalType.GRANT_HOLDER
    except ValueError:
        principal_type = PrincipalType.GRANT_HOLDER

    return Principal(
        principal_id=_text(claims, "sub"),
        principal_type=principal_type,
        grant_id=_text(claims, "grant_id"),
        client_id=_text(claims, "client_id"),
        token_id=_text(claims, "jti"),
    )
