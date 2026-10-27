from pydantic import ValidationError

from assured_route.core.models import Invoice, ValidationCheck


def validate_schema(raw: dict[str, object]) -> tuple[Invoice | None, list[ValidationCheck]]:
    try:
        invoice = Invoice.model_validate(raw)
    except ValidationError as exc:
        # Never copy Pydantic's input/ctx into a public report or audit log.
        return None, [
            ValidationCheck(
                validator="schema",
                code="schema_invalid",
                passed=False,
                field=str(error["loc"][0]) if error["loc"] else None,
                severity="error",
            )
            for error in exc.errors(include_input=False, include_context=False)
        ]
    return invoice, [ValidationCheck(validator="schema", code="schema_valid", passed=True)]
