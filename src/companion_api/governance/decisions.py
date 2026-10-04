"""Human decisions (doc/decisions/decisions.yaml) applied through the review tool and the audit trail.

The only way anything becomes approved, cleared or rejected. Each decision names a person, a role and a
date; a decision without them, or by someone not authorised for that kind of item, is refused whole.
AI verdicts (ai_prereview) are never decisions and never change a status.

Kinds of item and who may decide them:

    source:<source_id>          licence clearance        governance owner (Mousa al-Rashdan)
    policy-<name>, section18:<key>, reviewers   policy   governance owner
    selection-NN, map-<prophet>-NN, <draft>@<band>       qualified reviewer (reviewers.yaml), not the author
    gold/harmful question ids                            pipeline owner (Momen Alhamza) or a qualified reviewer
"""
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re

import yaml

from ..corpusprep import registry as registry_module
from . import audit, review, signatures

GOVERNANCE_OWNER = "Mousa al-Rashdan"
PIPELINE_OWNER = "Momen Alhamza"
DECISIONS = ("approve", "reject", "revise", "defer")
ROLES = ("governance", "pipeline", "scholarly", "safeguarding", "language")
REQUIRED = ("decision_id", "item_ids", "decision", "decided_by", "role", "date", "note")
FINAL = ("approve", "reject")


class DecisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paths:
    decisions: Path
    state: Path
    audit: Path
    reviewers: Path
    registry: Path
    drafts: Path
    known_items: frozenset
    # test/corpus-tasks: with `signers` set, every new decision must be committed and SSH-signed by the person it
    # names (signatures.py); `repo` is the git checkout holding the decisions file.
    signers: Path | None = None
    repo: Path | None = None


def signature_problems(paths: Paths, entries: list[dict]) -> dict[str, list[str]]:
    """decision_id -> signature problems; empty when signatures are not required or all are good."""
    if paths.signers is None or not entries:
        return {}
    return signatures.check(paths.decisions, entries, paths.signers, paths.repo or paths.decisions.parent)


def kind_of(item_id: str) -> str:
    if item_id.startswith("adr-"):
        return "adr"
    if item_id.startswith("source:"):
        return "source"
    if item_id.startswith(("policy-", "section18:")) or item_id == "reviewers":
        return "policy"
    if "@" in item_id:
        return "age_band"
    if item_id.startswith(("selection-", "map-")):
        return "content"
    return "eval"


def _authorised(entry: dict, kind: str, reviewers: dict) -> str | None:
    name, role = entry["decided_by"], entry["role"]
    qualified = name in reviewers and reviewers[name].get("qualified")
    if kind in ("source", "policy"):
        return None if name == GOVERNANCE_OWNER and role == "governance" else \
            f"{kind} decisions belong to {GOVERNANCE_OWNER} (role governance)"
    if kind in ("content", "age_band"):
        if not qualified:
            return f"{name} is not a qualified reviewer in reviewers.yaml"
        if role not in (reviewers[name].get("roles") or []):
            return f"{name} is not listed with role {role}"
        return None
    if kind == "adr":
        return None if name == PIPELINE_OWNER and role == "pipeline" else \
            f"architecture decisions on the pipeline belong to {PIPELINE_OWNER} (role pipeline)"
    if name == PIPELINE_OWNER and role == "pipeline" or qualified:
        return None
    return f"evaluation items belong to {PIPELINE_OWNER} (role pipeline) or a qualified reviewer"


def validate(entry: dict, paths: Paths, reviewers: dict) -> list[str]:
    problems = []
    missing = [key for key in REQUIRED if key not in entry]
    if missing:
        return [f"missing {', '.join(missing)}"]
    if not isinstance(entry["decided_by"], str) or not entry["decided_by"].strip():
        problems.append("decided_by is empty")
    if entry["decision"] not in DECISIONS:
        problems.append(f"decision must be one of {', '.join(DECISIONS)}")
    if entry["role"] not in ROLES:
        problems.append(f"role must be one of {', '.join(ROLES)}")
    try:
        if not (isinstance(entry["date"], (str, date)) and date.fromisoformat(str(entry["date"]))):
            raise ValueError
    except ValueError:
        problems.append("date must be a full ISO date like 2026-10-01")
    items = entry["item_ids"]
    if not isinstance(items, list) or not items:
        problems.append("item_ids must be a non-empty list")
        return problems
    if not problems:
        for item in items:
            if item not in paths.known_items:
                problems.append(f"unknown item {item}")
                continue
            reason = _authorised(entry, kind_of(item), reviewers)
            if reason:
                problems.append(f"{item}: {reason}")
    return problems


def _load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"applied": [], "items": {}}


def apply(paths: Paths) -> dict:
    """Validates every new decision first; applies them only if all are valid."""
    data = yaml.safe_load(paths.decisions.read_text(encoding="utf-8")) or {}
    entries = data.get("decisions") or []
    state = _load_state(paths.state)
    reviewers = review.load_reviewers(paths.reviewers)
    new = [entry for entry in entries if entry.get("decision_id") not in state["applied"]]
    problems = {entry.get("decision_id", f"#{i}"): validate(entry, paths, reviewers) for i, entry in enumerate(new)}
    problems = {key: value for key, value in problems.items() if value}
    ids = [entry.get("decision_id") for entry in entries]
    if len(ids) != len(set(ids)):
        problems["decisions"] = ["decision_id values must be unique"]
    for decision_id, found in signature_problems(paths, new).items():
        problems.setdefault(decision_id, []).extend(found)
    if problems:
        raise DecisionError("refused, nothing applied:\n" + "\n".join(
            f"  {key}: {'; '.join(value)}" for key, value in problems.items()))
    applied = []
    for entry in new:
        for item in entry["item_ids"]:
            _apply_one(entry, item, paths, state)
        state["applied"].append(entry["decision_id"])
        applied.append(entry["decision_id"])
        paths.state.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"applied": applied, "already_applied": len(entries) - len(new)}


def _apply_one(entry: dict, item: str, paths: Paths, state: dict) -> None:
    decision, actor, kind = entry["decision"], entry["decided_by"], kind_of(item)
    previous = state["items"].get(item, {}).get("status", "pending")
    target = {"approve": "approved", "reject": "rejected", "revise": "revise", "defer": "deferred"}[decision]
    if kind == "source" and decision in FINAL:
        target = "cleared" if decision == "approve" else "rejected"
        registry = registry_module.load(paths.registry)
        source = registry.get(item.split(":", 1)[1])
        source["status"] = target
        registry_module.save(registry)
    if kind == "age_band" and decision in FINAL:
        # The review tool enforces the transition, reviewer qualification and conflicts, and audits it.
        review.transition(paths.drafts, item, decision, actor, audit_path=paths.audit,
                          reviewers_path=paths.reviewers, reason=entry["note"] or "",
                          decision_id=entry["decision_id"])
    else:
        audit.append(paths.audit, actor=actor, action=f"decision.{decision}", item=item, from_state=previous,
                     to_state=target, reason=f"{entry['decision_id']}: {entry['note']}")
    state["items"][item] = {"status": target, "decided_by": actor, "role": entry["role"],
                            "date": str(entry["date"]), "decision_id": entry["decision_id"]}


def known_items(root: Path) -> frozenset:
    items = {"reviewers", "adr-0005"}
    reg = registry_module.load(root / "corpus/sources/registry.yaml")
    items |= {f"source:{s['source_id']}" for s in reg.sources}
    items |= {f"policy-{p.stem}" for p in (root / "doc/governance").glob("*.md")}
    items |= {f"section18:{key}" for key in ("age_band", "market", "language", "curriculum", "madhhab_scope",
                                              "voice", "business_model", "devices")}
    selection = yaml.safe_load((root / "corpus/candidate/hadith_selection.yaml").read_text(encoding="utf-8"))
    items |= {f"selection-{n:02d}" for n in range(1, len(selection["hadith"]) + 1)}
    for path in (root / "corpus/candidate/prophets").glob("*_source_map.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items |= {f"map-{data['prophet_id']}-{n:02d}" for n in range(1, len(data["ranges"]) + 1)}
    for name in ("gold.jsonl", "harmful.jsonl"):
        items |= {json.loads(line)["id"] for line in (root / "corpus/eval" / name).open(encoding="utf-8")}
    items |= {item.item_id for item in review.items(root / "corpus/drafts/age_band")}
    return frozenset(items)


def status_of(state_path: Path, item: str) -> str:
    return _load_state(state_path)["items"].get(item, {}).get("status", "pending")


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
