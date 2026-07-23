"""Post pipeline results to a Microsoft Teams channel via Incoming Webhook.

Extracts the Executive Summary and Action Card headlines from the communication
agent artifact, formats them as an Adaptive Card, and POSTs to the webhook URL.

Usage:
    python tools/notify_teams.py --run-dir runs/20260722T174751Z-9418f05b/
    python tools/notify_teams.py --run-dir runs/latest/ --webhook-url https://...

The webhook URL is read from (in priority order):
    1. --webhook-url argument
    2. TEAMS_WEBHOOK_URL environment variable
    3. .env file in the repo root

Exit 0 on success, 1 on failure (non-blocking — pipeline doesn't fail if notification fails).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


def find_communication_artifact(run_dir: Path) -> Path | None:
    """Find the communication agent artifact in the run directory."""
    artifacts_dir = run_dir / "artifacts"
    if not artifacts_dir.exists():
        return None
    for f in sorted(artifacts_dir.iterdir(), reverse=True):
        if f.name.endswith("-communication-agent.json"):
            return f
    return None


def extract_summary(artifact_path: Path) -> dict:
    """Extract Executive Summary, Action Card headlines, and card bodies from the artifact."""
    with open(artifact_path) as f:
        data = json.load(f)

    payload = data.get("payload", {})
    markdown = payload.get("rendered_output_markdown", "")

    # Extract title (first # line)
    title_match = re.search(r"^# (.+)$", markdown, re.MULTILINE)
    title = title_match.group(1) if title_match else "Pipeline Report"

    # Extract Executive Summary section
    exec_match = re.search(
        r"## Executive Summary\s*\n(.*?)(?=\n## |\Z)",
        markdown,
        re.DOTALL,
    )
    exec_summary = ""
    if exec_match:
        # Extract bullet points
        bullets = re.findall(r"^- \*\*(.+?)\*\*", exec_match.group(1), re.MULTILINE)
        if bullets:
            exec_summary = "\n".join(f"• {b}" for b in bullets)
        else:
            # Fallback: grab first 500 chars
            exec_summary = exec_match.group(1).strip()[:500]

    # Extract Action Card headlines
    card_headlines = re.findall(r"### Card \d+ — (.+)$", markdown, re.MULTILINE)

    # Extract Action Card bodies (visible content before <details>)
    card_bodies = []
    card_pattern = re.compile(
        r"### Card \d+ — .+?\n(.*?)(?=\n### Card \d+|\n## |\n---\n|\Z)",
        re.DOTALL,
    )
    for match in card_pattern.finditer(markdown):
        body = match.group(1).strip()
        # Remove <details> blocks, mermaid blocks, and markdown tables
        body = re.sub(r"<details>.*?</details>", "", body, flags=re.DOTALL)
        body = re.sub(r"```mermaid.*?```", "", body, flags=re.DOTALL)
        # Strip bold markdown for cleaner Teams rendering
        body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
        # Trim to a reasonable length per card
        if len(body) > 800:
            body = body[:800].rsplit("\n", 1)[0] + "\n..."
        card_bodies.append(body.strip())

    # Get run metadata
    run_id = data.get("run_id", artifact_path.parent.parent.name)
    status = data.get("status", "ok")

    return {
        "title": title,
        "exec_summary": exec_summary,
        "card_headlines": card_headlines[:5],
        "card_bodies": card_bodies[:5],
        "run_id": run_id,
        "status": status,
    }


def build_adaptive_card(summary: dict, report_url: str | None = None) -> dict:
    """Build a Teams Adaptive Card payload."""
    # Status indicator
    status_emoji = "🔴" if len(summary["card_headlines"]) >= 3 else "🟡" if summary["card_headlines"] else "🟢"

    body = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": f"{status_emoji} {summary['title']}",
            "wrap": True,
        },
    ]

    # Executive Summary
    if summary["exec_summary"]:
        body.append({
            "type": "TextBlock",
            "text": summary["exec_summary"],
            "wrap": True,
            "spacing": "Medium",
        })

    # Action Cards — full content
    if summary["card_headlines"]:
        for i, headline in enumerate(summary["card_headlines"]):
            body.append({
                "type": "TextBlock",
                "text": f"**Card {i+1} — {headline}**",
                "wrap": True,
                "spacing": "Medium",
                "weight": "Bolder",
                "separator": True,
            })
            if i < len(summary.get("card_bodies", [])):
                body.append({
                    "type": "TextBlock",
                    "text": summary["card_bodies"][i],
                    "wrap": True,
                    "spacing": "Small",
                })

    # Link to full report
    actions = []
    if report_url:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "View Full Report",
            "url": report_url,
        })

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                    "actions": actions if actions else None,
                },
            }
        ],
    }
    return card


def post_to_teams(webhook_url: str, card: dict) -> bool:
    """POST the Adaptive Card to the Teams webhook. Returns True on success."""
    payload = json.dumps(card).encode("utf-8")
    req = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            status = resp.status
            if status in (200, 202):
                print(f"Teams notification sent (HTTP {status})")
                return True
            else:
                print(f"Teams webhook returned HTTP {status}", file=sys.stderr)
                return False
    except URLError as e:
        print(f"Teams webhook failed: {e}", file=sys.stderr)
        return False


def get_webhook_url(cli_url: str | None) -> str | None:
    """Resolve webhook URL from CLI arg, env var, or .env file."""
    if cli_url:
        return cli_url
    if url := os.environ.get("TEAMS_WEBHOOK_URL"):
        return url
    # Try .env file in repo root
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TEAMS_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main():
    parser = argparse.ArgumentParser(description="Post pipeline results to Teams")
    parser.add_argument("--run-dir", required=True, help="Path to the run directory")
    parser.add_argument("--webhook-url", help="Teams Incoming Webhook URL (or set TEAMS_WEBHOOK_URL)")
    parser.add_argument("--report-url", help="URL to link to the full report (e.g., webapp URL)")
    parser.add_argument("--dry-run", action="store_true", help="Print the card JSON without posting")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    artifact = find_communication_artifact(run_dir)
    if not artifact:
        print(f"No communication agent artifact found in {run_dir}/artifacts/", file=sys.stderr)
        sys.exit(1)

    summary = extract_summary(artifact)
    card = build_adaptive_card(summary, report_url=args.report_url)

    if args.dry_run:
        print(json.dumps(card, indent=2))
        sys.exit(0)

    webhook_url = get_webhook_url(args.webhook_url)
    if not webhook_url:
        print(
            "No webhook URL configured. Set TEAMS_WEBHOOK_URL in .env or pass --webhook-url.",
            file=sys.stderr,
        )
        sys.exit(1)

    success = post_to_teams(webhook_url, card)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
