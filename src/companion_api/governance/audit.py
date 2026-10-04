"""Append-only audit trail with a hash chain (governance task 7).

Each line is one JSON event. Its `hash` is sha256 over the event without the
hash, and every event carries the previous event's hash, so editing, deleting,
inserting or reordering any line breaks the chain from that point on and
`verify` names the first broken line. Events hold ids, names and states,
never content text or child data.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

GENESIS = "0" * 64
FIELDS = ("seq", "at", "actor", "action", "item", "from_state", "to_state", "reason", "prev_hash")


class AuditError(RuntimeError):
    pass


def _digest(event: dict) -> str:
    body = {key: event[key] for key in FIELDS}
    return sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Verification:
    ok: bool
    events: int
    problem: str | None = None


def _read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise AuditError(f"line {number} is blank")
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            raise AuditError(f"line {number} is not JSON") from None
    return events


def head(path: Path) -> dict | None:
    """The last event's `{"seq", "hash"}`: an anchor to keep outside the file (test/corpus-tasks).

    A hash chain shows an edit, an insertion or a reordering, but not lost final
    events or a whole file rewritten consistently. An anchor kept elsewhere (a
    committed anchor file, a release manifest) closes both: `verify` then needs
    the trail to reach that event with that hash.
    """
    events = _read(Path(path))
    return {"seq": events[-1]["seq"], "hash": events[-1]["hash"]} if events else None


def verify(path: Path, anchors=()) -> Verification:
    """The chain checked end to end, and against every anchor (`head` values recorded earlier)."""
    try:
        events = _read(Path(path))
    except AuditError as error:
        return Verification(False, 0, str(error))
    result = _verify_chain(events)
    if not result.ok:
        return result
    for anchor in anchors:
        if not anchor:
            continue
        seq, digest = anchor.get("seq"), anchor.get("hash")
        if not isinstance(seq, int) or seq > len(events):
            return Verification(False, len(events), f"the trail ends at event {len(events)} but an anchor records "
                                                    f"event {seq}: events were removed")
        if events[seq - 1]["hash"] != digest:
            return Verification(False, len(events), f"event {seq} does not match its anchor: the trail was rewritten")
    return result


def _verify_chain(events: list[dict]) -> Verification:
    previous = GENESIS
    for number, event in enumerate(events, 1):
        if set(event) != set(FIELDS) | {"hash"}:
            return Verification(False, len(events), f"line {number} has unexpected fields")
        if event["seq"] != number:
            return Verification(False, len(events), f"line {number} has seq {event['seq']} (lines removed, "
                                                    "inserted or reordered)")
        if event["prev_hash"] != previous:
            return Verification(False, len(events), f"line {number} does not follow line {number - 1}")
        if _digest(event) != event["hash"]:
            return Verification(False, len(events), f"line {number} was modified after it was written")
        previous = event["hash"]
    return Verification(True, len(events))


def append(path: Path, *, actor: str, action: str, item: str, from_state: str | None, to_state: str | None,
           reason: str = "", at: str | None = None) -> dict:
    """Appends one event after verifying the chain; refuses to extend a broken trail."""
    path = Path(path)
    state = verify(path)
    if not state.ok:
        raise AuditError(f"audit trail {path} is broken ({state.problem}); nothing was appended")
    if not actor or not actor.strip():
        raise AuditError("every audit event needs an actor")
    events = _read(path)
    event = {"seq": len(events) + 1, "at": at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
             "actor": actor.strip(), "action": action, "item": item, "from_state": from_state,
             "to_state": to_state, "reason": reason, "prev_hash": events[-1]["hash"] if events else GENESIS}
    event["hash"] = _digest(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event
