"""Verify unrounded line and branch coverage against measured platform baselines."""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def check(label: str, covered: int, total: int, minimum: tuple[int, int]) -> None:
    if not isinstance(covered, int) or not isinstance(total, int) or not 0 <= covered <= total:
        raise ValueError(f"{label}: invalid coverage counts")
    if total == 0:
        raise ValueError(f"{label}: no executable coverage data")
    numerator, denominator = minimum
    print(f"{label}: {covered}/{total} ({covered / total:.4%}), minimum {numerator}/{denominator}")
    if covered * denominator < total * numerator:
        raise ValueError(f"{label}: coverage below required minimum")


def python_report(path: Path) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    total = report["totals"]
    check("Python lines", total["covered_lines"], total["num_statements"], (752, 870))
    check("Python branches", total["covered_branches"], total["num_branches"], (214, 278))
    matches = [
        item["summary"] for name, item in report["files"].items()
        if name.replace("\\", "/").endswith("/api_format_fix/color.py")
    ]
    if len(matches) != 1:
        raise ValueError("Python color coverage is missing or ambiguous")
    check("Python color branches", matches[0]["covered_branches"], matches[0]["num_branches"], (9, 10))


def node_report(path: Path) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    total = report["total"]
    check("Node lines", total["lines"]["covered"], total["lines"]["total"], (2500, 2565))
    check("Node branches", total["branches"]["covered"], total["branches"]["total"], (674, 740))
    matches = [
        item for name, item in report.items()
        if name.replace("\\", "/").endswith("/src/color.ts")
    ]
    if len(matches) != 1:
        raise ValueError("Node color coverage is missing or ambiguous")
    branches = matches[0]["branches"]
    check("Node color branches", branches["covered"], branches["total"], (9, 10))


def android_report(path: Path) -> None:
    root = ET.parse(path).getroot()

    def counts(element: ET.Element, kind: str) -> tuple[int, int]:
        counters = element.findall(f"./counter[@type='{kind}']")
        if len(counters) != 1:
            raise ValueError(f"Android {kind} coverage is missing or ambiguous")
        covered = int(counters[0].attrib["covered"])
        missed = int(counters[0].attrib["missed"])
        return covered, covered + missed

    check("Android lines", *counts(root, "LINE"), (510, 603))
    check("Android branches", *counts(root, "BRANCH"), (221, 330))
    sources = root.findall("./package/sourcefile[@name='OklchColor.kt']")
    if len(sources) != 1:
        raise ValueError("Android color coverage is missing or ambiguous")
    check("Android color branches", *counts(sources[0], "BRANCH"), (9, 10))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("python", "node", "android"))
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        {"python": python_report, "node": node_report, "android": android_report}[args.platform](
            args.report
        )
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print(f"Coverage verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
