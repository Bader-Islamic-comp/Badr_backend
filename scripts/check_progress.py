"""Three-way progress check: doc/done.md against the evidence, the architecture/plan and the task list.

    python scripts/check_progress.py [--no-run] [--timeout 600]

1. Every evidence path in done.md exists (globs must match) and every evidence command runs (exit 0).
2. Every numbered section of doc/architecture.md and every component of doc/plan.md has a row.
3. Every task in doc/corpus-tasks.md has a row, and no row claims more than the task's own status.
Prints done, missing, conflicts and items marked done without evidence; exit 1 on any conflict.
"""
import argparse
import glob
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "doc"
STATUSES = ("not_started", "in_progress", "draft_ready", "done_pending_approval", "blocked")
ORDER = {status: rank for rank, status in enumerate(("not_started", "blocked", "in_progress", "draft_ready",
                                                     "done_pending_approval"))}
DONE = ("done_pending_approval",)
PATH_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".json", ".jsonl", ".csv", ".tsv", ".txt", ".html")
COMMAND_START = ("python", "python3", "PYTHONPATH=")


def rows(path: Path) -> list[dict]:
    table = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] not in ("id", "---") and not set(cells[0]) <= {"-"}:
            table.append(dict(zip(("id", "item", "ref", "status", "evidence", "tasks", "updated"), cells)))
    return table


def evidence(cell: str) -> tuple[list[str], list[str]]:
    spans = re.findall(r"`([^`]+)`", cell)
    commands = [span for span in spans if span.startswith(COMMAND_START)]
    paths = [span for span in spans if span not in commands and ("/" in span or span.endswith(PATH_SUFFIXES))]
    return paths, commands


def run(command: str, timeout: int) -> tuple[bool, str]:
    env = dict(os.environ)
    words = shlex.split(command)
    while words and "=" in words[0] and not words[0].startswith("-"):
        key, value = words.pop(0).split("=", 1)
        env[key] = value
    if words and words[0] in ("python", "python3"):
        words[0] = sys.executable
    try:
        done = subprocess.run(words, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except OSError as error:
        return False, str(error)
    tail = (done.stdout + done.stderr).strip().splitlines()[-1:] or [""]
    return done.returncode == 0, f"exit {done.returncode}: {tail[0][:160]}"


def task_statuses() -> dict[str, str]:
    text = (DOC / "corpus-tasks.md").read_text(encoding="utf-8")
    statuses = {}
    for match in re.finditer(r"^### (\d+)\. .*?(?=^### |\Z)", text, re.M | re.S):
        found = re.search(r"\*\*الحالة:\*\*\s*([a-z_]+)", match.group(0))
        statuses[match.group(1)] = found.group(1) if found else "missing"
    return statuses


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-run", action="store_true", help="check paths only, do not run evidence commands")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    table = rows(DOC / "done.md")
    conflicts, without_evidence, done_items, missing = [], [], [], []

    ran: dict[str, tuple[bool, str]] = {}
    for row in table:
        label = f"[{row['id']}] {row['item'][:60]}"
        if row["status"] not in STATUSES:
            conflicts.append(f"{label}: unknown status {row['status']!r}")
        paths, commands = evidence(row["evidence"])
        if row["status"] in DONE + ("draft_ready",) and not paths and not commands:
            without_evidence.append(label)
        for path in paths:
            if not glob.glob(str(ROOT / path)):
                conflicts.append(f"{label}: evidence path {path} does not exist")
        for command in commands:
            if args.no_run:
                continue
            if command not in ran:
                print(f"running: {command}", file=sys.stderr, flush=True)
                ran[command] = run(command, args.timeout)
            ok, detail = ran[command]
            if not ok:
                conflicts.append(f"{label}: evidence command failed ({detail}): {command}")
        (done_items if row["status"] in DONE + ("draft_ready",) else missing).append(f"{label} — {row['status']}")

    architecture = {m for m in re.findall(r"^## (\d+)\.", (DOC / "architecture.md").read_text(encoding="utf-8"), re.M)}
    plan = set(re.findall(r"^## المكوّن (\d+)", (DOC / "plan.md").read_text(encoding="utf-8"), re.M))
    covered_arch = {m for row in table for m in re.findall(r"architecture §(\d+)", row["ref"])}
    covered_plan = {m for row in table for m in re.findall(r"plan مكوّن (\d+)", row["ref"])}
    for number in sorted(architecture - covered_arch, key=int):
        conflicts.append(f"architecture §{number} has no row in done.md")
    for number in sorted(plan - covered_plan, key=int):
        conflicts.append(f"plan component {number} has no row in done.md")

    tasks = task_statuses()
    covered_tasks: dict[str, list[dict]] = {}
    for row in table:
        for number in re.findall(r"\d+", row["tasks"]):
            covered_tasks.setdefault(number, []).append(row)
    for number, status in sorted(tasks.items(), key=lambda item: int(item[0])):
        if status not in STATUSES:
            conflicts.append(f"task {number} in corpus-tasks.md has status {status!r}")
        if number not in covered_tasks:
            conflicts.append(f"task {number} has no row in done.md")
            continue
        for row in covered_tasks[number]:
            if status in ORDER and row["status"] in ORDER and ORDER[row["status"]] > ORDER[status] \
                    and row["tasks"].strip() == number:
                conflicts.append(f"[{row['id']}] is {row['status']} but task {number} is only {status}")
    for number in covered_tasks:
        if number not in tasks:
            conflicts.append(f"done.md cites task {number}, which is not in corpus-tasks.md")

    print(f"Done or ready for approval ({len(done_items)}):")
    print("\n".join(f"  {item}" for item in done_items) or "  none")
    print(f"\nMissing / not yet done ({len(missing)}):")
    print("\n".join(f"  {item}" for item in missing) or "  none")
    print(f"\nMarked done without evidence ({len(without_evidence)}):")
    print("\n".join(f"  {item}" for item in without_evidence) or "  none")
    print(f"\nConflicts ({len(conflicts)}):")
    print("\n".join(f"  {item}" for item in conflicts) or "  none")
    print(f"\nTasks: {len(tasks)} in corpus-tasks.md; architecture sections {len(architecture)}, plan components "
          f"{len(plan)}; evidence commands run: {0 if args.no_run else len(ran)}")
    return 1 if conflicts or without_evidence else 0


if __name__ == "__main__":
    sys.exit(main())
