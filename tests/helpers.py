import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from assured_route.core.models import (
    ExtractRequest,
    Invoice,
    ProviderResult,
    VerificationResult,
)


@dataclass
class Extractor:
    payload: dict[str, object]
    estimated_cost_usd: Decimal = Decimal("0.0015")
    model_version: str = "test-extractor-v1"
    prompt_version: str = "test-prompt-v1"
    delay: float = 0
    calls: int = 0
    cancelled: bool = False
    error: Exception | None = None

    async def extract(
        self, request: ExtractRequest, *, timeout_ms: float | None = None
    ) -> ProviderResult:
        self.calls += 1
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.error:
            raise self.error
        return ProviderResult(payload=self.payload.copy(), model_version=self.model_version)


@dataclass
class Verifier:
    agrees: bool = True
    disputed_fields: list[str] = field(default_factory=list)
    estimated_cost_usd: Decimal = Decimal("0.0003")
    model_version: str = "test-verifier-v1"
    prompt_version: str = "test-verify-v1"
    calls: int = 0
    delay: float = 0

    async def verify(
        self, request: ExtractRequest, invoice: Invoice, *, timeout_ms: float | None = None
    ) -> VerificationResult:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return VerificationResult(
            agrees=self.agrees,
            disputed_fields=self.disputed_fields,
            model_version=self.model_version,
        )
