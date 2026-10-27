"""Exercise five real ASGI requests and regenerate synthetic request/response artifacts."""

import asyncio
import json
import logging
import os
from copy import deepcopy
from pathlib import Path

import httpx

from assured_route.config import Settings

ROOT = Path(__file__).resolve().parent


async def main() -> None:
    # The module-level ASGI app also reads settings on import. Keep this offline
    # runner independent of an incomplete live configuration in the working tree.
    os.environ["AR_PROVIDER_MODE"] = "mock"
    from assured_route.api import create_app

    base = json.loads((ROOT / "request.json").read_text(encoding="utf-8"))
    verifier = deepcopy(base)
    verifier["metadata"]["semantic_ambiguity"] = True
    expensive = deepcopy(base)
    expensive["metadata"]["high_risk"] = True
    review = deepcopy(base)
    review["raw_ocr_text"] = review["raw_ocr_text"].replace(
        "invoice_total: 1200.00", "invoice_total: 100.00"
    )
    escalation = json.loads((ROOT / "escalation-request.json").read_text(encoding="utf-8"))
    cases = [
        ("", base, "ACCEPT", "cheap"),
        ("verifier-", verifier, "ACCEPT", "cheap+verifier"),
        ("expensive-", expensive, "ACCEPT", "expensive"),
        ("review-", review, "REVIEW", "review"),
        ("escalation-", escalation, "ACCEPT", "expensive"),
    ]
    app = create_app(Settings(_env_file=None, provider_mode="mock"))
    # Keep this demo CLI's stdout concise; the service normally emits every JSON audit.
    logging.getLogger("assured_route.audit").setLevel(logging.WARNING)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://demo"
    ) as client:
        for prefix, body, decision, path in cases:
            response = await client.post("/extract", json=body)
            response.raise_for_status()
            result = response.json()
            assert (result["decision"], result["selected_path"]) == (decision, path)
            if decision == "REVIEW":
                assert result["extracted_data"] is None
            for name, value in [("request", body), ("response", result)]:
                (ROOT / f"{prefix}{name}.json").write_text(
                    json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            print(f"{prefix or 'cheap-'} {decision} {path} USD {result['estimated_cost']}")
    candidate = {
        line.split(": ", 1)[0]: line.split(": ", 1)[1] for line in base["raw_ocr_text"].splitlines()
    }
    records = [
        {
            "document_id": "synthetic-001",
            "raw_ocr_text": base["raw_ocr_text"],
            "candidate": candidate,
            "critical_error": False,
            "observed_cost_usd": "0.0015",
        },
        {
            "document_id": "synthetic-002",
            "raw_ocr_text": base["raw_ocr_text"],
            "candidate": {**candidate, "currency": "USD"},
            "critical_error": True,
            "observed_cost_usd": "0.0015",
        },
    ]
    (ROOT / "replay.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
