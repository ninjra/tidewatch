#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Example: Score JIRA issues with tidewatch.

Shows how to map JIRA issue fields to tidewatch Obligation fields
and produce a pressure-ranked queue.

Prerequisites:
    pip install tidewatch requests

Usage:
    export JIRA_URL=https://yourorg.atlassian.net
    export JIRA_TOKEN=your-api-token
    export JIRA_EMAIL=you@company.com
    python examples/jira_integration.py
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tidewatch import Obligation, recalculate_batch


def jira_issue_to_obligation(issue: dict) -> Obligation | None:
    """Map a JIRA issue to a tidewatch Obligation.

    Args:
        issue: JIRA issue dict from REST API /rest/api/3/search

    Returns:
        Obligation, or None if issue has no due date.
    """
    fields = issue["fields"]

    # Skip issues without deadlines — tidewatch requires a due date
    due_str = fields.get("duedate")
    if not due_str:
        return None

    # Parse JIRA date (YYYY-MM-DD) to datetime
    due_date = datetime.strptime(due_str, "%Y-%m-%d").replace(tzinfo=UTC)

    # Map JIRA priority to materiality
    priority_name = (fields.get("priority") or {}).get("name", "Medium")
    materiality = "material" if priority_name in ("Highest", "High", "Critical", "Blocker") else "routine"

    # Count linked issues as dependencies
    links = fields.get("issuelinks", [])
    dep_count = sum(
        1 for link in links
        if link.get("type", {}).get("inward", "").startswith("is blocked by")
        or link.get("type", {}).get("outward", "").startswith("blocks")
    )

    # Map status category to completion estimate
    status_category = (fields.get("status") or {}).get("statusCategory", {}).get("name", "")
    completion_map = {"To Do": 0.0, "In Progress": 0.3, "Done": 1.0}
    completion = completion_map.get(status_category, 0.1)

    # Map JIRA project to domain (customize for your org)
    project_key = (fields.get("project") or {}).get("key", "")
    domain_map = {
        "LEGAL": "legal",
        "FIN": "financial",
        "SEC": "security",
        "OPS": "ops",
        "ENG": "engineering",
    }
    domain = domain_map.get(project_key, "engineering")

    return Obligation(
        id=issue["key"],
        title=fields.get("summary", "Untitled"),
        due_date=due_date,
        materiality=materiality,
        dependency_count=dep_count,
        completion_pct=completion,
        domain=domain,
        status="done" if status_category == "Done" else "active",
    )


def fetch_jira_issues(jql: str = "duedate is not EMPTY ORDER BY duedate ASC") -> list[dict]:
    """Fetch issues from JIRA REST API.

    Requires: JIRA_URL, JIRA_EMAIL, JIRA_TOKEN environment variables.
    """
    import os

    import requests

    url = os.environ["JIRA_URL"]
    email = os.environ["JIRA_EMAIL"]
    token = os.environ["JIRA_TOKEN"]

    response = requests.get(
        f"{url}/rest/api/3/search",
        params={"jql": jql, "maxResults": 1000,
                "fields": "summary,duedate,priority,issuelinks,status,project"},
        auth=(email, token),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["issues"]


if __name__ == "__main__":
    import os
    import sys

    if not os.environ.get("JIRA_URL"):
        # Demo mode — show the mapping without API calls
        print("Demo mode (set JIRA_URL, JIRA_EMAIL, JIRA_TOKEN for live data)\n")

        demo_obligations = [
            Obligation(id="ENG-1234", title="Fix auth timeout in prod",
                       due_date=datetime.now(UTC) + timedelta(hours=4),
                       materiality="material", dependency_count=8, domain="engineering"),
            Obligation(id="LEGAL-567", title="Review vendor NDA",
                       due_date=datetime.now(UTC) + timedelta(days=2),
                       materiality="material", dependency_count=3, domain="legal"),
            Obligation(id="OPS-890", title="Rotate API keys",
                       due_date=datetime.now(UTC) + timedelta(days=5),
                       dependency_count=15, domain="ops"),
            Obligation(id="ENG-1235", title="Update README badges",
                       due_date=datetime.now(UTC) + timedelta(days=21),
                       domain="engineering"),
        ]
        results = recalculate_batch(demo_obligations)
    else:
        issues = fetch_jira_issues()
        obligations = [ob for issue in issues if (ob := jira_issue_to_obligation(issue)) is not None]
        if not obligations:
            print("No issues with due dates found.")
            sys.exit(0)
        results = recalculate_batch(obligations)

    print(f"{'#':>2}  {'Zone':6}  {'Pressure':>8}  {'ID':12}  Title")
    print("-" * 65)
    for i, r in enumerate(results[:20], 1):
        print(f"{i:>2}  {r.zone:6}  {r.pressure:>8.3f}  {str(r.obligation_id):12}  ", end="")
        # Truncate title for display
        title = str(r.obligation_id)
        if hasattr(r, '_title'):
            title = r._title
        print(r.obligation_id)
