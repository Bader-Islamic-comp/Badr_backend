"""Writes contracts/openapi-v1.json from the app itself.

The app serves no `/openapi.json`, so the published contract is a file. Writing
it by hand is how it drifts from the routes it describes; this regenerates it,
and `tests/test_api.py` fails when the checked-in copy is out of date.

    python tools/export_contracts.py            # rewrite the server's copy
    python tools/export_contracts.py <path>     # and a consumer's copy too

`comp-mobile/contracts/openapi-v1.json` is the same bytes, so pass its path
when the API changes.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from companion_api.config import Settings  # noqa: E402
from companion_api.main import create_app  # noqa: E402

# Only the shape of the API is published. The operator token never is, so this
# uses a placeholder that is long enough for `require_demo` and nothing else.
PLACEHOLDER_TOKEN = "contract-export-placeholder-token"


def contract() -> str:
    app = create_app(Settings(demo_mode=True, demo_token=PLACEHOLDER_TOKEN))
    document = app.openapi()
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def write(path: Path, text: str) -> bool:
    # CRLF, matching how the checked-in copies are stored.
    data = text.replace("\n", "\r\n").encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def main(argv: list[str]) -> int:
    text = contract()
    targets = [Path(__file__).resolve().parent.parent / "contracts" / "openapi-v1.json"]
    targets += [Path(argument) for argument in argv]
    for target in targets:
        print(("wrote " if write(target, text) else "unchanged ") + str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
