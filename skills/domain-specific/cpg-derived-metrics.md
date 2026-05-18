# Domain-Specific Skill: CPG-Derived Metrics

**Loaded by:** Data Profiler, Relationship Analyzer, Time Series Analyzer, Root Cause Investigator, Opportunity Identifier — when the run is operating against a CPG domain (sales, supply chain, operations, trade marketing). Loading is triggered by the domain context document for the relevant functional domain.
**Purpose:** Define the canonical derived metrics used across our CPG company, with the formulas, the inputs they require, the conventions for handling edge cases, and the gotchas that distinguish a correct derivation from a near-miss.

This skill is **CPG-specific to our company**. The metrics, conventions, and edge-case handling reflect our internal definitions, not industry-generic norms. When definitions change, this file changes — not the universal or analytical skills.

For metrics not covered here, fall back to the functional-domain context document, which carries the authoritative definitions for its scope.

## Sales / commercial metrics

### Volume
Total units sold, typically in cases (or eaches for SKUs sold individually). Aggregated by entity (account, region, channel) and period (week, month).

- **Inputs:** transaction or shipment records with quantity and timestamp.
- **Convention:** weekly volume defined as Monday–Sunday in local time zone unless the domain context specifies otherwise. Monthly is calendar month. Aligns with the company's standard reporting calendar.
- **Edge cases:** returns and adjustments are netted out by default; the gross / net distinction must be stated explicitly when both views matter.

### ACV (All-Commodity Volume) — weighted distribution
The share of total commodity-volume opportunity an SKU is available in. Used to normalize distribution metrics across markets with different total commodity volume.

- **Formula:** `ACV-weighted distribution % = sum(ACV of stores carrying the SKU) / total ACV of universe × 100`
- **Convention:** universe is defined by the relevant retail measurement service feed; the domain context names the specific universe per category.
- **Gotcha:** ACV-weighted distribution can rise while raw store-count distribution falls (the SKU is dropped from small stores and added to large stores). Always check both when interpreting distribution change.

### Velocity
Sales per point of distribution. The CPG canonical "are we selling well where we're carried" metric.

- **Formula:** `velocity = volume / ACV-weighted distribution %` *(usually expressed as units per $MM of ACV per week)*
- **Convention:** computed at the SKU × period level; aggregated by simple averaging (not volume-weighted) when rolling up to brand or category, because the metric is already normalized.
- **Edge case:** velocity is undefined when ACV-weighted distribution is zero. Treat as missing, not as a division-by-zero error.
- **Gotcha:** velocity changes can be driven either by genuine consumer behavior (the *velocity per point* interpretation) or by mix shift in which stores are carrying the SKU. The Validator's guardrail check should examine both.

### Volume = Distribution × Velocity decomposition
The canonical CPG performance-gap decomposition (referenced from [performance-gap-analysis.md](../analytical/performance-gap-analysis.md)):

`volume = ACV-weighted distribution × velocity per point × ACV-of-universe`

Taking logs converts to additive contributions, so a volume gap decomposes cleanly into a distribution component + a velocity component + a residual. The Opportunity Identifier uses this decomposition as the default for sales-domain gaps.

### Instock rate
The percent of store-SKU-period observations where the SKU is on shelf and available for purchase.

- **Formula:** `instock % = (count of in-stock observations) / (count of total observations) × 100`
- **Convention:** the observation grain (store-SKU-day vs. store-SKU-week) is defined by the data source; carry the grain forward in the metric label.
- **Gotcha:** instock measured by syndicated retail data lags real-time by 1–3 weeks depending on the source. Recent-week instock numbers are provisional; the domain context should specify the lag.

### Basket size
Average units per transaction. Used to distinguish volume gains from increased transaction frequency vs. larger transactions.

- **Formula:** `basket size = total units / transaction count`
- **Convention:** computed at the account × period level by default; aggregated by transaction-count-weighted average when rolling up.

## Supply chain metrics

### Fill rate
Share of orders (by units, lines, or cases) where the shipment matched the order quantity.

- **Formula:** `fill rate = units shipped / units ordered × 100` (units-based; line-based is similar with order lines as denominator)
- **Convention:** measured at the order line or order header level; the domain context specifies which is authoritative.
- **Edge case:** orders with zero ordered quantity are excluded, not counted as 100% fill.

### On-time-in-full (OTIF)
The percent of orders shipped on the requested date AND in the requested quantity. Multiplicative across the two components.

- **Formula:** `OTIF = (on-time % × in-full %)` if measured independently, or `(orders meeting both) / (total orders) × 100` if measured jointly. Joint is more conservative.
- **Convention:** "on time" depends on the customer's stated delivery window — typically a 1- or 2-day window from the requested delivery date. The domain context specifies the customer-specific tolerances.
- **Gotcha:** OTIF measured against the *promise date* and OTIF measured against the *original request date* can differ materially when promise dates were renegotiated. Always state which is being measured.

### Days-of-supply (DOS)
Inventory on hand relative to expected consumption.

- **Formula:** `DOS = (inventory on hand units) / (average daily consumption units)`
- **Convention:** consumption rate is the trailing-13-week average daily run-rate by default; the domain context can override with a different window.
- **Edge case:** DOS is undefined when consumption is zero. Treat as missing for the period; consider flagging as a stockout if inventory is also zero.
- **Gotcha:** DOS can rise either because inventory rose (oversupply) or because consumption fell (demand shock). The Validator's guardrail check should pair DOS with consumption rate.

### Cycle time
Duration metrics — order-to-ship, ship-to-deliver, dock-to-stock, etc. Each is a distinct cycle measured between two timestamped events.

- **Convention:** measured in business days unless otherwise stated. Distribution is typically right-skewed; use median + IQR rather than mean + SD.
- **Edge case:** records with negative or implausibly large cycle times indicate data quality issues (clock skew, mis-keyed timestamps); flag rather than include.

## Operations / manufacturing metrics

### OEE (Overall Equipment Effectiveness)
The canonical operations performance metric: `OEE = availability × performance × quality`.

- **Availability:** `actual run time / planned production time` (captures unplanned downtime).
- **Performance:** `(actual output × ideal cycle time) / actual run time` (captures speed losses).
- **Quality:** `good output / total output` (captures defect rates).

Each component decomposes further; see the operations functional domain context for the line-specific definitions.

### First-pass yield
Share of units produced that pass quality on the first attempt, without rework.

- **Formula:** `first-pass yield = (units passing first inspection) / (total units produced) × 100`
- **Convention:** measured at the SKU × line × shift level; aggregated by simple average when rolling up across shifts but by unit-weighted average when rolling up across SKUs.

### Changeover time
Time required to convert a production line from one SKU configuration to another.

- **Convention:** measured from the last good unit of the prior SKU to the first good unit of the next SKU. Skewed right; use median + IQR.
- **Gotcha:** changeover times vary by changeover *type* (similar SKU vs. dissimilar SKU). Aggregate changeover time across types is uninterpretable; always cut by type.

## Trade marketing metrics

### Promotional lift
The incremental volume produced by a promotional event, relative to expected non-promotional volume.

- **Formula:** `lift = (promo period volume - baseline expected volume) / baseline expected volume`
- **Convention:** baseline expected volume is the trailing-13-week average for non-promo weeks, seasonality-adjusted. The functional domain context for trade marketing specifies the exact baseline methodology.
- **Edge case:** lift is meaningful only when baseline expected volume is non-trivial. For low-baseline SKUs the percentage can be huge but the incremental units small; report incremental units alongside.

### Cannibalization index
The share of promoted-SKU lift that came from reduced volume on other SKUs in the same household / basket.

- **Formula:** `cannibalization index = (decline in non-promoted SKU volume) / (lift in promoted SKU volume)`
- **Convention:** measured at the household / basket level when household-panel data is available; at the category level otherwise (less accurate). The domain context specifies what's available.

### Promo ROI
Return on incremental trade-spend dollars.

- **Formula:** `promo ROI = (incremental gross profit) / (trade spend)`
- **Convention:** incremental gross profit uses gross margin per case net of any direct promo cost. The domain context specifies the cost allocation.
- **Gotcha:** ROI < 1 is common in CPG promotions and is not by itself "bad" — the strategic intent may be share gain rather than profit. Always state alongside the strategic intent if known.

## Finance metrics (analytics-relevant)

### Gross margin per case
Margin contribution per unit sold, after deducting cost-of-goods and direct trade costs.

- **Formula:** `gross margin per case = (revenue per case - COGS per case - direct trade cost per case)`
- **Convention:** the trade-cost allocation methodology comes from the finance functional domain context.

### Trade deductions
Claims taken by customers against invoices for various reasons (promotional allowances, shipping shortfalls, damages).

- **Convention:** aggregated by deduction reason code per customer per period. The domain context specifies the master reason-code list.
- **Edge case:** deduction recovery rate (the share eventually collected back) is a key derived metric — pair total deductions with recovery rate.

## When this skill is loaded but the domain context overrides

If the functional-domain context document provides a different definition or convention for any metric in this file, **the functional-domain context wins**. This skill is the company-wide reference; the functional-domain context is closer to the operational reality of that domain.

When a conflict exists, the run's caveats should note the override so reviewers can decide whether the conflict reflects a needed update to this file or a legitimate domain-specific exception.

## Anti-patterns

- Treating metrics as universally comparable when they're computed differently across functional domains. Volume in sales (cases shipped to retailer) ≠ volume in operations (cases produced) ≠ volume in finance (cases invoiced) for the same SKU in the same week — there are pipeline timing differences. State which is being used.
- Aggregating velocity by volume-weighting. The metric is already normalized; volume-weighting double-counts.
- Reporting unaggregated cycle times without a distribution view. Mean cycle time hides the tail; show median + IQR.
- Stating ACV-weighted distribution change without checking store-count distribution change. Mix shift in stores can drive the metric without an underlying distribution change.

## Output discipline

Code execution computes the derived metrics from underlying data; per the discipline rules in [pipeline-definitions.md](../../orchestration/pipeline-definitions.md) §10, only the computed values and small summary tables return to context. Raw underlying transactions stay in the sandbox.
