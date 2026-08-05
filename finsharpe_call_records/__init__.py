"""Call Record emission for FinSharpe MCP providers.

Emission and nothing else. Sampling, Usage Signature computation, Allowance
checking and retention all live elsewhere, on purpose: they change often and
per-provider, and every one of them added here would turn a provider upgrade
into a coordinated release across all of them.
"""

from finsharpe_call_records.install import (
    find_call_record_middleware,
    install_call_records,
    sink_from_env,
)
from finsharpe_call_records.middleware import CallRecordMiddleware
from finsharpe_call_records.principal import (
    PRINCIPAL_TYPE_CLAIM,
    Principal,
    principal_from_claims,
)
from finsharpe_call_records.record import (
    CALL_RECORD_FORMAT_VERSION,
    CallRecord,
    Outcome,
    PrincipalType,
)
from finsharpe_call_records.sink import (
    API_KEY_HEADER,
    CallRecordSink,
    HttpCallRecordSink,
    NullSink,
)

__all__ = [
    "API_KEY_HEADER",
    "CALL_RECORD_FORMAT_VERSION",
    "PRINCIPAL_TYPE_CLAIM",
    "CallRecord",
    "CallRecordMiddleware",
    "CallRecordSink",
    "HttpCallRecordSink",
    "NullSink",
    "Outcome",
    "Principal",
    "PrincipalType",
    "find_call_record_middleware",
    "install_call_records",
    "principal_from_claims",
    "sink_from_env",
]

__version__ = "0.1.0"
