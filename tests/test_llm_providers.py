import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from assured_route.config import Settings
from assured_route.core.decisions import Decision
from assured_route.core.models import ExtractRequest
from assured_route.core.policy import Policy
from assured_route.dependencies import build_router


def live_settings(**overrides):
    values = {
        "provider_mode": "openai_compatible",
        "cheap_model": "cheap-v1",
        "cheap_api_key": "cheap-secret",
        "cheap_base_url": "https://cheap.example/v1",
        "expensive_model": "expensive-v1",
        "expensive_api_key": "expensive-secret",
        "expensive_base_url": "https://expensive.example/v1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def completion(payload, *, finish_reason="stop", refusal=None):
    return {
        "model": "snapshot-v1",
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"content": json.dumps(payload), "refusal": refusal},
            }
        ],
    }


def execute(handler, source, settings=None, **request_options):
    async def send():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            router = build_router(settings or live_settings(), http_client=client)
            return await router.extract(ExtractRequest(raw_ocr_text=source, **request_options))

    return asyncio.run(send())


def test_live_mode_requires_two_models_and_secrets():
    with pytest.raises(ValidationError, match="AR_CHEAP_MODEL"):
        Settings(_env_file=None, provider_mode="openai_compatible")


def test_env_accepts_two_separate_models_keys_and_urls(monkeypatch):
    for name, value in {
        "AR_PROVIDER_MODE": "openai_compatible",
        "AR_CHEAP_MODEL": "cheap-v1",
        "AR_CHEAP_API_KEY": "one-secret",
        "AR_CHEAP_BASE_URL": "https://cheap.example/v1",
        "AR_EXPENSIVE_MODEL": "large-v1",
        "AR_EXPENSIVE_API_KEY": "two-secret",
        "AR_EXPENSIVE_BASE_URL": "https://large.example/v1",
    }.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    assert settings.cheap_model == "cheap-v1"
    assert settings.expensive_model == "large-v1"
    assert settings.cheap_api_key.get_secret_value() == "one-secret"
    assert settings.expensive_api_key.get_secret_value() == "two-secret"
    assert "one-secret" not in repr(settings)
    assert "two-secret" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@api.example/v1",
        "https://api.example/v1?key=secret",
        "http://remote.example/v1",
        "https://api.example/v1#fragment",
    ],
)
def test_unsafe_base_urls_rejected(url):
    with pytest.raises(ValidationError):
        live_settings(cheap_base_url=url)


def test_good_cheap_response_never_calls_expensive(invoice, source):
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(request.url.host)
        assert str(request.url) == "https://cheap.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer cheap-secret"
        assert body["model"] == "cheap-v1"
        assert body["response_format"] == {"type": "json_object"}
        assert body["max_completion_tokens"] == 1024
        assert source in body["messages"][1]["content"]
        return httpx.Response(200, json=completion(invoice))

    result = execute(handle, source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == "cheap"
    assert calls == ["cheap.example"]
    assert result.audit.calls[0].model_version == "snapshot-v1"


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "upstream_auth_error"),
        (403, "upstream_auth_error"),
        (429, "rate_limited"),
        (500, "upstream_server_error"),
        (503, "upstream_server_error"),
    ],
)
def test_http_failures_escalate_once_with_safe_audit(invoice, source, status, reason):
    calls = []

    def handle(request):
        calls.append(request.url.host)
        if request.url.host == "cheap.example":
            return httpx.Response(status, text="secret OCR and cheap-secret")
        assert request.headers["authorization"] == "Bearer expensive-secret"
        assert json.loads(request.content)["model"] == "expensive-v1"
        return httpx.Response(200, json=completion(invoice))

    result = execute(handle, source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == "expensive"
    assert calls == ["cheap.example", "expensive.example"]
    assert result.audit.calls[0].error_code == reason
    assert result.audit.calls[0].http_status == status
    assert "secret" not in result.audit.model_dump_json()


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("invalid_json", "invalid_json"),
        ("refusal", "model_refusal"),
        ("truncated", "truncated_output"),
        ("empty", "empty_output"),
        ("array", "invalid_response"),
        ("html", "invalid_response"),
    ],
)
def test_unusable_outputs_escalate(invoice, source, kind, reason):
    def handle(request):
        if request.url.host == "expensive.example":
            return httpx.Response(200, json=completion(invoice))
        if kind == "html":
            return httpx.Response(200, text="<html>proxy failure</html>")
        body = completion(invoice)
        message = body["choices"][0]["message"]
        if kind == "invalid_json":
            message["content"] = "not JSON"
        elif kind == "refusal":
            message["refusal"] = "Cannot process document"
        elif kind == "truncated":
            body["choices"][0]["finish_reason"] = "length"
        elif kind == "empty":
            message["content"] = None
        elif kind == "array":
            message["content"] = "[]"
        return httpx.Response(200, json=body)

    result = execute(handle, source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == "expensive"
    assert result.audit.calls[0].error_code == reason


def test_schema_failure_from_http_response_escalates(invoice, source):
    def handle(request):
        payload = (
            invoice if request.url.host == "expensive.example" else {"document_type": "invoice"}
        )
        return httpx.Response(200, json=completion(payload))

    result = execute(handle, source)
    assert result.selected_path == "expensive"
    assert result.audit.validation_attempts[0].decision == Decision.ESCALATE_TO_EXPENSIVE


def test_bad_expensive_response_never_returns_unverified_data(invoice, source):
    result = execute(
        lambda request: httpx.Response(200, json=completion({"currency": "USD"})), source
    )
    assert result.decision == Decision.REVIEW
    assert result.extracted_data is None
    assert len(result.audit.calls) == 2


def test_transport_timeout_is_a_timeout_not_a_programming_error(invoice, source):
    def handle(request):
        if request.url.host == "cheap.example":
            raise httpx.ReadTimeout("secret provider URL", request=request)
        return httpx.Response(200, json=completion(invoice))

    result = execute(handle, source)
    assert result.selected_path == "expensive"
    assert result.audit.calls[0].status == "timeout"
    assert result.audit.calls[0].error_code == "provider_timeout"


def test_oversized_response_is_rejected_before_parsing(invoice, source):
    def handle(request):
        if request.url.host == "cheap.example":
            return httpx.Response(200, content=b" " * 5000)
        return httpx.Response(200, json=completion(invoice))

    result = execute(handle, source, live_settings(llm_max_response_bytes=4096))
    assert result.selected_path == "expensive"
    assert result.audit.calls[0].error_code == "response_too_large"


def test_required_verifier_uses_configured_expensive_api(invoice, source):
    models = []

    def handle(request):
        body = json.loads(request.content)
        models.append(body["model"])
        payload = {"agrees": True, "disputed_fields": []} if len(models) == 2 else invoice
        return httpx.Response(200, json=completion(payload))

    result = execute(handle, source, metadata={"semantic_ambiguity": True})
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == "cheap+verifier"
    assert models == ["cheap-v1", "expensive-v1"]
    assert str(result.estimated_cost) == "0.0165"


def test_prompt_only_mode_and_legacy_token_parameter(invoice, source):
    def handle(request):
        body = json.loads(request.content)
        assert "response_format" not in body
        assert "max_completion_tokens" not in body
        assert body["max_tokens"] == 1024
        return httpx.Response(200, json=completion(invoice))

    result = execute(
        handle,
        source,
        live_settings(cheap_response_format="none", cheap_token_limit_parameter="max_tokens"),
    )
    assert result.decision == Decision.ACCEPT


def test_http_client_gets_router_remaining_timeout(invoice, source):
    seen = []

    def handle(request):
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json=completion(invoice))

    result = execute(
        handle, source, live_settings(policy=Policy(cheap_timeout_ms=40)), latency_budget_ms=1500
    )
    assert result.decision == Decision.ACCEPT
    assert 0 < seen[0]["read"] <= 0.04


def test_numeric_json_preserves_money_precision(invoice, source):
    amount = "1234567890123456.78"
    source = source.replace("invoice_total: 1200.00", "invoice_total: " + amount)

    def handle(request):
        body = completion(invoice)
        body["choices"][0]["message"]["content"] = json.dumps(invoice).replace(
            '"invoice_total": "1200.00"', '"invoice_total": ' + amount
        )
        return httpx.Response(200, json=body)

    result = execute(handle, source)
    assert result.decision == Decision.ACCEPT
    assert str(result.extracted_data.invoice_total) == amount


@pytest.mark.parametrize(
    "verdict",
    [
        {"agrees": "true", "disputed_fields": []},
        {"agrees": True, "disputed_fields": ["seller_name"]},
        {"agrees": True, "disputed_fields": ["SECRET source text"]},
        {"agrees": True},
    ],
)
def test_malformed_verifier_output_cannot_authorize_acceptance(invoice, source, verdict):
    def handle(request):
        payload = invoice if request.url.host == "cheap.example" else verdict
        return httpx.Response(200, json=completion(payload))

    result = execute(handle, source, metadata={"semantic_ambiguity": True})
    assert result.decision == Decision.REVIEW
    assert result.extracted_data is None
    assert result.audit.calls[1].error_code == "invalid_verifier_output"


def test_application_lifespan_closes_owned_provider_pool():
    from assured_route.api import create_app

    async def check():
        app = create_app(live_settings())
        client = app.state.router.cheap.chat.http_client
        assert not client.is_closed
        async with app.router.lifespan_context(app):
            pass
        assert client.is_closed

    asyncio.run(check())


@pytest.mark.parametrize(
    "url",
    ["https://api.example:bad/v1", "https://api.example:99999/v1", "https://api.example/v1\npath"],
)
def test_malformed_endpoint_is_rejected_at_startup(url):
    with pytest.raises(ValidationError):
        live_settings(cheap_base_url=url)


@pytest.mark.parametrize("key", ["dummy-ş-secret", "dummy\nsecret", "dummy secret"])
def test_invalid_bearer_credentials_fail_without_exposing_the_key(key):
    with pytest.raises(ValidationError) as error:
        live_settings(cheap_api_key=key)
    assert key not in str(error.value)


@pytest.mark.parametrize("boundary", ["envelope", "content"])
def test_decimal_parse_failure_escalates_instead_of_crashing(invoice, source, boundary):
    def handle(request):
        if request.url.host == "expensive.example":
            return httpx.Response(200, json=completion(invoice))
        invalid = '{"x":1e99999999999999999999999}'
        if boundary == "envelope":
            return httpx.Response(200, content=invalid)
        body = completion(invoice)
        body["choices"][0]["message"]["content"] = invalid
        return httpx.Response(200, json=body)

    result = execute(handle, source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == "expensive"
    expected = "invalid_response" if boundary == "envelope" else "invalid_json"
    assert result.audit.calls[0].error_code == expected
