import argparse
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from pydantic import Field

from assured_route.core.decisions import Decision
from assured_route.core.models import Contract, VerificationResult
from assured_route.core.policy import Policy
from assured_route.validators.quality_gate import QualityGate


class RecordedCandidate(Contract):
    document_id: str = Field(min_length=1)
    raw_ocr_text: str = Field(min_length=1, max_length=100000)
    candidate: dict[str, object]
    verifier: VerificationResult | None = None
    require_verifier: bool = False
    critical_error: bool | None = None  # Independent adjudication, NOT teacher disagreement.
    observed_cost_usd: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)


class ReplaySummary(Contract):
    total: int
    accepted: int
    escalated: int
    reviewed: int
    cheap_acceptance_coverage: float | None
    labeled_accepted: int
    critical_error_rate: float | None
    observed_cost_usd: Decimal
    observed_cost_per_verified_success: Decimal | None
    scope: str = "gate_only_recorded_candidates_not_counterfactual_routing"


def replay(records: Iterable[RecordedCandidate], policy: Policy) -> ReplaySummary:
    """Re-evaluate recorded candidates. Missing verifier/labels remain unknown.

    Input has one consolidated record per task, including all observed attempt costs.
    This function cannot estimate the outcome/cost of an unobserved expensive model.
    """
    gate = QualityGate()
    seen: set[str] = set()
    counts = dict.fromkeys(Decision, 0)
    total = labeled = errors = successes = 0
    cost = Decimal(0)
    for record in records:
        if record.document_id in seen:
            raise ValueError(f"Duplicate document_id: {record.document_id}")
        seen.add(record.document_id)
        result = gate.evaluate(
            record.candidate, record.raw_ocr_text, policy, record.verifier, record.require_verifier
        )
        counts[result.decision] += 1
        total += 1
        cost += record.observed_cost_usd
        if result.decision == Decision.ACCEPT and record.critical_error is not None:
            labeled += 1
            errors += int(record.critical_error)
            successes += int(not record.critical_error)
    return ReplaySummary(
        total=total,
        accepted=counts[Decision.ACCEPT],
        escalated=counts[Decision.ESCALATE_TO_EXPENSIVE],
        reviewed=counts[Decision.REVIEW],
        cheap_acceptance_coverage=counts[Decision.ACCEPT] / total if total else None,
        labeled_accepted=labeled,
        critical_error_rate=errors / labeled if labeled else None,
        observed_cost_usd=cost,
        observed_cost_per_verified_success=cost / successes if successes else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay quality-gate decisions on JSONL candidates"
    )
    parser.add_argument("records", type=Path)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()
    policy = (
        Policy.model_validate_json(args.policy.read_text(encoding="utf-8"))
        if args.policy
        else Policy()
    )
    records = [
        RecordedCandidate.model_validate_json(line)
        for line in args.records.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(replay(records, policy).model_dump_json(indent=2))


if __name__ == "__main__":
    main()

# TODO: Confidence intervals, stratified weighting and risk-coverage curves on golden data.
