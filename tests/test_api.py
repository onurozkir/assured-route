import asyncio
import json
import subprocess
import sys

import httpx

from assured_route.api import create_app
from assured_route.config import Settings


def post(body):
    async def send():
        app = create_app(Settings(_env_file=None, provider_mode="mock"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post("/extract", json=body)

    return asyncio.run(send())


def test_extract_with_default_mock(source):
    response = post({"raw_ocr_text": source})
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ACCEPT"
    assert body["selected_path"] == "cheap"
    assert body["estimated_cost"] == "0.0015"
    assert body["audit"]["document_sha256"]
    assert body["latency_breakdown"]["total_ms"] >= 0


def test_unsafe_policy_override_is_rejected(source):
    response = post({"raw_ocr_text": source, "policy": {"accept_risk_max": 0.99}})
    assert response.status_code == 422
    assert "cannot relax" in response.json()["detail"]


def test_validation_errors_do_not_echo_ocr():
    response = post({"raw_ocr_text": "SECRET invoice", "latency_budget_ms": 0})
    assert response.status_code == 422
    assert "SECRET" not in response.text


def test_env_config_supports_nested_policy(monkeypatch):
    monkeypatch.setenv("AR_POLICY__FORCE_EXPENSIVE", "true")
    monkeypatch.setenv("AR_CHEAP_COST_USD", "0.002")
    settings = Settings(_env_file=None)
    assert settings.policy.force_expensive
    assert str(settings.cheap_cost_usd) == "0.002"


def test_default_application_emits_json_audit_to_stdout():
    code = (
        "from assured_route.api import create_app; import logging; "
        "create_app(); create_app(); "
        "logging.getLogger('assured_route.audit').info('{\"request_id\":\"audit-probe\"}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=15, check=True
    )
    assert [json.loads(line) for line in result.stdout.splitlines()] == [
        {"request_id": "audit-probe"}
    ]
