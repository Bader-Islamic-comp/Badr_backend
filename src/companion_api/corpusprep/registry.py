"""The source registry, `corpus/sources/registry.yaml`: one entry per downloaded file."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import yaml

SCHEMA_VERSION = 1
STATUSES = ("candidate", "pending_legal", "rejected")
FORMATS = ("txt", "xml", "json", "csv")
REQUIRED = ("source_id", "title", "edition", "publisher", "url", "license", "license_url", "terms_summary",
            "retrieved_at", "sha256", "numbering_system", "status", "notes")
OPTIONAL = ("dataset", "role", "format")
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

_HEADER_END = "schema_version:"


class RegistryError(ValueError):
    pass


@dataclass
class Registry:
    path: Path
    header: str
    sources: list[dict]

    def get(self, source_id: str) -> dict:
        for source in self.sources:
            if source["source_id"] == source_id:
                return source
        raise KeyError(source_id)

    @property
    def digest(self) -> str:
        return sha256(self.path.read_bytes()).hexdigest()


def validate(data) -> list[str]:
    """Every problem in one pass, as `source_id: field: message`."""
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return [f"registry: schema_version must be {SCHEMA_VERSION}"]
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["registry: sources must be a non-empty list"]
    problems, seen = [], set()
    for position, source in enumerate(sources, 1):
        name = f"sources[{position}]"
        if not isinstance(source, dict):
            problems.append(f"{name}: must be a mapping")
            continue
        sid = source.get("source_id")
        if isinstance(sid, str) and SOURCE_ID.match(sid):
            name = sid
            if sid in seen:
                problems.append(f"{sid}: source_id: used twice")
            seen.add(sid)
        else:
            problems.append(f"{name}: source_id: must be lowercase a-z, 0-9 and '-'")
        for key in REQUIRED:
            if key not in source:
                problems.append(f"{name}: {key}: is required (use null when unknown)")
        for key in source:
            if key not in REQUIRED + OPTIONAL:
                problems.append(f"{name}: {key}: unknown field")
        if source.get("status") not in STATUSES:
            problems.append(f"{name}: status: must be one of {', '.join(STATUSES)}")
        if source.get("format") not in FORMATS:
            problems.append(f"{name}: format: must be one of {', '.join(FORMATS)}")
        digest = source.get("sha256")
        if digest is not None and not (isinstance(digest, str) and SHA256.match(digest)):
            problems.append(f"{name}: sha256: must be 64 lowercase hex characters or null")
        if (digest is None) != (source.get("retrieved_at") is None):
            problems.append(f"{name}: sha256 and retrieved_at are recorded together")
        for key in ("url", "title", "license", "terms_summary", "numbering_system"):
            if not isinstance(source.get(key), str) or not source.get(key, "").strip():
                problems.append(f"{name}: {key}: must be non-empty text")
        if source.get("status") == "candidate" and not source.get("notes"):
            problems.append(f"{name}: notes: a candidate source must say why its licence is unclear")
    return problems


def load(path) -> Registry:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    problems = validate(data)
    if problems:
        raise RegistryError("registry is invalid:\n  " + "\n  ".join(problems))
    header = text[:text.index(_HEADER_END)] if _HEADER_END in text else ""
    return Registry(path, header, data["sources"])


def save(registry: Registry) -> None:
    """Rewrites the registry keeping its header comment and field order."""
    body = yaml.safe_dump({"schema_version": SCHEMA_VERSION, "sources": registry.sources}, allow_unicode=True,
                          sort_keys=False, width=1000)
    problems = validate(yaml.safe_load(body))
    if problems:
        raise RegistryError("refusing to save an invalid registry:\n  " + "\n  ".join(problems))
    registry.path.write_text(registry.header + body, encoding="utf-8", newline="\n")
