"""Generate a weekly project-progress summary without changing milestones."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone


def run(*command: str) -> str:
    return subprocess.run(
        command, check=True, stdout=subprocess.PIPE, text=True
    ).stdout.strip()


def api_pages(endpoint: str) -> list[dict]:
    output = run("gh", "api", "--paginate", "--slurp", endpoint)
    result = json.loads(output)
    return [item for page in result for item in page]


def issue_comment_marker(repository: str, issue_number: int) -> str:
    return f"<!-- automated-progress-check:{repository}#{issue_number} -->"


def get_open_objectives(repository: str) -> list[dict]:
    pages = api_pages(f"repos/{repository}/issues?state=open&per_page=100")
    return [
        issue
        for issue in pages
        if not issue.get("pull_request")
        and any(label.get("name") == "objective" for label in issue.get("labels", []))
    ]


def get_recent_merged(repository: str, since: datetime) -> list[dict]:
    pulls = api_pages(f"repos/{repository}/pulls?state=closed&sort=updated&direction=desc&per_page=100")
    return [
        pull
        for pull in pulls
        if pull.get("merged_at")
        and datetime.fromisoformat(pull["merged_at"].replace("Z", "+00:00")) >= since
    ]


def get_task_counts(repository: str) -> tuple[int, int]:
    issues = api_pages(f"repos/{repository}/issues?state=all&per_page=100")
    tasks = [
        issue
        for issue in issues
        if not issue.get("pull_request")
        and not any(label.get("name") == "objective" for label in issue.get("labels", []))
    ]
    completed = sum(issue["state"] == "closed" for issue in tasks)
    return completed, len(tasks)


def build_summary(repository: str, since: datetime) -> str:
    merged = get_recent_merged(repository, since)
    completed, task_total = get_task_counts(repository)
    objective_count = len(get_open_objectives(repository))
    progress = round(completed / task_total * 100) if task_total else 0

    lines = [
        "## Automated progress summary",
        "",
        f"- Reporting period: {since.date().isoformat()} to {datetime.now(timezone.utc).date().isoformat()}",
        f"- Open objectives: {objective_count}",
        f"- Merged pull requests: {len(merged)}",
        f"- Task completion: {completed}/{task_total} ({progress}%)",
        "",
        "### Merged changes",
    ]
    if merged:
        for pull in merged:
            lines.append(f"- #{pull['number']} {pull['title']}")
    else:
        lines.append("- No merged pull requests in this period.")
    lines.extend(
        [
            "",
            (
                "This summary reports observed progress only. "
                "Small changes do not alter milestones or roadmap structure."
            ),
            "",
            "Roadmap or milestone changes require personal approval.",
        ]
    )
    return "\n".join(lines)


def upsert_objective_comment(repository: str, objective: dict, body: str) -> None:
    number = objective["number"]
    marker = issue_comment_marker(repository, number)
    pages = api_pages(f"repos/{repository}/issues/{number}/comments?per_page=100")
    existing = next(
        (
            comment
            for comment in pages
            if marker in comment.get("body", "")
            and comment.get("user", {}).get("login") == "github-actions[bot]"
        ),
        None,
    )
    marker_body = f"{marker}\n{body}"
    if existing:
        run(
            "gh",
            "api",
            "--method",
            "PATCH",
            f"repos/{repository}/issues/comments/{existing['id']}",
            "-f",
            f"body={marker_body}",
        )
    else:
        run(
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repository}/issues/{number}/comments",
            "-f",
            f"body={marker_body}",
        )


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    since = datetime.now(timezone.utc) - timedelta(days=7)
    objectives = get_open_objectives(repository)
    if not objectives:
        print("No open objective issue found; progress summary was not posted.")
        return
    body = build_summary(repository, since)
    for objective in objectives:
        upsert_objective_comment(repository, objective, body)


if __name__ == "__main__":
    main()
