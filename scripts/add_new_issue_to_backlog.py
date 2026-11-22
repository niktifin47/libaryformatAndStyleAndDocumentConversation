"""Classify a newly opened feature/idea as backlog work without changing milestones."""

import json
import os
import subprocess
from pathlib import Path


def run(*command: str) -> str:
    return subprocess.run(
        command, check=True, stdout=subprocess.PIPE, text=True
    ).stdout.strip()


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event["issue"]
    repository = event["repository"]["full_name"]
    number = issue["number"]
    labels = {label["name"] for label in issue.get("labels", [])}
    issue_type = issue.get("type")
    issue_type_name = (
        issue_type.get("name") if isinstance(issue_type, dict)
        else issue.get("issue_type")
    )
    is_feature = (
        "enhancement" in labels
        or issue_type_name == "Feature"
        or issue_type_name == "feature"
    )
    if (
        "objective" in labels
        or "roadmap" in labels
        or not is_feature
    ):
        return
    run(
        "gh",
        "issue",
        "edit",
        str(number),
        "--repo",
        repository,
        "--add-label",
        "enhancement",
    )
    run(
        "gh",
        "issue",
        "comment",
        str(number),
        "--repo",
        repository,
        "--body",
        "Recorded in the backlog with the `enhancement` label. "
        "This did not change any milestone or roadmap structure; "
        "roadmap changes require personal approval.",
    )


if __name__ == "__main__":
    main()
