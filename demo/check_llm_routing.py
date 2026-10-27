"""Run the actual HTTP adapters against a local Postman LLM simulation, no paid API calls."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from assured_route.config import Settings
from assured_route.core.policy import Policy

ROOT = Path(__file__).resolve().parent


async def check(url: str) -> None:
    # Only explicitly constructed simulation settings below may select live mode.
    os.environ["AR_PROVIDER_MODE"] = "mock"
    from assured_route.api import create_app

    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("This synthetic-data runner accepts a local HTTP simulation URL only")
    base = json.loads((ROOT / "request.json").read_text(encoding="utf-8"))
    # cheap ID, expensive ID, metadata, budget, final decision/path, outbound role sequence
    cases = [
        ("cheap-good", "expensive-good", {}, 5000, "ACCEPT", "cheap", ["cheap"]),
        (
            "cheap-schema-fail",
            "expensive-good",
            {},
            5000,
            "ACCEPT",
            "expensive",
            ["cheap", "expensive"],
        ),
        (
            "cheap-grounding-fail",
            "expensive-good",
            {},
            5000,
            "ACCEPT",
            "expensive",
            ["cheap", "expensive"],
        ),
        ("cheap-401", "expensive-good", {}, 5000, "ACCEPT", "expensive", ["cheap", "expensive"]),
        ("cheap-429", "expensive-good", {}, 5000, "ACCEPT", "expensive", ["cheap", "expensive"]),
        ("cheap-500", "expensive-good", {}, 5000, "ACCEPT", "expensive", ["cheap", "expensive"]),
        (
            "cheap-invalid-json",
            "expensive-good",
            {},
            5000,
            "ACCEPT",
            "expensive",
            ["cheap", "expensive"],
        ),
        (
            "cheap-refusal",
            "expensive-good",
            {},
            5000,
            "ACCEPT",
            "expensive",
            ["cheap", "expensive"],
        ),
        (
            "cheap-truncated",
            "expensive-good",
            {},
            5000,
            "ACCEPT",
            "expensive",
            ["cheap", "expensive"],
        ),
        (
            "cheap-timeout",
            "expensive-good",
            {},
            5000,
            "ACCEPT",
            "expensive",
            ["cheap", "expensive"],
        ),
        (
            "cheap-good",
            "expensive-good",
            {"high_risk": True},
            5000,
            "ACCEPT",
            "expensive",
            ["expensive"],
        ),
        (
            "cheap-good",
            "expensive-good",
            {"semantic_ambiguity": True},
            5000,
            "ACCEPT",
            "cheap+verifier",
            ["cheap", "verifier"],
        ),
        ("cheap-fatal", "expensive-good", {}, 5000, "REVIEW", "review", ["cheap"]),
        (
            "cheap-schema-fail",
            "expensive-schema-fail",
            {},
            5000,
            "REVIEW",
            "review",
            ["cheap", "expensive"],
        ),
        (
            "cheap-good",
            "expensive-500",
            {"high_risk": True},
            5000,
            "REVIEW",
            "review",
            ["expensive"],
        ),
        ("cheap-good", "expensive-good", {}, 1, "REVIEW", "review", []),
    ]
    for cheap, expensive, metadata, budget, decision, path, roles in cases:
        settings = Settings(
            _env_file=None,
            provider_mode="openai_compatible",
            cheap_model=cheap,
            cheap_api_key="simulation-cheap-key",
            cheap_base_url=url + "/cheap/v1",
            expensive_model=expensive,
            expensive_api_key="simulation-expensive-key",
            expensive_base_url=url + "/expensive/v1",
            policy=Policy(
                provider_timeout_ms=2000,
                cheap_timeout_ms=500,
                cheap_expected_ms=10,
                expensive_expected_ms=10,
                verifier_expected_ms=10,
                response_reserve_ms=10,
            ),
        )
        app = create_app(settings)
        logging.getLogger("assured_route.audit").setLevel(logging.WARNING)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local"
            ) as client:
                request = {**base, "metadata": metadata, "latency_budget_ms": budget}
                response = await client.post("/extract", json=request)
                response.raise_for_status()
                result = response.json()
        assert (result["decision"], result["selected_path"]) == (decision, path), (cheap, result)
        assert [call["role"] for call in result["audit"]["calls"]] == roles, (cheap, result)
        if decision == "REVIEW":
            assert result["extracted_data"] is None
        assert "simulation-cheap-key" not in response.text
        assert "simulation-expensive-key" not in response.text
        print(f"PASS {cheap} / {expensive}: {decision} via {path}; calls={','.join(roles)}")
    print(f"{len(cases)} real-HTTP integration scenarios passed; no paid model API was contacted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simulation-url", required=True, help="Use the URL from the Postman listening event"
    )
    args = parser.parse_args()
    asyncio.run(check(args.simulation_url.rstrip("/")))


if __name__ == "__main__":
    main()
