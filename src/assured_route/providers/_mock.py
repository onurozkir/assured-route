from assured_route.core.models import Invoice
from assured_route.providers.interfaces import ProviderError
from assured_route.validators.grounding_validator import normalize_text, parse_source_amount

ALIASES = {
    "fatura no": "invoice_number",
    "invoice no": "invoice_number",
    "fatura tarihi": "invoice_date",
    "vade tarihi": "due_date",
    "para birimi": "currency",
    "genel toplam": "invoice_total",
    "kdv toplam": "vat_total",
    "satıcı": "seller_name",
    "satici": "seller_name",
    "vergi no": "seller_tax_id",
    "alıcı": "buyer_name",
    "alici": "buyer_name",
}


def parse_labeled_invoice(source: str, *, extended: bool) -> dict[str, object]:
    """Deterministic demo parser, not an OCR engine or a simulated quality benchmark."""
    payload: dict[str, object] = {"document_type": "invoice"}
    seen: dict[str, str] = {}
    for line in source.splitlines():
        label, separator, value = line.partition(":")
        if not separator:
            continue
        key = normalize_text(label)
        if extended:
            key = ALIASES.get(key, key)
        if key not in Invoice.model_fields:
            continue
        value = value.strip()
        if key in seen and seen[key] != value:
            raise ProviderError("Conflicting duplicate source labels")
        seen[key] = value
        if key in {"invoice_total", "vat_total"}:
            amount = parse_source_amount(value)
            payload[key] = str(amount) if amount is not None else value
        else:
            payload[key] = value
    return payload
