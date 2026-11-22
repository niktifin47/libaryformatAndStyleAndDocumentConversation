import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "check_project_progress.py"
spec = importlib.util.spec_from_file_location("check_project_progress", SCRIPT)
assert spec is not None and spec.loader is not None
progress_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress_script)


def test_build_summary_has_progress_without_milestone_changes(monkeypatch):
    since = datetime.now(timezone.utc) - timedelta(days=7)
    monkeypatch.setattr(
        progress_script,
        "get_recent_merged",
        lambda repository, report_since: [{"number": 12, "title": "Fix parser"}],
    )
    monkeypatch.setattr(
        progress_script,
        "get_task_counts",
        lambda repository: (3, 4),
    )
    monkeypatch.setattr(
        progress_script,
        "get_open_objectives",
        lambda repository: [{"number": 23}],
    )
    body = progress_script.build_summary("owner/repo", since)
    assert "Task completion: 3/4 (75%)" in body
    assert "#12 Fix parser" in body
    assert "Small changes do not alter milestones" in body
    assert "Roadmap or milestone changes require personal approval" in body
