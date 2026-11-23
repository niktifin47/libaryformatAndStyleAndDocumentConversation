import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_coverage.py"


def run_gate(platform: str, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), platform, str(report)],
        capture_output=True,
        text=True,
        check=False,
    )


def python_report(color_covered: int = 10) -> str:
    totals = {
        "covered_lines": 10,
        "num_statements": 10,
        "covered_branches": 10,
        "num_branches": 10,
    }
    return json.dumps({
        "totals": totals,
        "files": {"src/api_format_fix/color.py": {
            "summary": {**totals, "covered_branches": color_covered}
        }},
    })


def node_report(color_covered: int = 10) -> str:
    total = {"lines": {"covered": 10, "total": 10}, "branches": {"covered": 10, "total": 10}}
    return json.dumps({
        "total": total,
        "repo/src/color.ts": {"branches": {"covered": color_covered, "total": 10}},
    })


def android_report(color_covered: int = 10) -> str:
    return (
        "<report><package><sourcefile name='OklchColor.kt'>"
        f"<counter type='BRANCH' covered='{color_covered}' missed='{10 - color_covered}'/>"
        "</sourcefile></package><counter type='LINE' covered='10' missed='0'/>"
        "<counter type='BRANCH' covered='10' missed='0'/></report>"
    )


@pytest.mark.parametrize(
    ("platform", "make_report"),
    [("python", python_report), ("node", node_report), ("android", android_report)],
)
def test_gate_accepts_good_reports_and_rejects_low_color_coverage(tmp_path, platform, make_report):
    report = tmp_path / "report"
    report.write_text(make_report(), encoding="utf-8")
    assert run_gate(platform, report).returncode == 0
    report.write_text(make_report(8), encoding="utf-8")
    failed = run_gate(platform, report)
    assert failed.returncode != 0
    assert "color branches" in failed.stderr


def test_gate_rejects_missing_empty_and_below_baseline_reports(tmp_path):
    report = tmp_path / "report"
    assert run_gate("python", report).returncode != 0
    report.write_text("{}", encoding="utf-8")
    assert run_gate("python", report).returncode != 0
    report.write_text(python_report().replace('"covered_lines": 10', '"covered_lines": 1'), encoding="utf-8")
    assert "below required minimum" in run_gate("python", report).stderr
    report.write_text(python_report().replace('"num_statements": 10', '"num_statements": 0'), encoding="utf-8")
    assert run_gate("python", report).returncode != 0


def test_shared_fixture_and_gate_changes_trigger_all_platform_checks():
    action = SCRIPT.parents[1] / ".github" / "actions" / "platform-changes" / "action.yml"
    text = action.read_text(encoding="utf-8")
    filters = dict(re.findall(
        r"^          (python|mobile|npm):\n((?:            - .*\n)+)", text, re.MULTILINE
    ))
    assert set(filters) == {"python", "mobile", "npm"}
    for path in ("test-fixtures/oklch.json", "scripts/check_coverage.py"):
        for name, entries in filters.items():
            patterns = re.findall(r"^\s+- '([^']+)'$", entries, re.MULTILINE)
            assert any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), (name, path)
