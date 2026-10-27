import re
from decimal import Decimal
from typing import Literal, Self
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from assured_route.core.policy import Policy


class ModelAPIConfig(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    model: str
    api_key: SecretStr = Field(repr=False)
    base_url: str
    response_format: Literal["json_object", "none"] = "json_object"
    token_limit_parameter: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"
    max_output_tokens: int = 1024
    max_response_bytes: int = 262144


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AR_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    provider_mode: Literal["mock", "openai_compatible"] = "mock"
    cheap_model: str = ""
    cheap_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    cheap_base_url: str = "https://api.openai.com/v1"
    expensive_model: str = ""
    expensive_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    expensive_base_url: str = "https://api.openai.com/v1"
    cheap_response_format: Literal["json_object", "none"] = "json_object"
    expensive_response_format: Literal["json_object", "none"] = "json_object"
    cheap_token_limit_parameter: Literal["max_completion_tokens", "max_tokens"] = (
        "max_completion_tokens"
    )
    expensive_token_limit_parameter: Literal["max_completion_tokens", "max_tokens"] = (
        "max_completion_tokens"
    )
    llm_max_output_tokens: int = Field(default=1024, ge=64, le=32768)
    llm_max_response_bytes: int = Field(default=262144, ge=4096, le=4194304)
    policy: Policy = Field(default_factory=Policy)
    cheap_cost_usd: Decimal = Field(default=Decimal("0.0015"), ge=0, allow_inf_nan=False)
    expensive_cost_usd: Decimal = Field(default=Decimal("0.015"), ge=0, allow_inf_nan=False)
    verifier_cost_usd: Decimal = Field(default=Decimal("0.0003"), ge=0, allow_inf_nan=False)
    mock_cheap_delay_ms: int = Field(default=10, ge=0, le=60000)
    mock_expensive_delay_ms: int = Field(default=30, ge=0, le=60000)
    mock_verifier_delay_ms: int = Field(default=5, ge=0, le=60000)
    log_level: str = "INFO"

    @field_validator("cheap_base_url", "expensive_base_url")
    @classmethod
    def safe_base_url(cls, value: str) -> str:
        try:
            if re.search(r"[\x00-\x20\x7f]", value):
                raise ValueError("Control character or whitespace in URL")
            httpx.URL(value)
            parts = urlsplit(value)
            if parts.port is not None and not 1 <= parts.port <= 65535:
                raise ValueError("Invalid URL port")
        except (ValueError, httpx.InvalidURL):
            raise ValueError("Invalid model base URL") from None
        if (
            not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.scheme not in {"http", "https"}
        ):
            raise ValueError(
                "Base URL must be an HTTP(S) URL without credentials, query or fragment"
            )
        if parts.scheme == "http" and parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "Remote model endpoints require HTTPS; HTTP is allowed on loopback only"
            )
        return value.rstrip("/")

    @model_validator(mode="after")
    def complete_live_configuration(self) -> Self:
        if self.provider_mode == "openai_compatible":
            for role in ("cheap", "expensive"):
                name: str = getattr(self, f"{role}_model")
                key: SecretStr = getattr(self, f"{role}_api_key")
                if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,200}", name):
                    raise ValueError(f"Set AR_{role.upper()}_MODEL to the provider model ID")
                if not key.get_secret_value().strip():
                    raise ValueError(f"Set AR_{role.upper()}_API_KEY for live mode")
                if not re.fullmatch(r"[\x21-\x7e]+", key.get_secret_value()):
                    raise ValueError(
                        f"AR_{role.upper()}_API_KEY must be a header-safe ASCII credential"
                    )
        return self

    def model_api(self, role: Literal["cheap", "expensive"]) -> ModelAPIConfig:
        return ModelAPIConfig(
            model=getattr(self, f"{role}_model"),
            api_key=getattr(self, f"{role}_api_key"),
            base_url=getattr(self, f"{role}_base_url"),
            response_format=getattr(self, f"{role}_response_format"),
            token_limit_parameter=getattr(self, f"{role}_token_limit_parameter"),
            max_output_tokens=self.llm_max_output_tokens,
            max_response_bytes=self.llm_max_response_bytes,
        )
