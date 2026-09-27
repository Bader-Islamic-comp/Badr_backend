"""Review workflow for age-band drafts (governance task 6).

    draft -> in_review -> approved | rejected
    any reviewed state -> quarantined (emergency; content is pulled from the next release)
    rejected -> draft (the author revises)

A review item is one version of one draft: `<draft id>@<band>`, for example
`story-yusuf-s01@7-9`. Approval is refused unless the reviewer is listed as
qualified in corpus/governance/reviewers.yaml, declares no conflict for the
item, is not its author, and the version passes its reading-level checks.
Every transition is written to the audit trail before the file changes.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import audit

TRANSITIONS = {
    "submit": ({"draft"}, "in_review"),
    "approve": ({"in_review"}, "approved"),
    "reject": ({"in_review"}, "rejected"),
    "revise": ({"rejected"}, "draft"),
    "quarantine": ({"draft", "in_review", "approved", "rejected"}, "quarantined"),
}
BANDS = ("7-9", "10-11")
HEADER_END = "schema_version:"


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class Item:
    item_id: str
    path: Path
    band: str
    status: str
    author: str | None
    reviewer: str | None
    checks: str | None


def _load(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    return text[:text.index(HEADER_END)], yaml.safe_load(text)


def items(drafts: Path) -> list[Item]:
    found = []
    for path in sorted(Path(drafts).rglob("*.yaml")):
        _, data = _load(path)
        for band in BANDS:
            version = data["versions"][band]
            found.append(Item(f"{data['id']}@{band}", path, band, version["review_status"], version["author"],
                              version["reviewer"], (version.get("reading_level_checks") or {}).get("status")))
    return found


def load_reviewers(path: Path) -> dict[str, dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {entry["name"]: entry for entry in data.get("reviewers") or []}


def transition(drafts: Path, item_id: str, action: str, actor: str, *, audit_path: Path, reviewers_path: Path,
               reason: str = "", decision_id: str | None = None) -> Item:
    if action not in TRANSITIONS:
        raise ReviewError(f"unknown action {action!r}")
    if action in ("approve", "reject") and not decision_id:
        raise ReviewError("approve and reject come only from a signed decision: add it to "
                          "doc/decisions/decisions.yaml and run scripts/apply_decisions.py")
    allowed, target = TRANSITIONS[action]
    match = next((item for item in items(drafts) if item.item_id == item_id), None)
    if match is None:
        raise ReviewError(f"no review item {item_id!r}")
    if match.status not in allowed:
        raise ReviewError(f"{item_id} is {match.status}; {action} needs {' or '.join(sorted(allowed))}")
    if action == "submit" and match.author != actor:
        raise ReviewError("only the author submits a draft for review")
    if action in ("approve", "reject"):
        if actor == match.author:
            raise ReviewError(f"{actor} wrote {item_id} and cannot review it")
        reviewer = load_reviewers(reviewers_path).get(actor)
        if reviewer is None or not reviewer.get("qualified"):
            raise ReviewError(f"{actor} is not a qualified reviewer in {reviewers_path}")
        draft_id = item_id.split("@")[0]
        if draft_id in (reviewer.get("conflicts") or []):
            raise ReviewError(f"{actor} declared a conflict of interest for {draft_id}")
    if action == "approve" and match.checks != "pass":
        raise ReviewError(f"{item_id} does not pass its reading-level checks (status {match.checks}); "
                          "run scripts/age_band.py check")
    if action in ("reject", "quarantine") and not reason.strip():
        raise ReviewError(f"{action} needs a reason")
    audit.append(audit_path, actor=actor, action=f"review.{action}", item=item_id, from_state=match.status,
                 to_state=target, reason=f"{decision_id}: {reason}" if decision_id else reason)
    header, data = _load(match.path)
    version = data["versions"][match.band]
    version["review_status"] = target
    if action in ("approve", "reject"):
        version["reviewer"] = actor
    match.path.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
                          encoding="utf-8", newline="\n")
    return next(item for item in items(drafts) if item.item_id == item_id)
