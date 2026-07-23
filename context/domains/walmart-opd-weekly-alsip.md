# Walmart OPD Weekly — Alsip DC

## Data Source
Pre-aggregated weekly OPD in-stock data for Walmart stores served by the **Alsip distribution center**, sourced from `CCB_DATASCIENCE_DEV.WALMART_OPD.V_OPD_WEEKLY_ALSIP`.

This is a materialized table (not a view) pre-joined from the raw OPD fact table, V_UPC_PRODUCT (product/PPG bridge), and V_STORE_CUSTOMER (DC/customer bridge). All joins are already resolved — no multi-table join logic is needed at query time.

## Table & Grain
One row = one **product (CORE_UPC_10) × store (STORE_NBR) × week (WEEK_START)** observation.

Date range: 2025 onward. Data is actual operational performance, not forecast or plan.

## Key Metrics

| Metric | How to compute | Target |
|---|---|---|
| FTPR (First Time Pick Rate) | `SUM(FTPR_NMRTR) / SUM(FTPR_DNMNTR)` | ≥ 95% |
| Nil Pick Rate | `SUM(SCHDL_NIL_PICK_RATE_NMRTR) / SUM(SCHDL_NIL_PICK_RATE_DNMNTR)` | Lower is better |
| Pre-Substitution Rate | `SUM(PRESUB_RATE_NMRTR) / SUM(PRESUB_RATE_DNMNTR)` | — |
| Post-Substitution Rate | `SUM(POSTSUB_RATE_NMRTR) / SUM(POSTSUB_RATE_DNMNTR)` | — |

**Always compute rates from SUM(numerator) / SUM(denominator). Never average pre-computed rate columns (FTPR_RATE, NIL_PICK_RATE, etc.) across groups — that introduces Simpson's Paradox.**

## Key Dimensions

| Column | Meaning |
|---|---|
| `WEEK_START` | First day (Monday) of the week. Use for trending and date filtering. |
| `STORE_NBR` | Walmart store number |
| `CUSTOMER_DESC` | Full Walmart customer description (e.g. WALMART SUPERCENTER #1234) |
| `DISTRIBUTION_CENTER_DESC` | RCCB distribution center serving this store (all rows = Alsip) |
| `CORE_UPC_10` | 10-digit core UPC — product identifier |
| `PRODUCT_ID` | RCCB product (material) ID |
| `PRODUCT_DESC` | RCCB product description |
| `PPG` | Promoted Package Group — groups related products |
| `BRAND` | Product brand (use ILIKE for filtering — mixed case) |
| `CATEGORY` | Product category (SSD, ENERGY, Water, etc.) |
| `FLAVOR` | Product flavor variant |
| `SIZE` | Package size descriptor |

## Business Context
- **FTPR** (First Time Pick Rate) is the primary OPD service metric. It measures the share of customer orders picked successfully on the first attempt. Higher is better.
- **Nil-picks** are failed picks — the item was ordered but not available on the shelf at pick time. This is the inverse of FTPR but not an exact complement due to substitutions.
- **Alsip** is the DC being analyzed. All stores in this dataset are served by the Alsip distribution center.
- RCCB is a Coca-Cola bottler; Walmart OPD is one of their key fulfillment channels.

## Analytical Guardrails
- When FTPR declines, check whether nil-picks rose (they should be inversely correlated).
- Substitution rates can mask nil-pick severity — a high pre-sub rate may hide true out-of-stock impact.
- Pair any store-level finding with the store's pick volume (FTPR_DNMNTR) to avoid over-interpreting small-volume stores.
- Pair any product-level finding with the product's pick volume to avoid over-interpreting niche SKUs.

## Suggested Analysis Paths
- **Weekly FTPR trend** — is performance improving or declining across the Alsip footprint?
- **Category breakdown** — which product categories have the worst FTPR?
- **Store-level outliers** — which stores consistently underperform the DC average?
- **PPG analysis** — which promoted package groups have the highest nil-pick rates?
- **Delivery impact** — do stores with more DELIVERY_STOP_COUNT or IS_DELIVERY_ACTIVE_WEEK=1 have better FTPR? Correlate delivery frequency with in-stock performance.
- **Merch impact** — do stores with more MERCH_VISIT_COUNT or IS_MERCH_ACTIVE_WEEK=1 have better FTPR? Does longer merch duration (AVG_MERCH_DURATION_MINS) correlate with improvement?
- **Day-of-week patterns** — use DAYS_IN_WEEK to detect partial weeks and exclude them from trend analysis.

## Delivery & Merch Columns (pre-joined from GreenMile)
These columns are already in the flat table — no cross-table joins needed.

| Column | Meaning |
|---|---|
| `DELIVERY_STOP_COUNT` | Number of DC delivery stops at this store this week (0 = no delivery) |
| `AVG_DELIVERY_DURATION_MINS` | Average delivery stop duration in minutes |
| `TOTAL_DELIVERY_DURATION_MINS` | Total delivery time at the store this week |
| `IS_DELIVERY_ACTIVE_WEEK` | 1 if at least one delivery happened, 0 otherwise |
| `MERCH_VISIT_COUNT` | Number of merchandising visits this week (0 = no merch) |
| `AVG_MERCH_DURATION_MINS` | Average merch visit duration in minutes |
| `TOTAL_MERCH_DURATION_MINS` | Total merch time at the store this week |
| `IS_MERCH_ACTIVE_WEEK` | 1 if at least one merch visit happened, 0 otherwise |

## Known Considerations
- Data starts from 2025-01-01. All rows are actuals (not forecast/plan).
- Store 9999 (sentinel) is already excluded from the source table.
- Unmatched UPCs with corrupt nil pick values are already filtered out via INNER JOIN to V_UPC_PRODUCT in the source table.
- BRAND values are mixed case — always use ILIKE for brand filtering.
