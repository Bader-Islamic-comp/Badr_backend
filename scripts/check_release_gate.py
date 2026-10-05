"""The release gate (doc/governance/release-gate.md): one checklist that must be fully green before
`features.generativeAnswers` or `features.voice` is offered to a child.

    python scripts/check_release_gate.py [--switch generativeAnswers|voice] [--no-run] [--json]

The checklist is corpus/governance/release_gate.yaml. Items are counted the same way as in
scripts/progress_score.py:
- A human item (H) is green when every decision item its patterns match has an applied, audited final decision.
  A `policy-<name>` pattern that matches nothing asks for doc/governance/<name>.md to be written first.
- An automated item (M) is green when its evidence paths exist, its commands exit 0 and its built-in check
  passes.

Prints every item of the switch (both switches by default) with its owner and, when red, why. Exits 0 only when
all are green. `--no-run` skips the commands; a skipped command is not a pass, so the gate stays red.
"""
import json
import sys

import yaml

import _common  # noqa: F401
from _common import ROOT
from check_progress import COMMAND_START
from progress_score import _audited_items, check_automated, check_human, decision_state
from companion_api.governance import decisions
from companion_api.rag.release import POINTER, ReleaseError, load_release

GATE = ROOT / "corpus/governance/release_gate.yaml"
KINDS = ("H", "M")


def published_release() -> tuple[bool, str]:
    """The release the server serves is on the published channel, which `load_release` only accepts with approved,
    non-synthetic content citing cleared sources (rag/release.py)."""
    pointer = ROOT / "releases" / POINTER
    if not pointer.exists():
        return False, f"no releases/{POINTER}"
    try:
        release = load_release(pointer)
    except ReleaseError as error:
        return False, f"release refused: {error}"
    if release.manifest.channel != "published":
        return False, f"{release.manifest.release_id} is on the {release.manifest.channel} channel"
    return True, ""


CHECKS = {"published_release": published_release}


def validate(config: dict) -> list[str]:
    """What is wrong with the checklist itself; empty when it is well formed."""
    problems, seen = [], set()
    switches = set(config.get("switches") or ())
    if not switches:
        problems.append("no switches")
    for item in config.get("items") or ():
        name = item.get("id", "?")
        if name in seen:
            problems.append(f"{name}: duplicate id")
        seen.add(name)
        if item.get("kind") not in KINDS:
            problems.append(f"{name}: kind must be one of {', '.join(KINDS)}")
        if not item.get("text"):
            problems.append(f"{name}: no text")
        gates = set(item.get("gates") or ())
        if not gates or not gates <= switches:
            problems.append(f"{name}: gates must be a non-empty subset of {sorted(switches)}")
        if item.get("kind") == "H" and (not item.get("decisions") or not item.get("owner")):
            problems.append(f"{name}: a human item needs decisions and an owner")
        if item.get("kind") == "M" and not (item.get("evidence") or item.get("check")):
            problems.append(f"{name}: an automated item needs evidence or a check")
        if item.get("check") and item["check"] not in CHECKS:
            problems.append(f"{name}: unknown check {item['check']}")
    return problems


def load(path=GATE) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems = validate(config)
    if problems:
        raise ValueError("release gate: " + "; ".join(problems))
    return config


def evaluate(config: dict, *, switch: str | None = None, no_run: bool = False) -> dict:
    """Every item of `switch` (all items when None), green or red with the reason."""
    state, known, audited, ran = decision_state(), decisions.known_items(ROOT), _audited_items(), {}
    rows = []
    for item in config["items"]:
        if switch is not None and switch not in item["gates"]:
            continue
        if item["kind"] == "H":
            ok, reason = check_human(item, known=known, state=state, audited=audited)
            unwritten = [pattern for pattern in item["decisions"]
                         if pattern.startswith("policy-") and pattern not in known]
            if unwritten:
                ok, reason = False, "write " + ", ".join(f"doc/governance/{p.removeprefix('policy-')}.md"
                                                         for p in unwritten) + ", then decide it"
        else:
            ok, reason = check_automated(item, no_run=no_run, ran=ran)
            if ok and no_run and any(e.startswith(COMMAND_START) for e in item.get("evidence", [])):
                ok, reason = False, "not run (--no-run)"
            if ok and item.get("check"):
                ok, reason = CHECKS[item["check"]]()
        rows.append({"id": item["id"], "kind": item["kind"], "gates": item["gates"], "text": item["text"],
                     "owner": item.get("owner", "automated"), "task": item.get("task", ""), "green": ok,
                     "why": "" if ok else reason})
    return {"switch": switch or "all", "green": bool(rows) and all(row["green"] for row in rows), "items": rows}


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    switch = args[args.index("--switch") + 1] if "--switch" in args else None
    config = load()
    if switch is not None and switch not in config["switches"]:
        print(f"unknown switch {switch}; one of {', '.join(config['switches'])}")
        return 2
    result = evaluate(config, switch=switch, no_run="--no-run" in args)
    if "--json" in args:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        for row in result["items"]:
            mark = "GREEN" if row["green"] else "RED  "
            print(f"{mark} {row['id']} [{row['kind']}] {row['text']} ({row['owner']})")
            if row["why"]:
                print(f"      {row['why']}")
        red = sum(not row["green"] for row in result["items"])
        print(f"release gate ({result['switch']}): {'GREEN' if result['green'] else 'RED'}, "
              f"{len(result['items']) - red} of {len(result['items'])} items green")
    return 0 if result["green"] else 1


if __name__ == "__main__":
    sys.exit(main())
