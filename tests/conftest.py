import os

import pytest

# Test collection imports the module-level FastAPI app. Never let a developer's
# live .env switch that app to a paid provider; live-adapter tests inject settings.
os.environ["AR_PROVIDER_MODE"] = "mock"


@pytest.fixture
def invoice() -> dict[str, object]:
    return {
        "document_type": "invoice",
        "invoice_number": "INV-2026-001",
        "invoice_date": "2026-10-20",
        "due_date": "2026-11-20",
        "currency": "TRY",
        "invoice_total": "1200.00",
        "vat_total": "200.00",
        "seller_name": "Acme Ltd",
        "seller_tax_id": "1234567890",
        "buyer_name": "Buyer Ltd",
    }


@pytest.fixture
def source(invoice: dict[str, object]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in invoice.items())
