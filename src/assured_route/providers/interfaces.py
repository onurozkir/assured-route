from decimal import Decimal
from typing import Literal, Protocol

from assured_route.core.models import ExtractRequest, Invoice, ProviderResult, VerificationResult

type ProviderErrorCode = Literal[
    "provider_error",
    "provider_timeout",
    "network_error",
    "upstream_auth_error",
    "rate_limited",
    "upstream_server_error",
    "upstream_client_error",
    "invalid_response",
    "invalid_json",
    "model_refusal",
    "truncated_output",
    "empty_output",
    "response_too_large",
    "invalid_verifier_output",
]


class ProviderError(Exception):
    """Adapter boundary for expected network, rate limit, and malformed-output errors."""

    def __init__(
        self,
        message: str = "Provider request failed",
        *,
        code: ProviderErrorCode = "provider_error",
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class ProviderMetadata(Protocol):
    @property
    def model_version(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    @property
    def estimated_cost_usd(self) -> Decimal: ...


class ExtractionProvider(ProviderMetadata, Protocol):
    async def extract(
        self, request: ExtractRequest, *, timeout_ms: float | None = None
    ) -> ProviderResult: ...


class VerifierProvider(ProviderMetadata, Protocol):
    async def verify(
        self, request: ExtractRequest, invoice: Invoice, *, timeout_ms: float | None = None
    ) -> VerificationResult: ...


# TODO: Add actual token-usage billing; fixed per-call costs remain scenario estimates.
