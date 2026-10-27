import re

from assured_route.core.models import Invoice, ValidationCheck


def validate_business_rules(invoice: Invoice) -> list[ValidationCheck]:
    return [
        ValidationCheck(
            validator="business_rules",
            code="total_covers_vat",
            field="invoice_total",
            passed=invoice.invoice_total >= invoice.vat_total,
            severity="fatal",
            recoverable=False,
        ),
        ValidationCheck(
            validator="business_rules",
            code="due_after_invoice",
            field="due_date",
            passed=invoice.due_date >= invoice.invoice_date,
            severity="fatal",
            recoverable=False,
        ),
        ValidationCheck(
            validator="business_rules",
            code="tax_id_length",
            field="seller_tax_id",
            passed=re.fullmatch(r"[0-9]{10,11}", invoice.seller_tax_id) is not None,
            severity="error",
        ),
    ]
