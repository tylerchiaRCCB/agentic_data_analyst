# Walmart OPD — Nil-Pick & First Time Pick Rate (FTPR)

## Data Source
Walmart Luminate / Retail Link — Online, Pickup, and Delivery (OPD) order fulfillment data for RCCB (Reyes Coca-Cola Bottling) products.

## Grain
One row = one **UPC × Store × Date**. `DATE_SID` is an integer date key in `YYYYMMDD` format.

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
| `CATEGORY` | Product category (e.g., SH Coconut Water, SSD, etc.) |
| `SIZE` | Package size (e.g., "16 OZ SINGLE", "12oz 8pk PET") |
| `ORIGINAL_UPC` | Product UPC identifier |

## Business Context
- **FTPR** (First Time Pick Rate) is the primary OPD service metric. Higher is better. Target is typically ≥ 95%.
- **Nil-picks** are failed picks — the item was ordered but not available on the shelf at pick time. Lower is better.
- Nil-picks can be attributed to **KO responsibility** (supplier didn't deliver / out of stock at DC) or **Walmart responsibility** (store didn't shelve / phantom inventory).
- Nil Pick rate can be calculated as SCHDL_NIL_PICK_RATE_NMRTR / SCHDL_NIL_PICK_RATE_DNMNTR
- **Pre-substitution** happens when the customer picks an alternative before the order is picked. **Post-substitution** happens when the picker substitutes at pick time.
- **Scheduled vs unscheduled nil-picks** distinguish between picks that fail during the planned window vs outside it.
- RCCB is a Coca-Cola bottler serving convenience and grocery retail; Walmart is a key account.

## Guardrail Pairings
- When FTPR declines, check whether nil-picks rose (they should be inversely correlated).
- When nil-picks rise, check KO vs WM attribution flags to determine accountability.
- Substitution rates can mask nil-pick severity — a high pre-sub rate may hide true out-of-stock impact.

## Known Considerations
- `DATE_SID` is integer format `YYYYMMDD`, not a standard date — parse accordingly.
- Product descriptor columns (BRAND, CATEGORY, FLAVOR, ITEM_DESC, SIZE) are available in the full Snowflake table but excluded from the synthetic sample to avoid inconsistent UPC-to-attribute mappings.

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