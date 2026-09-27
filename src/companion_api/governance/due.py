"""Re-review triggers (governance task 8): which chunks of a release are due for review, and why.

    source_changed        a source's sha256 in the registry differs from the one the release was built from
    source_status_changed a source the chunk cites is now candidate or rejected
    embedding_changed     the configured embedding model differs from the release's
    policy_changed        the governance policy version differs from the release's
    cadence_elapsed       the release is older than the review cadence (approved chunks only)
    never_approved        the chunk is still a draft (reported, not a re-review)
"""
from datetime import datetime, timezone
from pathlib import Path

from ..corpusprep import registry as registry_module
from ..rag.release import load_release

DEFAULT_CADENCE_DAYS = 365  # proposed; the governance owner sets the real value


def due(release_path: Path, registry_path: Path, *, embedding_model: str, policy_version: str,
        cadence_days: int = DEFAULT_CADENCE_DAYS, now: datetime | None = None) -> dict:
    loaded = load_release(release_path)
    manifest = loaded.manifest
    registry = registry_module.load(registry_path)
    current = {source["source_id"]: source for source in registry.sources}
    built_from = manifest.pipeline.get("sourceSha256", {})
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(manifest.created_at)).days
    global_reasons = []
    if manifest.embedder.model != embedding_model:
        global_reasons.append("embedding_changed")
    if manifest.pipeline.get("policyVersion") != policy_version:
        global_reasons.append("policy_changed")
    items, counts = [], {}
    for chunk in loaded.chunks:
        reasons = list(global_reasons)
        for sid in chunk.source_ids:
            source = current.get(sid)
            if source is None or built_from.get(sid) != source["sha256"]:
                reasons.append("source_changed")
            if source is not None and source["status"] in ("candidate", "rejected"):
                reasons.append("source_status_changed")
        if chunk.review_status == "approved":
            if age > cadence_days:
                reasons.append("cadence_elapsed")
        else:
            reasons.append("never_approved")
        reasons = list(dict.fromkeys(reasons))
        for reason in reasons:
            counts[reason] = counts.get(reason, 0) + 1
        if [reason for reason in reasons if reason != "never_approved"]:
            items.append({"chunk_id": chunk.id, "reasons": reasons})
    return {"release_id": manifest.release_id, "release_age_days": age, "cadence_days": cadence_days,
            "chunks": len(loaded.chunks), "due": len(items), "reason_counts": counts, "items": items}
