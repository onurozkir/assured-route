from assured_route.core.models import RiskAssessment, ValidationReport

WEIGHTS = {
    "schema": 0.85,
    "grounding": 0.85,
    "business_rules": 0.98,
    "verifier": 0.85,
    "runtime": 1.0,
}


def score_risk(report: ValidationReport) -> RiskAssessment:
    """Conservative maximum over field failures; this is not a probability."""
    fields: dict[str, float] = {}
    score = 0.05
    for check in report.checks:
        value = 0.05 if check.passed else WEIGHTS[check.validator]
        if check.severity == "warning":
            value = 0.2
        score = max(score, value)
        if check.field:
            fields[check.field] = max(fields.get(check.field, 0.05), value)
    return RiskAssessment(score=score, fields=fields)
