"""Signed decisions: a decision applies only if git shows the person it names signed it (test/corpus-tasks).

`doc/decisions/decisions.yaml` used to be trusted on its typed `decided_by`, so
anyone able to push could write "Mousa al-Rashdan" and approve a source. Now
every line of a decision entry must come from a commit that is SSH-signed by
the key registered for that person in `corpus/governance/signers.yaml`:

    signers:
    - name: Mousa al-Rashdan              # exactly as written in decided_by
      principal: mousa@example.org        # any id without spaces; git prints it as the signer
      key: ssh-ed25519 AAAA... comment    # the public key, one line

The check reads the repository itself (`git blame` for the commits that wrote
the entry, `git log %G?/%GS` against an allowed-signers file built from
`signers.yaml`), so it cannot be satisfied by editing the decisions file
alone. `signers.yaml` itself belongs under code-owner review (`.github/CODEOWNERS`),
because adding a key is how a person becomes able to sign. An uncommitted or
unsigned entry, an unknown signer and a signature by someone other than
`decided_by` are each refusals.

Signing a decision (once per machine):

    git config gpg.format ssh
    git config user.signingkey ~/.ssh/id_ed25519.pub
    git commit -S -m "D-0001: ..."
"""
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

_SHA = re.compile(r"^([0-9a-f]{40}) \d+ \d+")
_UNCOMMITTED = "0" * 40


class SignatureError(RuntimeError):
    pass


def load_signers(path: Path) -> dict[str, dict]:
    """name -> {principal, key}; an empty mapping when the file is missing or lists nobody."""
    if not Path(path).is_file():
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    signers = {}
    for entry in data.get("signers") or []:
        name, principal, key = entry.get("name"), entry.get("principal"), entry.get("key")
        if not (isinstance(name, str) and isinstance(principal, str) and isinstance(key, str)) \
                or " " in principal.strip() or not key.startswith("ssh-"):
            raise SignatureError(f"signers.yaml: invalid entry for {name!r} (name, principal without spaces, ssh key)")
        signers[name.strip()] = {"principal": principal.strip(), "key": key.strip()}
    return signers


def entry_lines(text: str) -> dict[str, tuple[int, int]]:
    """decision_id -> (first line, last line), 1-based, of each entry of the `decisions` list."""
    root = yaml.compose(text)
    if root is None:
        return {}
    ranges = {}
    for key, value in root.value:
        if key.value != "decisions" or not hasattr(value, "value") or not isinstance(value.value, list):
            continue
        for item in value.value:
            fields = {k.value: v for k, v in item.value} if isinstance(item.value, list) else {}
            node = fields.get("decision_id")
            if node is not None:
                # end_mark points just past the item; a trailing newline puts it on the next line's column 0.
                end = item.end_mark.line if item.end_mark.column else item.end_mark.line - 1
                ranges[str(node.value)] = (item.start_mark.line + 1, end + 1)
    return ranges


def _git(repo: Path, *args: str, config: tuple[str, ...] = ()) -> str:
    command = ["git", "-C", str(repo)]
    for setting in config:
        command += ["-c", setting]
    result = subprocess.run(command + list(args), capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise SignatureError(f"git {args[0]} failed ({result.returncode})")
    return result.stdout


def _commits(repo: Path, relative: str, first: int, last: int) -> set[str]:
    porcelain = _git(repo, "blame", "--porcelain", "-L", f"{first},{last}", "--", relative)
    return {match.group(1) for line in porcelain.splitlines() if (match := _SHA.match(line))}


def check(decisions_path: Path, entries: list[dict], signers_path: Path, repo: Path) -> dict[str, list[str]]:
    """decision_id -> problems with its signatures; an empty dict when every entry is properly signed."""
    decisions_path, repo = Path(decisions_path).resolve(), Path(repo).resolve()
    try:
        signers = load_signers(signers_path)
        relative = decisions_path.relative_to(repo).as_posix()
        lines = entry_lines(decisions_path.read_text(encoding="utf-8"))
    except (SignatureError, ValueError, yaml.YAMLError) as error:
        return {"signatures": [str(error)]}
    problems: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory() as folder:
        allowed = Path(folder) / "allowed_signers"
        allowed.write_text("".join(f'{signer["principal"]} namespaces="git" {signer["key"]}\n'
                                   for signer in signers.values()), encoding="utf-8")
        config = ("gpg.format=ssh", f"gpg.ssh.allowedSignersFile={allowed.as_posix()}")
        verified: dict[str, tuple[str, str]] = {}
        for entry in entries:
            decision_id = str(entry.get("decision_id"))
            name = str(entry.get("decided_by", "")).strip()
            found = []
            signer = signers.get(name)
            if signer is None:
                found.append(f"no signing key is registered for {name} in signers.yaml")
            elif decision_id not in lines:
                found.append("entry not found in the decisions file")
            else:
                try:
                    commits = _commits(repo, relative, *lines[decision_id])
                except SignatureError as error:
                    commits = set()
                    found.append(f"{error}: is the decisions file committed?")
                if _UNCOMMITTED in commits:
                    found.append("has uncommitted lines; commit it with a signature (git commit -S)")
                for sha in sorted(commits - {_UNCOMMITTED}):
                    if sha not in verified:
                        status, principal = (_git(repo, "log", "-1", "--format=%G?%x00%GS", sha, config=config)
                                             .strip().split("\x00") + [""])[:2]
                        verified[sha] = (status, principal)
                    status, principal = verified[sha]
                    if status != "G":
                        found.append(f"commit {sha[:10]} is not signed by a registered key (status {status or 'N'})")
                    elif principal != signer["principal"]:
                        found.append(f"commit {sha[:10]} is signed by {principal}, not by {name}")
            if found:
                problems[decision_id] = found
    return problems
