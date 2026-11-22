import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "add_new_issue_to_backlog.py"
spec = importlib.util.spec_from_file_location("add_new_issue_to_backlog", SCRIPT)
assert spec is not None and spec.loader is not None
backlog_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backlog_script)


def test_new_feature_uses_existing_backlog_label(monkeypatch, tmp_path):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "repository": {"full_name": "owner/repo"},
                "issue": {
                    "number": 40,
                    "labels": [],
                    "type": {"name": "Feature"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    calls = []
    monkeypatch.setattr(backlog_script, "run", lambda *args: calls.append(args))
    backlog_script.main()
    assert ("gh", "issue", "edit", "40", "--repo", "owner/repo", "--add-label", "enhancement") in calls
    assert not any("remove-milestone" in call for call in calls)
