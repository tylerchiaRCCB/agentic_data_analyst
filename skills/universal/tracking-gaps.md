# Universal Skill: Tracking Gaps

**Role:** When the data needed to answer a question does not exist, produce a specific instrumentation request — not a workaround that pretends the gap isn't there. Loaded with every agent call.

A missing data field is itself a finding. The system's job in that case is to make the gap legible to the people who can close it, not to extrapolate, proxy, or quietly skip the part of the analysis the gap blocks.

## When this skill triggers

- The Question Framer's `data_requirements` cannot be fully met by available columns.
- An analytical agent needs a metric or dimension to answer cleanly and finds it unavailable, unreliable, or at the wrong grain.
- The Findings Validator's guardrail check requires a counter-metric that the dataset does not contain.
- The Opportunity Identifier needs an outcome metric to measure intervention success and the metric is absent.

In any of these cases, the gap becomes part of the artifact's output and, eventually, part of the recipient-facing output.

## Required practices

1. **Name the missing data explicitly.** Not "data was incomplete," but a description specific enough to instrument against. *(Example, CPG)*: *"This analysis would have been substantially stronger with weekly inventory snapshots at the account level. The available data is at the regional weekly level, which masks account-level variation in days-of-supply."* The structure transfers across domains: state the desired grain or column, contrast it with what's currently available, and name what the gap blocks.

2. **Specify what would close the gap.** Either a column, a join, a grain change, or a new instrumentation event:
   - **Column:** *"Need a column: `account_id` on the orders table (currently joinable only through a manual mapping)."*
   - **Grain (illustrated in sales):** *"Need daily granularity for the instock metric (currently weekly), to detect mid-week recovery."*
   - **Event (illustrated in trade marketing):** *"Need an event log of promotional price changes with effective date and SKU; currently only end-of-period summaries exist."* — the same shape applies across our CPG functional domains (supply chain: receipt and shipment event log; operations: line-stop event log; finance: trade deduction event log; commercial: account-status-change log).

3. **Estimate the analytical impact of closing the gap.** What would be possible with the data that isn't possible without it? Make the business case for the instrumentation, briefly.

4. **Do not produce a workaround that hides the gap.** Using a coarse proxy and reporting the proxy's result as if it answered the original question is a category error. Either:
   - Use the proxy *and* explicitly state that it is a proxy, *and* describe what the proxy does and doesn't capture, *and* downgrade the confidence of any finding derived from it; or
   - Decline the analysis for the affected scope and report it as blocked on instrumentation.

5. **Aggregate gaps for the recipient.** The Communication Agent should collect tracking gaps from upstream artifacts into a single `Open Data Gaps` section in the output. This makes the cumulative case for instrumentation investment visible to the recipient, rather than scattering single-sentence laments across cards.

## Tie to framing

A tool that quietly extrapolates around missing data looks more useful than it is — until a recipient acts on a confident-sounding number and discovers it was an inference, not a measurement. Surfacing tracking gaps honestly is one of the ways the product earns recipient trust over time: the system flags what it cannot answer, so when it *does* answer, the recipient can rely on it.

## Anti-patterns

- "Data was unavailable" with no follow-up — leaves the recipient without a path to fix it.
- Substituting a coarse proxy without labeling it as such.
- Skipping the affected portion of the analysis silently and emitting only the parts that worked, without naming what was skipped.
- Listing gaps in the lineage log but not in the recipient-facing output — the data-engineering and instrumentation teams need to see them too.
