from enum import StrEnum


class Decision(StrEnum):
    ACCEPT = "ACCEPT"
    ESCALATE_TO_EXPENSIVE = "ESCALATE_TO_EXPENSIVE"
    REVIEW = "REVIEW"


class SelectedPath(StrEnum):
    CHEAP = "cheap"
    CHEAP_VERIFIER = "cheap+verifier"
    EXPENSIVE = "expensive"
    REVIEW = "review"
