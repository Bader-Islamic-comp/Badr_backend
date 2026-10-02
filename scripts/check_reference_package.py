"""Check the registry against the challenge's reference package and generate its governance page.

    python scripts/check_reference_package.py           check; print a summary by package rule
    python scripts/check_reference_package.py --write   also regenerate doc/governance/reference-package.md

Exit status: 0 when the check passes, 1 when it fails (each problem is printed), 2 when a file cannot be read.
What is checked is described in src/companion_api/corpusprep/reference_package.py. Warnings never fail it.
"""
import argparse
import sys

import _common  # noqa: F401
from _common import REGISTRY, ROOT
from companion_api.corpusprep import reference_package, registry as registry_module

PACKAGE = ROOT / "corpus/sources/reference_package.yaml"
DOC = ROOT / "doc/governance/reference-package.md"


def summary(sources: list[dict], package: dict, report: reference_package.Report) -> list[str]:
    lines = [f"{len(sources)} registry sources against the reference package "
             f"(version {(package.get('package') or {}).get('version')}):",
             f"  {'package rule':<16} {'sources':>7}  registry status / acquisition"]
    for rule in (*registry_module.PACKAGE_RULES, "missing"):
        if rule in report.by_rule:
            entry = report.by_rule[rule]
            lines.append(f"  {rule:<16} {entry['sources']:>7}  {reference_package.counts(entry['status'])} / "
                         f"{reference_package.counts(entry['acquisition'])}")
    lines.append(f"  organizers' rulings recorded: {len(package.get('rulings') or [])}")
    lines += [f"warning: {warning}" for warning in report.warnings]
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", default=REGISTRY)
    parser.add_argument("--package", default=PACKAGE)
    parser.add_argument("--write", action="store_true", help="regenerate doc/governance/reference-package.md")
    args = parser.parse_args(argv)
    try:
        registry = registry_module.load(args.registry)
        package = reference_package.load(args.package)
    except (registry_module.RegistryError, reference_package.PackageError, OSError) as error:
        print(error, file=sys.stderr)
        return 2
    report = reference_package.check(registry.sources, package, ROOT)
    print("\n".join(summary(registry.sources, package, report)))
    if args.write:
        DOC.write_text(reference_package.render(registry.sources, package, report), encoding="utf-8", newline="\n")
        print(f"wrote {DOC.relative_to(ROOT)}")
    if report.problems:
        print(f"FAILED ({len(report.problems)} problems):\n  " + "\n  ".join(report.problems), file=sys.stderr)
        return 1
    print("check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
