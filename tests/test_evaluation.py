from decimal import Decimal

import pytest
from pydantic import ValidationError

from assured_route.core.policy import Policy
from assured_route.evaluation.cost_simulator import CostScenario, RouteShare, simulate
from assured_route.evaluation.policy_replay import RecordedCandidate, replay


def test_replay_measures_only_independently_labeled_accepted_errors(invoice, source):
    records = [
        RecordedCandidate(
            document_id="a",
            raw_ocr_text=source,
            candidate=invoice,
            critical_error=False,
            observed_cost_usd="0.0015",
        ),
        RecordedCandidate(
            document_id="b",
            raw_ocr_text=source,
            candidate=invoice,
            critical_error=True,
            observed_cost_usd="0.0015",
        ),
        RecordedCandidate(document_id="c", raw_ocr_text=source, candidate=invoice),
        RecordedCandidate(
            document_id="d", raw_ocr_text=source, candidate={**invoice, "currency": "USD"}
        ),
    ]
    result = replay(records, Policy())
    assert result.accepted == 3
    assert result.escalated == 1
    assert result.cheap_acceptance_coverage == 0.75
    assert result.labeled_accepted == 2
    assert result.critical_error_rate == 0.5
    assert result.observed_cost_per_verified_success == Decimal("0.0030")


def test_replay_unlabeled_data_does_not_claim_zero_error(invoice, source):
    result = replay(
        [RecordedCandidate(document_id="a", raw_ocr_text=source, candidate=invoice)], Policy()
    )
    assert result.critical_error_rate is None
    assert result.observed_cost_per_verified_success is None


def test_replay_empty_dataset_has_no_defined_coverage():
    result = replay([], Policy())
    assert result.cheap_acceptance_coverage is None
    assert result.critical_error_rate is None


def test_replay_rejects_duplicate_tasks(invoice, source):
    record = RecordedCandidate(document_id="same", raw_ocr_text=source, candidate=invoice)
    with pytest.raises(ValueError, match="Duplicate"):
        replay([record, record], Policy())


def test_cost_simulator_reproduces_blog_scenario():
    scenario = CostScenario(
        monthly_requests=4_000_000,
        routes=[
            RouteShare(name="direct_expensive", share="0.20", expensive_calls=1),
            RouteShare(name="cheap_rules", share="0.55", cheap_calls=1),
            RouteShare(name="cheap_verified", share="0.15", cheap_calls=1, verifier_calls=1),
            RouteShare(
                name="verified_escalation",
                share="0.05",
                cheap_calls=1,
                verifier_calls=1,
                expensive_calls=1,
            ),
            RouteShare(name="early_escalation", share="0.05", cheap_calls=1, expensive_calls=1),
        ],
        shadow_expensive_calls=60_000,
        infrastructure_cost_usd="60",  # verifier 240 + infrastructure 60 = 300
    )
    result = simulate(scenario)
    assert result.cheap_cost_usd == Decimal("4800")
    assert result.expensive_cost_usd == Decimal("18000")
    assert result.total_cost_usd == Decimal("24000")
    assert result.total_savings_usd == Decimal("36000")
    assert result.cost_per_verified_success is None


def test_cost_simulator_includes_review_and_error_loss():
    scenario = CostScenario(
        monthly_requests=1000,
        routes=[RouteShare(name="cheap", share=1, cheap_calls=1)],
        review_share="0.1",
        review_unit_cost_usd=2,
        expected_error_share="0.001",
        error_loss_per_task_usd=10,
        verified_success_share="0.9",
    )
    result = simulate(scenario)
    assert result.total_cost_usd == Decimal("211.5")
    assert result.cost_per_verified_success == Decimal("211.5") / Decimal(900)


def test_cost_simulator_rejects_invalid_traffic_distribution():
    with pytest.raises(ValidationError, match="sum to 1"):
        CostScenario(monthly_requests=10, routes=[RouteShare(name="cheap", share="0.8")])
