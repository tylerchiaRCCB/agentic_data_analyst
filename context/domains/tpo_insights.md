# TPO Insights — Trade Promotion Optimization

## Data Source
Anaplan trade promotion data from `CCB_PRD.ANAPLAN_RAW_SHARE.TPO_V`, modeled for weekly promotional analysis by key account and Promoted Package Group (PPG).

## Table & Grain

### Primary Fact: TPO Weekly (`TPO_V`)
One row = one **week × account × PPG** observation with promotion attributes, pricing, and volume/profitability measures.

## Mandatory Scope Rules
- Analyze only active promotions.
- Active-promotion scope is defined as:
  - `PPG IS NOT NULL`
  - `EVEN_OFFER_STANDARD <> 'No Message'`
  - `EDV = 'false'`
- Treat these filters as part of the business definition of the dataset, not as optional slicers.

## Key Dimensions

| Column | Meaning |
|---|---|
| `TIME` | Fiscal week label used for reporting (for example, `Week 49 FY24`) |
| `YEAR` | Fiscal year label |
| `WEEK_NUM` | Fiscal week number |
| `PROMO_WEEK_START` | Week start date; stored as text and should be converted with `TRY_TO_DATE()` |
| `ACCOUNT` | Retail customer or banner where the promotion ran |
| `PPG` | Promoted Package Group |
| `HOLIDAYS` | Seasonal or holiday context for the promotion week |
| `EVEN_OFFER_STANDARD` | Standardized promotion offer message |
| `EVENT_OFFER_RPA` | RPA-style promotion offer description |
| `PURCHASE_QUANTITY` | Quantity customer must purchase to receive promotion |
| `FREE_QUANTITY` | Free quantity customer receives from promotion |
| `SAVE_QUANTITY` | Quantity customer saves on from promotion |
| `IN_AD` | Whether the promotion was featured in retailer advertising |
| `ACCELERATION` | Whether the promotion is classified as an acceleration event |
| `DIGITAL_DEAL` | Whether the promotion was a digital offer |
| `FLAVOR_SEGMENTATION` | Whether the promotion targeted a flavor subset |
| `EDV` | Every Day Value flag; `true` rows are excluded from valid promo analysis |

## Key Metrics

| Metric | Meaning | Recommended computation |
|---|---|---|
| `retail_units` | Consumer units sold during the promo week | `SUM(RETAIL_UNITS_ACT_FCST_CONVERTED_TO_SPC * RETAIL_UNITS_PER_SPC)` |
| `base_retail_units` | Baseline units expected without promotion | `SUM(BASE_RETAIL_UNITS_ACTUAL_CONVERTED_TO_SPC * RETAIL_UNITS_PER_SPC)` |
| `incremental_retail_units` | Promo-driven volume lift above baseline | `SUM((actual_spc - base_spc) * RETAIL_UNITS_PER_SPC)` |
| `unit_lift_rate` | Relative volume lift vs baseline | `SUM(incremental units) / NULLIF(SUM(base units), 0)` |
| `retail_dollars` | Promo-period retail revenue | `SUM(actual_units * price)` |
| `communicated_promo_price` | Advertised promo price per unit | average price across scoped promo rows |
| `white_tag_price` | Regular shelf price per unit | average regular price across scoped promo rows |
| `percentage_discount` | Discount depth off regular price | aggregate as a rate, not a simple average of subgroup averages |
| `redemption_rate` | Share of promo-eligible purchases that redeemed the offer | aggregate as a rate |
| `retail_margin_percentage` | Retailer margin percentage during promo | aggregate as a rate |
| `retail_unit_profit` | Profit dollars per consumer unit | sum or inspect alongside volume |
| `dnnsi` | Dead Net Net Selling Income | `SUM(DNNSI)` |
| `dngp` | Dead Net Gross Profit | `SUM(DNGP)` |
| `dnnsi_per_incremental_unit` | Revenue efficiency per unit of lift | `SUM(DNNSI) / NULLIF(SUM(incremental units), 0)` |

## Business Context
- This domain is for **trade promotion effectiveness**, not general sales reporting.
- The main questions are which promotions drive the most incremental volume, which accounts respond best, and which promotion mechanics create profitable lift rather than volume at any cost.
- `PPG` is the main product grouping for trade promotion analysis.
- `ACCOUNT` is the main external customer dimension for comparing promo response across banners or retailers.
- `EDV = 'true'` means the row represents an everyday-value condition rather than a true promotional event; exclude from promo-effectiveness conclusions.
- Promotions with no message (`EVEN_OFFER_STANDARD = 'No Message'`) should not be interpreted as real advertised promotional mechanics.
- For must-buy mechanics, prefer `PURCHASE_QUANTITY`, `FREE_QUANTITY`, and `SAVE_QUANTITY` over free-text parsing of `EVEN_OFFER_STANDARD`.

## Analytical Guardrails
- Always compute rates using aggregated numerators and denominators where available. Do not average pre-computed row-level rates across groups if a true numerator/denominator formulation exists.
- Pair `unit_lift_rate` with `base_retail_units` so high lift on tiny baselines is not over-interpreted.
- Pair `percentage_discount` with `dngp` or `dnnsi` to avoid recommending unprofitable deep-discount promotions.
- Pair `redemption_rate` with `retail_units` to distinguish strong but low-scale offers from strong and scalable offers.
- Pair `dnnsi_per_incremental_unit` with `incremental_retail_units` so efficiency is not mistaken for total business impact.
- When comparing accounts or PPGs, inspect both absolute lift and profitability. Volume-only conclusions are incomplete.

## Suggested Analysis Paths
- Compare `unit_lift_rate`, `incremental_retail_units`, `dngp`, and `dnnsi` by `ACCOUNT` to identify the best-performing retailer relationships.
- Compare promo effectiveness by `PPG` to see which product groups respond best to promotions.
- Segment by `IN_AD`, `DIGITAL_DEAL`, `ACCELERATION`, and `FLAVOR_SEGMENTATION` to evaluate which promotion mechanics drive lift.
- Segment by `PURCHASE_QUANTITY`, `FREE_QUANTITY`, and `SAVE_QUANTITY` to evaluate which bundle structures drive lift and profitability.
- Evaluate holiday effects by comparing outcomes across `HOLIDAYS` and fiscal periods.
- Compare `communicated_promo_price`, `white_tag_price`, and `percentage_discount` to understand whether deeper discounts actually improve lift and profitability.

## Known Considerations
- `PROMO_WEEK_START` is stored as text, not a native date. Use `TRY_TO_DATE(PROMO_WEEK_START)` for time-series analysis.
- Earlier semantic-model profiling was based on a limited sample, so prior observations about null-heavy fields, all-zero numeric columns, or low account cardinality may reflect sampling artifacts rather than confirmed source-data issues.
- `EVENT_OFFER_RPA` and `MESSAGE_TYPE` should still be validated before using them as core segmentation variables.
- If a refreshed random sample or a direct SQL spot check still shows all-zero numeric fields or suspiciously low distinct counts, treat the dataset as potentially incomplete before making business recommendations.
- `PERCENTAGE__DISCOUNT` contains a double underscore in the source column name. Reference the exact source field name in SQL expressions.
- Because this is already weekly grain, avoid re-aggregating to overly coarse levels too early if the question depends on account or PPG variation.