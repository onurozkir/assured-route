from decimal import Decimal

import pytest

from assured_route.core.decisions import Decision
from assured_route.core.models import VerificationResult
from assured_route.core.policy import Policy, PolicyOverrides
from assured_route.validators.quality_gate import QualityGate


def test_accepts_grounded_invoice(invoice, source):
    result = QualityGate().evaluate(invoice, source, Policy())
    assert result.decision == Decision.ACCEPT
    assert result.invoice.invoice_total == Decimal("1200.00")
    assert result.report.passed


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "not-a-number", -1])
def test_rejects_invalid_amounts(invoice, source, value):
    invoice["invoice_total"] = value
    result = QualityGate().evaluate(invoice, source, Policy())
    assert result.decision == Decision.ESCALATE_TO_EXPENSIVE
    assert any(c.validator == "schema" and not c.passed for c in result.report.checks)
    assert result.risk.score >= 0.8


@pytest.mark.parametrize("value", ["20/10/2026", "20261020", "2026-02-30", 1792454400])
def test_requires_real_iso_calendar_dates(invoice, source, value):
    invoice["invoice_date"] = value
    assert QualityGate().evaluate(invoice, source, Policy()).decision != Decision.ACCEPT


def test_missing_required_field_is_recoverable(invoice, source):
    del invoice["seller_tax_id"]
    result = QualityGate().evaluate(invoice, source, Policy())
    assert result.decision == Decision.ESCALATE_TO_EXPENSIVE


def test_total_smaller_than_tax_requires_review(invoice, source):
    invoice["invoice_total"] = "100.00"
    result = QualityGate().evaluate(invoice, source + "\ninvoice_total: 100.00", Policy())
    assert result.decision == Decision.REVIEW
    assert result.risk.score >= 0.95


def test_numeric_substrings_do_not_count_as_grounding(invoice, source):
    invoice["invoice_total"] = "200.00"
    # Remove vat line; 200.00 is only a suffix of 1200.00.
    source = "\n".join(line for line in source.splitlines() if not line.startswith("vat_total:"))
    result = QualityGate().evaluate(invoice, source, Policy())
    checks = [c for c in result.report.checks if c.field == "invoice_total"]
    assert any(c.validator == "grounding" and not c.passed for c in checks)


def test_verifier_cannot_override_schema_failure(invoice, source):
    del invoice["currency"]
    result = QualityGate().evaluate(
        invoice, source, Policy(), VerificationResult(agrees=True, model_version="v1")
    )
    assert result.decision == Decision.ESCALATE_TO_EXPENSIVE


def test_disagreement_escalates(invoice, source):
    result = QualityGate().evaluate(
        invoice,
        source,
        Policy(),
        VerificationResult(agrees=False, disputed_fields=["invoice_total"], model_version="v1"),
    )
    assert result.decision == Decision.ESCALATE_TO_EXPENSIVE
    assert result.risk.fields["invoice_total"] >= 0.8


def test_semantic_ambiguity_requires_verifier(invoice, source):
    result = QualityGate().evaluate(invoice, source, Policy(), require_verifier=True)
    assert result.needs_verifier
    assert result.decision != Decision.ACCEPT


def test_policy_override_cannot_relax_server_risk_threshold():
    with pytest.raises(ValueError):
        Policy(accept_risk_max=0.1).with_overrides(PolicyOverrides(accept_risk_max=0.5))


@pytest.mark.parametrize("fragment", ["2026-10-20", "2026/10/20", "2026-AB", "AB/2026"])
def test_date_and_identifier_fragments_cannot_ground_amounts(invoice, source, fragment):
    invoice["invoice_total"] = "2026"
    source = "\n".join(
        line
        for line in source.splitlines()
        if not line.startswith(("invoice_total:", "invoice_date:"))
    )
    result = QualityGate().evaluate(invoice, source + "\nref: " + fragment, Policy())
    assert any(
        c.field == "invoice_total" and c.validator == "grounding" and not c.passed
        for c in result.report.checks
    )


def test_untrusted_field_names_never_enter_validation_audit(invoice, source):
    secret = "SECRET customer@email.example"
    schema_result = QualityGate().evaluate({**invoice, secret: "value"}, source, Policy())
    verifier_result = QualityGate().evaluate(
        invoice,
        source,
        Policy(),
        VerificationResult(agrees=False, disputed_fields=[secret], model_version="test"),
    )
    assert secret not in schema_result.report.model_dump_json()
    assert secret not in verifier_result.report.model_dump_json()
    assert schema_result.decision != Decision.ACCEPT
    assert verifier_result.decision != Decision.ACCEPT


def test_fuzzy_comparison_prefilters_impossible_lengths_and_deduplicates(
    invoice, source, monkeypatch
):
    from assured_route.validators import grounding_validator as module

    real_matcher = module.SequenceMatcher
    compared = []

    def tracked_matcher(junk, a, b):
        compared.append(b)
        return real_matcher(junk, a, b)

    monkeypatch.setattr(module, "SequenceMatcher", tracked_matcher)
    invoice["seller_name"] = "ab" * 150
    # Max name length 300. Tiny lines cannot achieve the configured 0.92 similarity.
    result = QualityGate().evaluate(invoice, source + "\n" + "ab\n" * 32000, Policy())
    assert result.decision != Decision.ACCEPT
    assert compared == []
