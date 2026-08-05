"""The Call Record wire contract.

This module is the shared artifact of the whole telemetry effort. Providers
deploy independently, so several versions of this library are always live at
once and the sink must accept records produced by any of them. Three rules keep
that workable:

* every record carries ``format_version`` explicitly;
* new fields are **additive** — a reader that does not know a field ignores it
  rather than rejecting the record;
* a field is never repurposed. Retiring one means adding its replacement and
  leaving the old one populated until every provider has moved.

Changing this contract is the expensive part of the system. Changing anything
else in this library is cheap.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: Bumped only when the meaning of an existing field changes. Adding a field is
#: additive and does not bump it.
CALL_RECORD_FORMAT_VERSION = 1


# `str, Enum` rather than `StrEnum`: this library has to install into every
# provider, and StrEnum is 3.11+. The two behave identically for what is done
# with them here — comparison by value and Pydantic JSON serialisation.
class PrincipalType(str, Enum):
    """Who a Call Record is attributed to.

    Recorded explicitly rather than inferred. Orchestrator Access reaches
    providers under the Service Identity and is metered upstream as Credits;
    without this field a later analysis would read that traffic as one
    impossibly heavy Grant-Holder.
    """

    GRANT_HOLDER = "grant_holder"
    SERVICE_IDENTITY = "service_identity"


class Outcome(str, Enum):
    """How a tool call ended.

    ``FAILED`` is a tool-level error the caller was told about (FastMCP's
    ``ToolError``); ``ERROR`` is an unhandled exception. The distinction is what
    separates a caller probing the surface from one using it.
    """

    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


class CallRecord(BaseModel):
    """One observation of a single tool invocation at a provider.

    ``extra="allow"`` is deliberate and load-bearing in both directions: a newer
    emitter may add fields this version has never heard of, and they must
    survive the round trip rather than being dropped on the floor.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    format_version: int = CALL_RECORD_FORMAT_VERSION

    occurred_at: datetime
    """When the call started, UTC."""

    principal_id: str | None = None
    """The ``sub`` claim — a Grant-Holder's user id, or the Service Identity's."""

    principal_type: PrincipalType = PrincipalType.GRANT_HOLDER

    grant_id: str | None = None
    client_id: str | None = None

    token_id: str | None = None
    """The access token's ``jti``, so a record ties back to one device row."""

    provider: str
    """Which MCP served the call — ``tradekit``, ``filings``, ``quant``, ..."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    duration_ms: float
    outcome: Outcome
