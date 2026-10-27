from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyOverrides(BaseModel):
    """Public overrides may only tighten server policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    accept_risk_max: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    force_expensive: bool = False
    require_verifier: bool = False


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str = "heuristic-v1"
    accept_risk_max: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    force_expensive: bool = False
    enable_verifier: bool = True
    require_verifier: bool = False
    low_ocr_threshold: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    max_cheap_pages: int = Field(default=3, ge=1, le=1000)
    max_cheap_chars: int = Field(default=12000, ge=1, le=100000)
    fuzzy_name_threshold: float = Field(default=0.92, ge=0.85, le=1, allow_inf_nan=False)
    response_reserve_ms: int = Field(default=20, ge=1, le=1000)
    cheap_expected_ms: int = Field(default=80, ge=1)
    expensive_expected_ms: int = Field(default=250, ge=1)
    verifier_expected_ms: int = Field(default=40, ge=1)
    provider_timeout_ms: int = Field(default=1000, ge=1, le=60000)
    cheap_timeout_ms: int | None = Field(default=None, ge=1, le=60000)

    @model_validator(mode="after")
    def verifier_configuration(self) -> Self:
        if self.require_verifier and not self.enable_verifier:
            raise ValueError("Required verifier must be enabled")
        return self

    def with_overrides(self, overrides: PolicyOverrides | None) -> Self:
        if overrides is None:
            return self
        threshold = overrides.accept_risk_max
        if threshold is not None and threshold > self.accept_risk_max:
            raise ValueError("Request policy cannot relax server accept_risk_max")
        values = self.model_dump()
        if threshold is not None:
            values["accept_risk_max"] = threshold
        values["force_expensive"] = self.force_expensive or overrides.force_expensive
        values["require_verifier"] = self.require_verifier or overrides.require_verifier
        return self.model_validate(values)
