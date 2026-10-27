import argparse
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from assured_route.core.models import Contract

type Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
type Share = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]


class RouteShare(Contract):
    name: str = Field(min_length=1)
    share: Share
    cheap_calls: int = Field(default=0, ge=0, le=10)
    expensive_calls: int = Field(default=0, ge=0, le=10)
    verifier_calls: int = Field(default=0, ge=0, le=10)


class CostScenario(Contract):
    monthly_requests: int = Field(ge=1)
    routes: list[RouteShare] = Field(min_length=1)
    cheap_unit_cost_usd: Money = Decimal("0.0015")
    expensive_unit_cost_usd: Money = Decimal("0.015")
    verifier_unit_cost_usd: Money = Decimal("0.0003")
    shadow_expensive_calls: int = Field(default=0, ge=0)
    infrastructure_cost_usd: Money = Decimal(0)
    review_share: Share = Decimal(0)
    review_unit_cost_usd: Money = Decimal(0)
    expected_error_share: Share = Decimal(0)
    error_loss_per_task_usd: Money = Decimal(0)
    verified_success_share: Share | None = None

    @model_validator(mode="after")
    def valid_mix(self) -> Self:
        if sum((route.share for route in self.routes), Decimal(0)) != 1:
            raise ValueError("Route shares must sum to 1")
        if len({route.name for route in self.routes}) != len(self.routes):
            raise ValueError("Route names must be unique")
        return self


class CostSummary(Contract):
    cheap_cost_usd: Decimal
    expensive_cost_usd: Decimal
    verifier_cost_usd: Decimal
    shadow_cost_usd: Decimal
    review_cost_usd: Decimal
    expected_error_loss_usd: Decimal
    infrastructure_cost_usd: Decimal
    total_cost_usd: Decimal
    baseline_expensive_cost_usd: Decimal
    total_savings_usd: Decimal
    cost_per_verified_success: Decimal | None
    basis: str = "scenario_assumptions_not_measured_production_savings"


def simulate(scenario: CostScenario) -> CostSummary:
    requests = Decimal(scenario.monthly_requests)
    cheap = (
        requests
        * sum((r.share * r.cheap_calls for r in scenario.routes), Decimal(0))
        * scenario.cheap_unit_cost_usd
    )
    expensive = (
        requests
        * sum((r.share * r.expensive_calls for r in scenario.routes), Decimal(0))
        * scenario.expensive_unit_cost_usd
    )
    verifier = (
        requests
        * sum((r.share * r.verifier_calls for r in scenario.routes), Decimal(0))
        * scenario.verifier_unit_cost_usd
    )
    shadow = scenario.shadow_expensive_calls * scenario.expensive_unit_cost_usd
    review = requests * scenario.review_share * scenario.review_unit_cost_usd
    error_loss = requests * scenario.expected_error_share * scenario.error_loss_per_task_usd
    total = (
        cheap
        + expensive
        + verifier
        + shadow
        + review
        + error_loss
        + scenario.infrastructure_cost_usd
    )
    baseline = requests * scenario.expensive_unit_cost_usd
    successes = (
        requests * scenario.verified_success_share
        if scenario.verified_success_share is not None
        else Decimal(0)
    )
    return CostSummary(
        cheap_cost_usd=cheap,
        expensive_cost_usd=expensive,
        verifier_cost_usd=verifier,
        shadow_cost_usd=shadow,
        review_cost_usd=review,
        expected_error_loss_usd=error_loss,
        infrastructure_cost_usd=scenario.infrastructure_cost_usd,
        total_cost_usd=total,
        baseline_expensive_cost_usd=baseline,
        total_savings_usd=baseline - total,
        cost_per_verified_success=total / successes if successes else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate routing costs from explicit traffic shares"
    )
    parser.add_argument("scenario", type=Path)
    args = parser.parse_args()
    scenario = CostScenario.model_validate_json(args.scenario.read_text(encoding="utf-8"))
    print(simulate(scenario).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
