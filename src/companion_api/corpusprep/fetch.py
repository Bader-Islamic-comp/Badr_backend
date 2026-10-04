"""Download registered sources into `corpus/raw/` and verify them by sha256.

A file is only accepted when its digest equals the registry's. A missing digest
is written only with `record=True` (first download, reviewed by a person); a
different digest is a failure, never an overwrite, because a changed upstream
source is exactly what a reviewer must see before it reaches the corpus.
"""
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Callable

import httpx

Downloader = Callable[[str, Path, float], None]


class SourceChanged(RuntimeError):
    pass


def digest(path: Path) -> str:
    hasher = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            hasher.update(block)
    return hasher.hexdigest()


def raw_path(raw_root: Path, source: dict) -> Path:
    return Path(raw_root) / source["source_id"] / f"{source['source_id']}.{source['format']}"


def http_download(url: str, target: Path, timeout: float, out=sys.stderr, attempts: int = 3) -> None:
    """Streams `url` to `target`, printing progress every 2 MB; retries transport and HTTP errors only."""
    for attempt in range(1, attempts + 1):
        try:
            return _stream(url, target, timeout, out)
        except httpx.HTTPError as error:
            if attempt == attempts:
                raise
            print(f"    retry {attempt}/{attempts - 1} after {type(error).__name__}", file=out, flush=True)
            time.sleep(2 * attempt)


def _stream(url: str, target: Path, timeout: float, out) -> None:
    shown = 0
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "badr-corpus-fetch/1 (+offline corpus preparation)"}) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for block in response.iter_bytes(1 << 16):
                handle.write(block)
                if handle.tell() - shown >= 2 << 20:
                    shown = handle.tell()
                    print(f"    ... {shown / 1e6:.1f} MB", file=out, flush=True)


def ensure(source: dict, raw_root: Path, *, record: bool = False, refresh: bool = False, timeout: float = 120.0,
           download: Downloader = http_download, out=sys.stderr) -> tuple[Path, str]:
    """Returns (path, action) where action is `cached`, `verified` or `recorded`.

    Raises `SourceChanged` when a digest differs from the registry or is not
    recorded yet and `record` is off. Updates `source` in place when recording.
    """
    target = raw_path(raw_root, source)
    expected = source.get("sha256")
    sid = source["source_id"]
    if target.is_file() and not refresh:
        actual = digest(target)
        if expected is None:
            if not record:
                raise SourceChanged(f"{sid}: {target} exists but its sha256 is not in the registry; "
                                    "rerun with --record after reviewing it")
            _record(source, actual)
            return target, "recorded"
        if actual != expected:
            raise SourceChanged(f"{sid}: local raw file {target} does not match the registry "
                                f"(expected {expected}, found {actual}); it was modified after download")
        return target, "cached"
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{sid}.", dir=target.parent)
    os.close(handle)
    temp = Path(temp_name)
    try:
        print(f"  downloading {sid}", file=out, flush=True)
        download(source["url"], temp, timeout)
        actual = digest(temp)
        if expected is None and not record:
            raise SourceChanged(f"{sid}: sha256 is not in the registry; rerun with --record after reviewing "
                                f"the download (got {actual})")
        if expected is not None and actual != expected:
            raise SourceChanged(f"{sid}: SOURCE CHANGED upstream - expected sha256 {expected}, downloaded {actual}. "
                                "Nothing was overwritten. Review the new file, then update the registry "
                                "deliberately (a new edition is a governance decision).")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    if expected is None:
        _record(source, actual)
        return target, "recorded"
    return target, "verified"


def _record(source: dict, actual: str) -> None:
    source["sha256"] = actual
    source["retrieved_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
