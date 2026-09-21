"""Fail-closed development routing, not an approved safeguarding classifier."""

UNAVAILABLE = (
    "The learning question service is unavailable in this development demo. "
    "Please ask a trusted adult, teacher, or qualified local scholar for help with learning questions."
)


def route_input(text: str) -> str:
    # All input takes the same unavailable route. No model, retrieval, speech,
    # disclosure processing, or data-dependent response is permitted here.
    if not text.strip() or len(text) > 2000:
        raise ValueError("invalid_request")
    return UNAVAILABLE

