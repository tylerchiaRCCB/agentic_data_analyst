"""Stand-in for the real analyst pipeline, honoring the same CLI contract.

Behavior toggles via the question text (for testing):
  contains "FAIL"  -> exit 1 after logging
  contains "HANG"  -> sleep for 10 minutes (tests timeout/cancel)
Otherwise: logs progress, writes report.md + one artifact, exits 0.
"""

import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-file", required=True)
    parser.add_argument("--semantic-view", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    question = Path(args.question_file).read_text(encoding="utf-8")
    out = Path(args.output_dir)

    print(f"[fake-pipeline] question: {question!r}", flush=True)
    print(f"[fake-pipeline] semantic view: {args.semantic_view}", flush=True)

    if "HANG" in question:
        print("[fake-pipeline] hanging...", flush=True)
        time.sleep(600)

    steps = [
        "connecting to Snowflake via Cortex Analyst",
        "generating SQL from semantic view",
        "pulling data",
        "running statistical analysis agent",
        "running trends analysis agent",
        "validating findings",
        "writing report",
    ]
    for step in steps:
        print(f"[fake-pipeline] {step}", flush=True)
        time.sleep(0.3)

    if "FAIL" in question:
        print("[fake-pipeline] simulated failure", file=sys.stderr, flush=True)
        return 1

    (out / "report.md").write_text(
        f"# Analysis Report\n\n**Question:** {question}\n\n"
        "## Key Findings\n\n"
        "- Revenue grew **12%** week-over-week\n"
        "- The West region drove 60% of the change\n\n"
        "| Region | Change |\n|---|---|\n| West | +18% |\n| East | +4% |\n",
        encoding="utf-8",
    )
    (out / "artifacts" / "data_summary.csv").write_text(
        "region,change\nWest,0.18\nEast,0.04\n", encoding="utf-8"
    )
    print("[fake-pipeline] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
