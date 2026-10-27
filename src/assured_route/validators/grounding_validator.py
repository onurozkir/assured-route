import re
import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from assured_route.core.models import Invoice, ValidationCheck

AMOUNT_PATTERN = re.compile(r"(?<![\w.,+/\-])[0-9]+(?:[.,][0-9]+)*(?![\w.,+/\-])")
MAX_FUZZY_COMPARISONS = 32


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def parse_source_amount(token: str) -> Decimal | None:
    """Support explicit decimal and grouped TR/EN forms; ambiguous grouping fails closed."""
    if re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", token):
        normalized = token
    elif re.fullmatch(r"[0-9]+,[0-9]{1,2}", token):
        normalized = token.replace(",", ".")
    elif re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})+,[0-9]{2}", token):
        normalized = token.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+\.[0-9]{2}", token):
        normalized = token.replace(",", "")
    else:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def validate_grounding(invoice: Invoice, source: str, threshold: float) -> list[ValidationCheck]:
    normalized = normalize_text(source)
    amounts = {parse_source_amount(m.group()) for m in AMOUNT_PATTERN.finditer(source)}
    lines = sorted({normalize_text(line.split(":", 1)[-1]) for line in source.splitlines()})
    checks: list[ValidationCheck] = []
    for field, value in invoice.model_dump(mode="json").items():
        if field == "document_type":
            # Document type is inferred; it need not literally occur in OCR.
            continue
        candidate = normalize_text(str(value))
        if field in {"invoice_total", "vat_total"}:
            matched = Decimal(str(value)) in amounts
        else:
            matched = (
                re.search(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", normalized) is not None
            )
        fuzzy = False
        if not matched and field in {"seller_name", "buyer_name"}:
            # Maximum possible similarity from lengths alone; skip impossible matches.
            candidates = [
                line
                for line in lines
                if 2 * min(len(candidate), len(line)) / (len(candidate) + len(line)) >= threshold
            ]
            # A missed fuzzy match escalates safely instead of blocking the event loop.
            fuzzy = any(
                SequenceMatcher(None, candidate, line).ratio() >= threshold
                for line in candidates[:MAX_FUZZY_COMPARISONS]
            )
        checks.append(
            ValidationCheck(
                validator="grounding",
                field=field,
                passed=matched,
                code="source_exact" if matched else "source_fuzzy" if fuzzy else "source_missing",
                severity="info" if matched else "warning" if fuzzy else "error",
            )
        )
    return checks
