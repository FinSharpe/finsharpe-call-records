"""One-call registration for providers.

A provider adopts Call Records by importing this and calling it on its
module-level FastMCP server::

    from finsharpe_call_records import install_call_records

    mcp = FastMCP("tradekit", ...)
    install_call_records(mcp, provider="tradekit")

Configuration is read from the environment so that adding a provider is a code
change in one place and a deployment change in another.
"""

from __future__ import annotations

import logging
import os

from finsharpe_call_records.middleware import (
    DEFAULT_MAX_IN_FLIGHT,
    CallRecordMiddleware,
)
from finsharpe_call_records.sink import (
    DEFAULT_TIMEOUT_SECONDS,
    CallRecordSink,
    HttpCallRecordSink,
    NullSink,
)

logger = logging.getLogger("finsharpe.call_records")

SINK_URL_ENV = "CALL_RECORDS_SINK_URL"
API_KEY_ENV = "CALL_RECORDS_API_KEY"
TIMEOUT_ENV = "CALL_RECORDS_TIMEOUT_SECONDS"
MAX_IN_FLIGHT_ENV = "CALL_RECORDS_MAX_IN_FLIGHT"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def sink_from_env() -> CallRecordSink:
    """Build the configured sink, or a :class:`NullSink` if none is set."""
    url = os.environ.get(SINK_URL_ENV, "").strip()
    if not url:
        logger.info("%s unset; Call Records will be built and discarded", SINK_URL_ENV)
        return NullSink()
    return HttpCallRecordSink(
        url,
        api_key=os.environ.get(API_KEY_ENV) or None,
        timeout=_float_env(TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS),
    )


def install_call_records(
    server,
    *,
    provider: str,
    sink: CallRecordSink | None = None,
) -> CallRecordMiddleware:
    """Register :class:`CallRecordMiddleware` on ``server`` and return it.

    Registration is unconditional. A provider with no sink configured still
    carries the middleware and emits into a :class:`NullSink`, so "does this
    server emit?" is a property of the server rather than of the environment it
    was booted in — which is what makes a provider's registration test worth
    having.
    """
    middleware = CallRecordMiddleware(
        provider=provider,
        sink=sink if sink is not None else sink_from_env(),
        max_in_flight=_int_env(MAX_IN_FLIGHT_ENV, DEFAULT_MAX_IN_FLIGHT),
    )
    server.add_middleware(middleware)
    logger.info("Call Record emission registered for provider '%s'", provider)
    return middleware


def find_call_record_middleware(server) -> CallRecordMiddleware | None:
    """Return the server's Call Record middleware, if it has one.

    Exists for each provider's own registration test: a provider that installed
    the library but never registered the middleware emits nothing and is
    otherwise indistinguishable from a provider with no traffic.
    """
    for middleware in getattr(server, "middleware", []):
        if isinstance(middleware, CallRecordMiddleware):
            return middleware
    return None
