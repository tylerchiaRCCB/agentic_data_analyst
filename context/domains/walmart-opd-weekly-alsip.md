# Walmart OPD Weekly — Alsip DC

## Data Source
Pre-aggregated weekly OPD in-stock data for Walmart stores served by the **Alsip distribution center**, sourced from `CCB_DATASCIENCE_DEV.WALMART_OPD.V_OPD_WEEKLY_ALSIP`.

This is a materialized table (not a view) pre-joined from the raw OPD fact table, V_UPC_PRODUCT (product/PPG bridge), and V_STORE_CUSTOMER (DC/customer bridge). All joins are already resolved — no multi-table join logic is needed at query time.

Data is pulled via a fixed SQL query (`queries/walmart-opd-weekly-alsip.sql`) using `--source direct_sql`. No Cortex Analyst is involved.

## Table & Grain
One row = one **product (CORE_UPC_10) × store (STORE_NBR) × week (WEEK_START)** observation.

- **47 columns** total
- **46 stores** in the Alsip DC footprint
- **642 UPCs** across 60 brands and 15 categories
- **28 weeks** of history (2025-12-28 to 2026-07-19)
- **~508K rows** total (complete weeks); pipeline pulls last 8 weeks (~150K rows)

## Key Metrics

| Metric | How to compute | Pre-computed column | Target |
|---|---|---|---|
| FTPR (First Time Pick Rate) | `SUM(FTPR_NMRTR) / SUM(FTPR_DNMNTR)` | `FTPR_RATE` (row-level only) | ≥ 95% |
| Nil Pick Rate | `SUM(SCHDL_NIL_PICK_RATE_NMRTR) / SUM(SCHDL_NIL_PICK_RATE_DNMNTR)` | `NIL_PICK_RATE` (row-level only) | Lower is better |
| Pre-Substitution Rate | `SUM(PRESUB_RATE_NMRTR) / SUM(PRESUB_RATE_DNMNTR)` | `PRESUB_RATE` (row-level only) | — |
| Post-Substitution Rate | `SUM(POSTSUB_RATE_NMRTR) / SUM(POSTSUB_RATE_DNMNTR)` | `POSTSUB_RATE` (row-level only) | — |

**CRITICAL: Always compute rates from SUM(numerator) / SUM(denominator) when aggregating across stores, weeks, or products. The pre-computed rate columns (FTPR_RATE, NIL_PICK_RATE, PRESUB_RATE, POSTSUB_RATE) are valid only at the individual row grain — never average them across groups (that introduces Simpson's Paradox).**

## Key Dimensions

| Column | Meaning |
|---|---|
| `WEEK_START` | First day (Monday) of the week. Use for trending and date filtering. |
| `DAYS_IN_WEEK` | Number of days with data in this week. Use 7 = complete week; filter out partial weeks. |
| `STORE_NBR` | Walmart store number |
| `CUSTOMER_DESC` | Full Walmart customer description (e.g. WALMART SUPERCENTER #1234) |
| `DISTRIBUTION_CENTER_DESC` | RCCB distribution center serving this store (all rows = Alsip) |
| `CORE_UPC_10` | 10-digit core UPC — product identifier |
| `PRODUCT_ID` | RCCB product (material) ID |
| `PRODUCT_DESC` | RCCB product description |
| `PPG` | Promoted Package Group — groups related products for trade promotion |
| `BRAND` | Product brand (use ILIKE for filtering — mixed case) |
| `CATEGORY` | Product category (see list below) |
| `FLAVOR` | Product flavor variant |
| `SIZE` | Package size descriptor |
| `ORIGINAL_ITEM_DESC` | Original Walmart item description |
| `MANAGEDBY_SID` | RCCB sales rep / managed-by surrogate key |

## Categories (by pick volume, descending)

1. SPARKLING SOFT DRINKS — ~469K picks (largest category)
2. CORE SPARKLING — ~334K picks
3. ADVANCED HYDRATION — ~141K picks
4. DAIRY BEVERAGES — ~108K picks
5. ENERGY DRINKS — ~86K picks
6. JUICE DRINKS — ~79K picks
7. ENHANCED WATER BEVERAGES — ~54K picks
8. TEA — ~29K picks
9. FRUIT/VEGETABLE STILL DRINKS — ~25K picks
10. PACKAGED WATER — ~15K picks
11. COFFEE PACKAGED — ~8K picks
12. COFFEE — ~610 picks
13. NECTARS — ~19 picks
14. PACKAGED WATER (PLAIN & ENRICHED) — ~13 picks
15. SSD — ~0 picks (legacy/deprecated category code)

## Business Context
- **FTPR** (First Time Pick Rate) is the primary OPD service metric. It measures the share of customer orders picked successfully on the first attempt. Higher is better.
- **Nil-picks** are failed picks — the item was ordered but not available on the shelf at pick time. This is the inverse of FTPR but not an exact complement due to substitutions.
- **Alsip** is the DC being analyzed. All stores in this dataset are served by the Alsip distribution center.
- RCCB is a Coca-Cola bottler; Walmart OPD is one of their key fulfillment channels.
- **SPARKLING SOFT DRINKS** and **CORE SPARKLING** together represent the bulk of pick volume (~800K picks). These were previously combined as "SSD."

## Analytical Guardrails
- When FTPR declines, check whether nil-picks rose (they should be inversely correlated).
- Substitution rates can mask nil-pick severity — a high pre-sub rate may hide true out-of-stock impact.
- Pair any store-level finding with the store's pick volume (FTPR_DNMNTR) to avoid over-interpreting small-volume stores.
- Pair any product-level finding with the product's pick volume to avoid over-interpreting niche SKUs.

## Suggested Analysis Paths
- **Weekly FTPR trend** — is performance improving or declining across the Alsip footprint?
- **Category breakdown** — which product categories have the worst FTPR? (Focus on top-7 by volume)
- **Store-level outliers** — which stores consistently underperform the DC average?
- **PPG analysis** — which promoted package groups have the highest nil-pick rates?
- **Product analysis** — which products at which stores have concerning FTPR and nil-pick rates?
- **Delivery impact** — do stores with more delivery stops or longer delivery durations have better FTPR?
- **Merch impact** — do stores with more merch visits or longer merch durations have better FTPR?
- **Week-over-week change** — what degraded THIS week vs the prior 5-week baseline?

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
- Data starts from 2025-12-28. All rows are actuals (not forecast/plan).
- Store 9999 (sentinel) is already excluded from the source table.
- Unmatched UPCs with corrupt nil pick values are already filtered out via INNER JOIN to V_UPC_PRODUCT in the source table.
- BRAND values are mixed case — always use ILIKE for brand filtering.
- The pipeline pulls only the last 8 complete weeks (DAYS_IN_WEEK=7) via `queries/walmart-opd-weekly-alsip.sql`.
- Category names changed mid-2026: "SSD" → "SPARKLING SOFT DRINKS" + "CORE SPARKLING"; "Isotonics" → "ADVANCED HYDRATION"; "Enh Water" → "ENHANCED WATER BEVERAGES"; "ENERGY" → "ENERGY DRINKS".
