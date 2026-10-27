import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from assured_route.core.decisions import Decision, SelectedPath
from assured_route.core.policy import Policy, PolicyOverrides


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Invoice(Contract):
    document_type: Literal["invoice"]
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    invoice_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)
    vat_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)
    seller_name: str = Field(min_length=1, max_length=300)
    seller_tax_id: str = Field(min_length=1, max_length=32)
    buyer_name: str = Field(min_length=1, max_length=300)

    @field_validator("invoice_date", "due_date", mode="before")
    @classmethod
    def iso_date_only(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Date must be an ISO-8601 calendar date: YYYY-MM-DD")
        return value

    @field_validator("invoice_total", "vat_total", mode="before")
    @classmethod
    def numeric_not_boolean(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
            raise ValueError("Amount must be numeric")
        return value

    @field_validator("invoice_number", "seller_name", "buyer_name", "seller_tax_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field must not be blank")
        return value.strip()


class DocumentMetadata(Contract):
    page_count: int = Field(default=1, ge=1, le=1000)
    ocr_quality: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    known_template: bool = True
    high_risk: bool = False
    semantic_ambiguity: bool = False


class ExtractRequest(Contract):
    raw_ocr_text: str = Field(min_length=1, max_length=100000)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    latency_budget_ms: int = Field(default=1500, ge=1, le=60000)
    policy: PolicyOverrides | None = None

    @field_validator("raw_ocr_text")
    @classmethod
    def nonblank_source(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OCR text must not be blank")
        return value


class ValidationCheck(Contract):
    validator: Literal["schema", "grounding", "business_rules", "verifier", "runtime"]
    code: str
    passed: bool
    field: str | None = None
    severity: Literal["info", "warning", "error", "fatal"] = "info"
    recoverable: bool = True

    @field_validator("field", mode="before")
    @classmethod
    def known_field_only(cls, value: object) -> str | None:
        # Model-generated keys/disputed fields are untrusted and may contain source data.
        return value if isinstance(value, str) and value in Invoice.model_fields else None


class ValidationReport(Contract):
    checks: list[ValidationCheck] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


class RiskAssessment(Contract):
    score: float = Field(ge=0, le=1)
    fields: dict[str, float] = Field(default_factory=dict)
    basis: Literal["heuristic_not_probability"] = "heuristic_not_probability"


class VerificationResult(Contract):
    agrees: bool
    disputed_fields: list[str] = Field(default_factory=list)
    model_version: str


class GateResult(Contract):
    invoice: Invoice | None
    decision: Decision
    report: ValidationReport
    risk: RiskAssessment
    needs_verifier: bool = False


class ProviderResult(Contract):
    payload: dict[str, object]
    model_version: str
    prompt_version: str = "invoice-v1"


class CallRecord(Contract):
    role: Literal["cheap", "expensive", "verifier"]
    model_version: str
    prompt_version: str
    status: Literal["ok", "timeout", "error", "cancelled"]
    latency_ms: float
    estimated_cost_usd: Decimal
    error_code: str | None = None
    http_status: int | None = None


class AuditEvent(Contract):
    stage: str
    reason: str
    elapsed_ms: float
    decision: Decision | None = None


class ValidationAttempt(Contract):
    role: Literal["cheap", "expensive"]
    report: ValidationReport
    decision: Decision
    risk_score: float


class AuditInfo(Contract):
    request_id: str
    document_sha256: str
    policy_sha256: str
    policy: Policy
    started_at: datetime
    versions: dict[str, str]
    events: list[AuditEvent]
    calls: list[CallRecord]
    validation_attempts: list[ValidationAttempt]


class LatencyBreakdown(Contract):
    total_ms: float
    budget_ms: int
    stages_ms: dict[str, float]
    deadline_exceeded: bool


class ExtractResponse(Contract):
    extracted_data: Invoice | None
    decision: Decision
    selected_path: SelectedPath
    validation_report: ValidationReport
    estimated_risk_score: float
    field_risk_scores: dict[str, float]
    risk_basis: Literal["heuristic_not_probability"] = "heuristic_not_probability"
    estimated_cost: Decimal
    cost_currency: Literal["USD"] = "USD"
    latency_breakdown: LatencyBreakdown
    audit: AuditInfo
