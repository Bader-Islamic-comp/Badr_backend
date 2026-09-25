"""Fail-closed development routing, not an approved safeguarding classifier."""

# Development copy awaiting safeguarding and scholarly review; Robert's voice (doc/robert-persona.md).
UNAVAILABLE = (
    "My question answering is unavailable in this development version of the app, so I can't answer that yet. "
    "Please ask a trusted adult, a teacher or a qualified local scholar for help with learning questions."
)


def route_input(text: str) -> str:
    # All input takes the same unavailable route. No model, retrieval, speech,
    # disclosure processing, or data-dependent response is permitted here.
    if not text.strip() or len(text) > 2000:
        raise ValueError("invalid_request")
    return UNAVAILABLE

