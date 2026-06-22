# Walmart OPD — In-Stock Performance × RCCB Internal Data

## Data Source
Walmart Luminate / Retail Link — Online, Pickup, and Delivery (OPD) order fulfillment data for RCCB (Reyes Coca-Cola Bottling) products, enriched with RCCB internal product, customer, distribution center, delivery, merchandising, and calendar data.

## Tables & Grain

### Primary Fact: OPD Daily (`WALMART_STANDARDIZED_EXTERNAL_DATA`)
One row = one **UPC × Store × Date**. `DATE_SID` is a VARCHAR date key in `YYYYMMDD` format.

### Related Tables (joined via bridge views)

| Table | Source | Join Path | Purpose |
|---|---|---|---|
| `V_STORE_CUSTOMER` | `CCB_DATASCIENCE_DEV.WALMART_OPD` | `STORE_NBR → STORE_NBR` | Maps Walmart store numbers to RCCB customers, distribution centers, and territory hierarchy |
| `V_UPC_PRODUCT` | `CCB_DATASCIENCE_DEV.WALMART_OPD` | `CORE_UPC_10 → CORE_UPC_10` | Maps Walmart UPCs to RCCB product IDs, descriptions, and Promoted Package Groups (PPG) |
| `F_DELIVERY_STOP_DTL_V` | `CCB_PRD.DM` | via `CUSTOMER_SID` and/or `PRODUCT_SID` from bridges | RCCB delivery execution — cases delivered, delivery frequency |
| `F_STOP` | `CCB_PRD.GREEN_MILE_CORE` | via `CUSTOMER_SID` from store bridge | GreenMile merchandising and delivery stop events — visit count, duration |
| `D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V` | `CCB_PRD.DM` | `DATE_SID → DATE_SID` | Coke fiscal calendar — fiscal year/period/week, holidays, day of week |

## Key Metrics

| Column | Meaning | How to compute the rate |
|---|---|---|
| `FTPR_QTY` | First Time Pick Rate quantity — units successfully picked on first attempt | `FTPR_NMRTR / FTPR_DNMNTR` = FTPR % |
| `FTPR_NMRTR` | FTPR numerator (units picked successfully on first try) | — |
| `FTPR_DNMNTR` | FTPR denominator (total units ordered) | — |
| `NIL_PICK_QTY` | Nil-pick quantity — units that could not be picked (out of stock at pick time) | — |
| `NIL_PICK_COUNT` | Count of nil-pick events | — |
| `TY_NIL_PICK_KO_FLAG` | Nil-pick attributed to KO (Coca-Cola) responsibility | 1 = KO-attributable |
| `TY_NIL_PICK_WM_FLAG` | Nil-pick attributed to Walmart responsibility | 1 = WM-attributable |
| `TY_NIL_PICK_POSSIBLE_PI` | Nil-pick flagged as possible phantom inventory | — |
| `PRESUB_QTY` | Pre-substitution quantity (customer-initiated substitution before pick) | — |
| `PRESUB_RATE_NMRTR / _DNMNTR` | Pre-substitution rate numerator / denominator | `NMRTR / DNMNTR` |
| `POSTSUB_RATE_NMRTR / _DNMNTR` | Post-substitution rate numerator / denominator | `NMRTR / DNMNTR` |
| `SCHDL_NIL_PICK_QTY` | Scheduled nil-pick quantity (within scheduled delivery window) | — |
| `SCHDL_NIL_PICK_RATE_NMRTR / _DNMNTR` | Scheduled nil-pick rate | `NMRTR / DNMNTR` |
| `UNSCHDL_NIL_PICK_QTY` | Unscheduled nil-pick quantity (outside scheduled window) | — |
| `UNSCHDL_NIL_PICK_RATE_NMTR / _DNMTR` | Unscheduled nil-pick rate | `NMTR / DNMTR` |

## Dimensions

| Column | Meaning |
|---|---|
| `UNIQUE_KEY` | Surrogate/hash key uniquely identifying each row |
| `DATE_SID` | Date key in YYYYMMDD format |
| `STORE_NBR` | Walmart store number |
| `BRAND` | Product brand (Coca-Cola, Monster, Dasani, Powerade, Gold Peak, Topo Chico, smartwater) |
| `CATEGORY` | Product category (SSD, ENERGY, Water, Isotonics, Tea, RTD Coffee, Enh Water, etc.) |
| `FLAVOR` | Product flavor variant |
| `ORIGINAL_ITEM_DESC` | Full product description from Walmart |
| `SIZE` | Package size (e.g., "16 OZ SINGLE", "12oz 8pk PET") |
| `ORIGINAL_UPC` | Product UPC identifier |
| `UPC_NO_LEADING_ZEROS` | UPC with leading zeros stripped |
| `CORE_UPC_10` | 10-digit core UPC — **join key** to RCCB product master via `V_UPC_PRODUCT` |

## Cross-Table Dimensions (via bridge views)

| Column | Bridge View | Meaning |
|---|---|---|
| `DISTRIBUTION_CENTER_DESC` | `V_STORE_CUSTOMER` | RCCB distribution center name serving the Walmart store |
| `CUSTOMER_SID` | `V_STORE_CUSTOMER` | RCCB customer surrogate key — join to delivery and merch tables |
| `CUSTOMER_ID` | `V_STORE_CUSTOMER` | RCCB customer natural key |
| `PRODUCT_ID` | `V_UPC_PRODUCT` | RCCB product (material) ID — 6-digit identifier |
| `PRODUCT_SID` | `V_UPC_PRODUCT` | RCCB product surrogate key — join to delivery tables |
| `PRODUCT_DESC` | `V_UPC_PRODUCT` | RCCB product description |
| `PROMOTED_PACKAGE_GROUP_DESC` | `V_UPC_PRODUCT` | PPG — groups products for trade promotion planning |
| `FISCAL_YEAR` / `FISCAL_PERIOD_NUM` / `FISCAL_WEEK_NUM` | `D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V` | Coke fiscal calendar fields |
| `HOLIDAY_IND` / `HOLIDAY_DESC` | `D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V` | Holiday indicator and name |
| `DAY_OF_WEEK_DESC` | `D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V` | Day of week name |

## Business Context
- **FTPR** (First Time Pick Rate) is the primary OPD service metric. Higher is better. Target is typically ≥ 95%.
- **Nil-picks** are failed picks — the item was ordered but not available on the shelf at pick time. Lower is better.
- Nil-pick attribution flags exist (`TY_NIL_PICK_KO_FLAG`, `TY_NIL_PICK_WM_FLAG`, `TY_NIL_PICK_POSSIBLE_PI`) but their exact definitions are unconfirmed — verify meaning with the Walmart OPD data owner before interpreting.
- Nil Pick rate can be calculated as SCHDL_NIL_PICK_RATE_NMRTR / SCHDL_NIL_PICK_RATE_DNMNTR
- **Pre-substitution** happens when the customer picks an alternative before the order is picked. **Post-substitution** happens when the picker substitutes at pick time.
- **Scheduled vs unscheduled nil-picks** distinguish between picks that fail during the planned window vs outside it.
- RCCB is a Coca-Cola bottler serving convenience and grocery retail; Walmart is a key account.

## Relationship Hypotheses
When analyzing in-stock drivers, consider these cross-table relationships:
- **DC Performance**: Join OPD → `V_STORE_CUSTOMER` to group FTPR/nil-pick rates by distribution center. Identify which DCs have the worst in-stock metrics and whether KO attribution is concentrated.
- **Delivery Execution**: Join OPD → `V_STORE_CUSTOMER` → `F_DELIVERY_STOP_DTL_V` to correlate delivery volume and frequency with FTPR. **Coverage note (verified Jan 2025 – Apr 2026)**: 563 of 623 OPD stores (90.4%) have active RCCB delivery (`DELIVERED_QTY > 0` in at least one stop). 43 stores (6.9%) have a `CUSTOMER_SID` but no rows in `F_DELIVERY_STOP_DTL_V` — these are genuine no-delivery stores. 17 stores (2.7%) have no `CUSTOMER_SID` at all (bridge miss). Any pipeline output reporting far fewer delivery-active stores is a SQL aggregation artifact, not ground truth — validate delivery SQL against this diagnostic before interpreting coverage.
- **Merch Execution**: Join OPD → `V_STORE_CUSTOMER` → `F_STOP` to test whether stores with more merchandising visits or longer merch time have better FTPR. Filter `ROLE LIKE '%MERCH%'` for merch stops, `ROLE = 'DC'` for delivery stops.
- **Product-Level Supply**: Join OPD → `V_UPC_PRODUCT` → `F_DELIVERY_STOP_DTL_V` to analyze delivery volume at the product level. Products with low delivery frequency relative to pick demand may have higher nil-pick rates.
- **Calendar Effects**: Join OPD → `D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V` to check for holiday impacts, day-of-week patterns, and fiscal period trends on in-stock performance.
- **Trade Promotions**: PPG from `V_UPC_PRODUCT` can link to `CCB_PRD.ANAPLAN_RAW_SHARE.TPO_V` to check if promo weeks show worse FTPR (demand spike not met by supply).

## Guardrail Pairings
- When FTPR declines, check whether nil-picks rose (they should be inversely correlated).
- When nil-picks rise, check KO vs WM attribution flags to determine accountability.
- Substitution rates can mask nil-pick severity — a high pre-sub rate may hide true out-of-stock impact.
- When a DC shows poor FTPR, check both its KO attribution rate (supply-side) and delivery volume (is it underserving?).
- When merch visits are low for a store, check if nil-pick rates are disproportionately high — merch gaps may cause phantom inventory.

## Known Considerations
- `DATE_SID` is VARCHAR format `YYYYMMDD`, not a standard date — use `TRY_TO_DATE(DATE_SID, 'YYYYMMDD')` for date arithmetic.
- `STORE_NBR = 9999` is a sentinel/rollup code — always exclude with `STORE_NBR != 9999`.
- Always compute rates as `SUM(numerator) / NULLIF(SUM(denominator), 0)`. Never use `AVG` of pre-computed row-level rates — that introduces Simpson's Paradox.
- The store-to-customer mapping uses `REGEXP_SUBSTR(CUSTOMER_DESC, '#([0-9]+)')` — pharmacies are excluded from the bridge view to avoid duplicate store numbers.
- The UPC-to-product bridge filters to `MATERIAL_TYPE = 'ZFER'` (finished goods), `PRODUCT_ID > 99999`, and `PPG IS NOT NULL` to keep only active SKUs.
- GreenMile `ACTUAL_ARRIVAL_DATE` and `ACTUAL_DEPARTURE_DATE` are native TIMESTAMP columns — use directly with `DATEDIFF()`. Filter by `ROUTE_DATE` for date ranges.

## Column Reference (Snowflake Schema)

| Column | Type | Description |
|---|---|---|
| `UNIQUE_KEY` | NUMBER(19,0) | Surrogate/hash key uniquely identifying each row |
| `DATE_SID` | VARCHAR | Date identifier in YYYYMMDD format (e.g., 20260409) |
| `STORE_NBR` | NUMBER(38,0) | Walmart store number |
| `CATEGORY` | VARCHAR(1000) | Product category (e.g., Energy, SSD, Isotonics, Enh Water) |
| `SIZE` | VARCHAR(1000) | Package size description (e.g., "16 OZ SINGLE", "12oz 8pk PET") |
| `ORIGINAL_UPC` | VARCHAR(1000) | Original UPC barcode number |
| `FTPR_QTY` | NUMBER(38,4) | First Time Pick Rate quantity — units ordered for first-time picks |
| `FTPR_NMRTR` | NUMBER(38,4) | First Time Pick Rate numerator (successful first picks) |
| `FTPR_DNMNTR` | NUMBER(38,4) | First Time Pick Rate denominator (total first pick attempts). FTPR = NMRTR/DNMNTR |
| `NIL_PICK_QTY` | NUMBER(38,4) | Nil pick quantity — units that could not be fulfilled |
| `NIL_PICK_COUNT` | NUMBER(38,4) | Count of nil pick occurrences |
| `TY_NIL_PICK_KO_FLAG` | VARCHAR(1000) | Flag indicating if this-year nil pick is attributable to KO (Coca-Cola) |
| `TY_NIL_PICK_WM_FLAG` | VARCHAR(1000) | Flag indicating if this-year nil pick is attributable to Walmart |
| `TY_NIL_PICK_POSSIBLE_PI` | VARCHAR(1000) | Flag indicating if this-year nil pick is possibly due to a phantom inventory issue |
| `PRESUB_QTY` | NUMBER(38,4) | Pre-substitution quantity — units ordered before substitutions applied |
| `PRESUB_RATE_NMRTR` | NUMBER(38,4) | Pre-substitution rate numerator |
| `PRESUB_RATE_DNMNTR` | NUMBER(38,4) | Pre-substitution rate denominator |
| `POSTSUB_RATE_NMRTR` | NUMBER(38,4) | Post-substitution rate numerator |
| `POSTSUB_RATE_DNMNTR` | NUMBER(38,4) | Post-substitution rate denominator |
| `SCHDL_NIL_PICK_QTY` | NUMBER(38,4) | Scheduled nil pick quantity — nil picks during scheduled delivery windows |
| `SCHDL_NIL_PICK_RATE_NMRTR` | NUMBER(38,4) | Scheduled nil pick rate numerator |
| `SCHDL_NIL_PICK_RATE_DNMNTR` | NUMBER(38,4) | Scheduled nil pick rate denominator |
| `UNSCHDL_NIL_PICK_QTY` | NUMBER(38,4) | Unscheduled nil pick quantity — nil picks outside scheduled windows |
| `UNSCHDL_NIL_PICK_RATE_NMTR` | NUMBER(38,4) | Unscheduled nil pick rate numerator |
| `UNSCHDL_NIL_PICK_RATE_DNMTR` | NUMBER(38,4) | Unscheduled nil pick rate denominator |