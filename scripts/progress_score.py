"""Progress out of 100 over the 15 corpus tasks (doc/progress_items.yaml).

    python scripts/progress_score.py [--no-run] [--write]

Every task weighs 100/15. Inside a task, items are weighted; an M item counts only when its evidence paths
exist, its commands exit 0 and (for history_methods) the latest retrieval run measured those methods; an H
item counts only when every matching decision item has an applied final decision and an audit event.
Prints X (total) = Y (automated) + Z (human). --write updates the "التقدم" section of doc/done.md and
reports/progress/score.json (read by the dashboard).
"""
from datetime import datetime, timezone
import fnmatch
import glob
import json
import re
import sys

import yaml

import _common  # noqa: F401
from _common import CONTENT_AUDIT, ROOT
from check_progress import COMMAND_START, run
from companion_api.governance import decisions

TASKS = 15
FINAL_STATES = ("approved", "rejected", "cleared")


def _audited_items() -> set[str]:
    if not CONTENT_AUDIT.is_file():
        return set()
    return {json.loads(line)["item"] for line in CONTENT_AUDIT.read_text(encoding="utf-8").splitlines() if line}


def _latest_methods() -> set[str]:
    path = ROOT / "reports/retrieval/history.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return set(json.loads(lines[-1])["methods"]) if lines else set()


def decision_state() -> dict:
    path = ROOT / "corpus/governance/decision_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"items": {}}


def check_automated(item: dict, *, no_run: bool, ran: dict, methods: set = frozenset()) -> tuple[bool, str]:
    """An M item: every evidence path exists and every command exits 0 (`ran` caches commands across items)."""
    ok, reason = True, ""
    for evidence in item.get("evidence", []):
        if evidence.startswith(COMMAND_START):
            if no_run:
                continue
            if evidence not in ran:
                ran[evidence] = run(evidence, 600)
            if not ran[evidence][0]:
                ok, reason = False, f"command failed: {evidence}"
        elif not glob.glob(str(ROOT / evidence)):
            ok, reason = False, f"missing {evidence}"
    lacking = [m for m in item.get("history_methods", []) if m not in methods]
    if lacking:
        ok, reason = False, f"not measured: {', '.join(lacking)}"
    return ok, reason


def check_human(item: dict, *, known, state: dict, audited: set) -> tuple[bool, str]:
    """An H item: every decision item its patterns match has an applied final decision and an audit event."""
    matched = [i for i in known if any(fnmatch.fnmatchcase(i, pattern) for pattern in item["decisions"])]
    undecided = [i for i in matched if state["items"].get(i, {}).get("status") not in FINAL_STATES
                 or i not in audited]
    reason = f"{len(undecided)}/{len(matched)} items without an applied, audited decision"
    return bool(matched) and not undecided, reason


def score(no_run: bool = False) -> dict:
    config = yaml.safe_load((ROOT / "doc/progress_items.yaml").read_text(encoding="utf-8"))["tasks"]
    state = decision_state()
    known = sorted(decisions.known_items(ROOT))
    audited, methods, ran = _audited_items(), _latest_methods(), {}
    rows, total_m, total_h, possible_m = [], 0.0, 0.0, 0.0
    for task in range(1, TASKS + 1):
        items = config[task]
        weights = sum(item["weight"] for item in items)
        share = 100 / TASKS / weights
        m_done = h_done = 0.0
        missing = []
        for item in items:
            if item["kind"] == "M":
                possible_m += item["weight"] * share
                ok, reason = check_automated(item, no_run=no_run, ran=ran, methods=methods)
            else:
                ok, reason = check_human(item, known=known, state=state, audited=audited)
            if ok:
                if item["kind"] == "M":
                    m_done += item["weight"] * share
                else:
                    h_done += item["weight"] * share
            else:
                missing.append({"id": item["id"], "kind": item["kind"], "text": item["text"],
                                "owner": item.get("owner", "Momen Alhamza (automated)"), "why": reason})
        rows.append({"task": task, "total": round((m_done + h_done) * TASKS, 1), "automated": round(m_done * TASKS, 1),
                     "human": round(h_done * TASKS, 1), "missing": missing})
        total_m += m_done
        total_h += h_done
    return {"computed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "total": round(total_m + total_h, 1), "automated": round(total_m, 1), "human": round(total_h, 1),
            "automated_possible": round(possible_m, 1), "human_possible": round(100 - possible_m, 1),
            "commands_run": 0 if no_run else len(ran), "tasks": rows}


def _names() -> dict[int, str]:
    text = (ROOT / "doc/corpus-tasks.md").read_text(encoding="utf-8")
    return {int(n): title for n, title in re.findall(r"^### (\d+)\. (.+)$", text, re.M)}


def render(result: dict) -> str:
    names = _names()
    lines = [f"التقدم الكلي: **{result['total']} / 100** — الآلي {result['automated']} / "
             f"{result['automated_possible']} ممكن، والبشري {result['human']} / {result['human_possible']} ممكن "
             f"(حُسب {result['computed_at']} بـ `python3 scripts/progress_score.py`).", "",
             "| # | التاسك | الكلي | الآلي | البشري | الناقص (صاحبه) |", "| --- | --- | ---: | ---: | ---: | --- |"]
    for row in result["tasks"]:
        missing = "؛ ".join(f"{m['id']} {m['text']} ({m['owner']})" for m in row["missing"]) or "—"
        lines.append(f"| {row['task']} | {names.get(row['task'], '')} | {row['total']} | {row['automated']} | "
                     f"{row['human']} | {missing} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    result = score(no_run="--no-run" in args)
    print(f"Total progress: {result['total']} / 100")
    print(f"Automated part: {result['automated']} / 100 (of {result['automated_possible']} possible)")
    print(f"Human part:     {result['human']} / 100 (of {result['human_possible']} possible)")
    for row in result["tasks"]:
        print(f"  task {row['task']:>2}: total {row['total']:>5}  M {row['automated']:>5}  H {row['human']:>5}  "
              f"missing: {', '.join(m['id'] for m in row['missing']) or '-'}")
    if "--write" in args:
        out = ROOT / "reports/progress"
        out.mkdir(parents=True, exist_ok=True)
        (out / "score.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        done = ROOT / "doc/done.md"
        text = done.read_text(encoding="utf-8")
        section = "## التقدم\n\n" + render(result) + "\n"
        text = re.sub(r"## التقدم\n.*?(?=\n## |\Z)", section.rstrip("\n"), text, flags=re.S) \
            if "## التقدم" in text else text.rstrip("\n") + "\n\n" + section
        done.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
