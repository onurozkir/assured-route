import re
from dataclasses import dataclass

from assured_route.core.models import ExtractRequest
from assured_route.core.policy import Policy


@dataclass(frozen=True)
class PreRoute:
    use_expensive: bool
    reasons: tuple[str, ...]
    estimated_risk: float


class PreRouter:
    def route(self, request: ExtractRequest, policy: Policy) -> PreRoute:
        metadata = request.metadata
        reasons = []
        if policy.force_expensive:
            reasons.append("policy_force_expensive")
        if metadata.high_risk:
            reasons.append("metadata_high_risk")
        if metadata.ocr_quality < policy.low_ocr_threshold:
            reasons.append("low_ocr_quality")
        if not metadata.known_template:
            reasons.append("unknown_template")
        if metadata.page_count > policy.max_cheap_pages:
            reasons.append("too_many_pages")
        if len(request.raw_ocr_text) > policy.max_cheap_chars:
            reasons.append("long_document")
        currencies = set(re.findall(r"\b(?:TRY|USD|EUR|GBP)\b", request.raw_ocr_text.upper()))
        if len(currencies) > 1:
            reasons.append("multiple_currencies")
        return PreRoute(
            bool(reasons), tuple(reasons) or ("cheap_eligible",), 0.85 if reasons else 0.1
        )


# TODO: Learn a LightGBM router using features available before inference; evaluate per segment.
