# Example outputs

Canonical reference outputs from running the pipeline against the included
smoke-test data. These are checked into the repo so they survive the
`output/*` gitignore and can be shared via stable GitHub URLs.

## `smoke-test-output.md`

End-to-end output of the pipeline against `data/sample/smoke-test.csv`
(100 rows of synthetic CPG-shaped data, ~$0.30 to render via replay tool).

What's notable in this output:

- **Two action cards** — A003/SKU003 instock anomaly (Grade A) and A001/SKU004
  fill-rate decline (Grade B).
- **The Findings Validator's CI correction** — visible in Action Card #2's
  caveats. The upstream Time Series Analyzer used z=1.96 (normal distribution)
  instead of t=4.303 (t-distribution at df=2 for n=4). The Validator caught it
  and the corrected CI [−0.0112, −0.0038] appears in the recipient output.
- **"What would have constituted a finding" section** — explicitly lists
  thresholds that weren't crossed. This is the framing's calibration of
  "all clear" — recipients learn what the system was looking for, so the
  absence of findings is informative, not opaque.
- **Prompt-injection notice** — the smoke-test data includes 11 synthetic
  injection-shaped strings in `account_notes`. The Data Profiler detected,
  quarantined, and surfaced them with required remediation action.
- **Open Data Gaps table** — 5 specific instrumentation requests with
  impact ratings, demonstrating the system's "missing data is itself a
  finding" discipline.

## How to view

- **On GitHub.com:** rendered cleanly.
- **In Obsidian / Typora / Bear:** drop the file into a vault.
- **As PDF:** `pandoc smoke-test-output.md -o smoke-test-output.pdf`.

The runtime output (whatever the current pipeline produces) lands in
`output/<run_id>.md` and is gitignored. This `docs/examples/` copy is the
stable, shareable canonical reference.
