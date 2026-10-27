from assured_route.core.decisions import Decision
from assured_route.core.models import (
    GateResult,
    ValidationCheck,
    ValidationReport,
    VerificationResult,
)
from assured_route.core.policy import Policy
from assured_route.core.risk import score_risk
from assured_route.validators.business_rules import validate_business_rules
from assured_route.validators.grounding_validator import validate_grounding
from assured_route.validators.schema_validator import validate_schema


class QualityGate:
    def evaluate(
        self,
        raw: dict[str, object],
        source: str,
        policy: Policy,
        verifier: VerificationResult | None = None,
        require_verifier: bool = False,
    ) -> GateResult:
        invoice, checks = validate_schema(raw)
        if invoice is not None:
            checks += validate_grounding(invoice, source, policy.fuzzy_name_threshold)
            checks += validate_business_rules(invoice)
        fuzzy_fields = [c.field for c in checks if c.code == "source_fuzzy"]
        required = require_verifier or policy.require_verifier or bool(fuzzy_fields)
        if verifier is not None:
            fields: list[str | None] = list(verifier.disputed_fields) or [None]
            for field in fields:
                checks.append(
                    ValidationCheck(
                        validator="verifier",
                        code="verifier_agrees" if verifier.agrees else "verifier_disagrees",
                        field=field,
                        passed=verifier.agrees and not verifier.disputed_fields,
                        severity="error",
                    )
                )
            # Agreement may resolve fuzzy names only. Exact critical failures remain failures.
            if verifier.agrees and not verifier.disputed_fields:
                for check in checks:
                    if check.code == "source_fuzzy":
                        check.passed = True
                        check.severity = "info"
        elif required:
            checks.append(
                ValidationCheck(
                    validator="verifier",
                    code="verifier_required",
                    passed=False,
                    severity="warning",
                )
            )
        failures = [c for c in checks if not c.passed]
        deterministic_errors = [
            c for c in failures if c.validator != "verifier" and c.severity != "warning"
        ]
        needs_verifier = required and verifier is None and not deterministic_errors
        report = ValidationReport(checks=checks)
        risk = score_risk(report)
        if any(not c.recoverable for c in failures):
            decision = Decision.REVIEW
        elif failures or risk.score > policy.accept_risk_max:
            decision = Decision.ESCALATE_TO_EXPENSIVE
        else:
            decision = Decision.ACCEPT
        return GateResult(
            invoice=invoice,
            decision=decision,
            report=report,
            risk=risk,
            needs_verifier=needs_verifier,
        )
