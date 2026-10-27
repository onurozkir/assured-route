from assured_route.core.decisions import Decision
from assured_route.core.models import GateResult
from assured_route.routing.deadline_manager import DeadlineManager


def can_escalate(result: GateResult | None, deadline: DeadlineManager, expected_ms: int) -> bool:
    """At most one expensive attempt; fatal contradictions always need human review."""
    return (
        result is None or result.decision == Decision.ESCALATE_TO_EXPENSIVE
    ) and deadline.can_start(expected_ms)
