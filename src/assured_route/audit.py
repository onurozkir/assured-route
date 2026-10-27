import json
import logging
import sys

from assured_route.core.models import ExtractResponse

logger = logging.getLogger("assured_route.audit")


def configure_audit_logging(level: str) -> None:
    logger.setLevel(level.upper())
    if not any(handler.name == "assured_route.stdout" for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.name = "assured_route.stdout"
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


def log_result(result: ExtractResponse) -> None:
    """Value-free audit; add a durable sink without logging source or extracted values."""
    payload = result.audit.model_dump(mode="json")
    payload.update(
        decision=result.decision,
        path=result.selected_path,
        estimated_cost_usd=str(result.estimated_cost),
        risk_score=result.estimated_risk_score,
        total_ms=result.latency_breakdown.total_ms,
    )
    logger.info(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


# TODO: Durable, access-controlled audit storage with retention and integrity guarantees.
