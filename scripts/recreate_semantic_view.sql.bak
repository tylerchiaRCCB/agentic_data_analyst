USE ROLE CCB_DATASCIENCE_SYSADMIN_SNOWFLAKE;
USE DATABASE CCB_DATASCIENCE_DEV;
USE SCHEMA WALMART_OPD;

-- Drop existing view before recreating
DROP SEMANTIC VIEW IF EXISTS CCB_DATASCIENCE_DEV.WALMART_OPD.WALMART_OPD;

CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  'CCB_DATASCIENCE_DEV.WALMART_OPD',
  $$
name: walmart_opd
description: >
  Walmart Online, Pickup, and Delivery (OPD) in-stock execution data for RCCB
  (Reyes Coca-Cola Bottling). Tracks first-time pick rate, nil-pick events
  and their attribution (KO vs Walmart vs Phantom Inventory), pre- and
  post-substitution rates, and scheduled vs unscheduled nil picks.

tables:
  - name: walmart_opd_daily
    description: >
      Fact table at UPC x Store x Date grain. Each row is one product-store-day
      observation of OPD pick performance. Contains numerators and denominators
      for rate calculations.
    base_table:
      database: CCB_DATASCIENCE_DEV
      schema: PUBLIC
      table: WALMART_STANDARDIZED_EXTERNAL_DATA
    dimensions:
      - name: store_nbr
        description: "Walmart store number."
        expr: STORE_NBR
        data_type: NUMBER
        synonyms: ["store", "store number", "store id", "location"]
      - name: brand
        description: "Product brand name."
        expr: BRAND
        data_type: VARCHAR
        synonyms: ["brand name", "product brand"]
        sample_values: ["Coca-Cola", "Monster", "Dasani", "Powerade", "Gold Peak", "Topo Chico", "smartwater"]
      - name: category
        description: "Product category. 18 categories covering RCCB beverage portfolio."
        expr: CATEGORY
        data_type: VARCHAR
        synonyms: ["product category", "category name", "beverage category"]
        sample_values: ["SSD", "ENERGY", "Water", "Isotonics", "Tea", "RTD Coffee", "Enh Water", "Sparkling Wtr", "CSD", "Juice", "Still", "Protein", "Milk", "Topo Chico", "Shelf Stable Juice", "Drops", "SH Coconut Water", "Powdered Soft Drinks"]
        is_enum: true
      - name: flavor
        description: "Product flavor variant."
        expr: FLAVOR
        data_type: VARCHAR
        synonyms: ["flavor name", "variant"]
      - name: original_item_desc
        description: "Full product description from Walmart."
        expr: ORIGINAL_ITEM_DESC
        data_type: VARCHAR
        synonyms: ["item description", "product name", "product description", "item name"]
      - name: size
        description: "Package size descriptor (e.g., 12 OZ, 20 OZ, 12PK 12OZ)."
        expr: SIZE
        data_type: VARCHAR
        synonyms: ["package size", "pack size"]
      - name: original_upc
        description: "Universal Product Code."
        expr: ORIGINAL_UPC
        data_type: VARCHAR
        synonyms: ["upc", "upc code", "product code", "item code"]
      - name: upc_no_leading_zeros
        description: "UPC with leading zeros stripped."
        expr: UPC_NO_LEADING_ZEROS
        data_type: VARCHAR
      - name: core_upc_10
        description: "10-digit core UPC for cross-reference."
        expr: CORE_UPC_10
        data_type: VARCHAR
      - name: ko_attribution_flag
        description: "KO (RCCB) attribution flag for nil picks. 1 = supplier-side."
        expr: TY_NIL_PICK_KO_FLAG
        data_type: VARCHAR
        synonyms: ["ko flag", "rccb flag", "supplier flag"]
        sample_values: ["0", "1"]
        is_enum: true
      - name: wm_attribution_flag
        description: "Walmart attribution flag for nil picks. 1 = retailer-side."
        expr: TY_NIL_PICK_WM_FLAG
        data_type: VARCHAR
        synonyms: ["wm flag", "walmart flag", "retailer flag"]
        sample_values: ["0", "1"]
        is_enum: true
      - name: phantom_inventory_flag
        description: "Phantom inventory flag. 1 = possible phantom inventory."
        expr: TY_NIL_PICK_POSSIBLE_PI
        data_type: VARCHAR
        synonyms: ["phantom inventory", "pi flag", "phantom flag"]
        sample_values: ["0", "1"]
        is_enum: true
    time_dimensions:
      - name: date_sid
        description: "Date in YYYYMMDD string format. Use TRY_TO_DATE(DATE_SID, 'YYYYMMDD') for date ops."
        expr: DATE_SID
        data_type: VARCHAR
        synonyms: ["date", "day", "observation date", "pick date"]
    facts:
      - name: ftpr_numerator
        description: "First Time Pick Rate numerator - successful first-time picks."
        expr: FTPR_NMRTR
        data_type: NUMBER
        synonyms: ["successful picks", "first time picks"]
      - name: ftpr_denominator
        description: "First Time Pick Rate denominator - total pick attempts."
        expr: FTPR_DNMNTR
        data_type: NUMBER
        synonyms: ["total picks", "pick attempts", "total orders"]
      - name: ftpr_qty
        description: "First Time Pick Rate quantity."
        expr: FTPR_QTY
        data_type: NUMBER
      - name: nil_pick_qty
        description: "Total nil-pick quantity - items that could not be picked."
        expr: NIL_PICK_QTY
        data_type: NUMBER
        synonyms: ["nil picks", "missed picks", "failed picks"]
      - name: nil_pick_count
        description: "Count of nil-pick events."
        expr: NIL_PICK_COUNT
        data_type: NUMBER
      - name: presub_qty
        description: "Pre-substitution quantity."
        expr: PRESUB_QTY
        data_type: NUMBER
      - name: presub_rate_numerator
        description: "Pre-substitution rate numerator."
        expr: PRESUB_RATE_NMRTR
        data_type: NUMBER
      - name: presub_rate_denominator
        description: "Pre-substitution rate denominator."
        expr: PRESUB_RATE_DNMNTR
        data_type: NUMBER
      - name: postsub_rate_numerator
        description: "Post-substitution rate numerator."
        expr: POSTSUB_RATE_NMRTR
        data_type: NUMBER
      - name: postsub_rate_denominator
        description: "Post-substitution rate denominator."
        expr: POSTSUB_RATE_DNMNTR
        data_type: NUMBER
      - name: scheduled_nil_pick_qty
        description: "Scheduled nil-pick quantity."
        expr: SCHDL_NIL_PICK_QTY
        data_type: NUMBER
        synonyms: ["scheduled nil picks"]
      - name: scheduled_nil_pick_rate_numerator
        description: "Scheduled nil-pick rate numerator."
        expr: SCHDL_NIL_PICK_RATE_NMRTR
        data_type: NUMBER
      - name: scheduled_nil_pick_rate_denominator
        description: "Scheduled nil-pick rate denominator."
        expr: SCHDL_NIL_PICK_RATE_DNMNTR
        data_type: NUMBER
      - name: unscheduled_nil_pick_qty
        description: "Unscheduled nil-pick quantity."
        expr: UNSCHDL_NIL_PICK_QTY
        data_type: NUMBER
        synonyms: ["unscheduled nil picks"]
      - name: unscheduled_nil_pick_rate_numerator
        description: "Unscheduled nil-pick rate numerator."
        expr: UNSCHDL_NIL_PICK_RATE_NMTR
        data_type: NUMBER
      - name: unscheduled_nil_pick_rate_denominator
        description: "Unscheduled nil-pick rate denominator."
        expr: UNSCHDL_NIL_PICK_RATE_DNMTR
        data_type: NUMBER
    metrics:
      - name: ftpr_rate
        description: "First Time Pick Rate. Target >= 95%."
        expr: SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0)
        synonyms: ["ftpr", "first time pick rate", "pick rate", "fill rate"]
      - name: nil_pick_rate
        description: "Nil Pick Rate = SUM(SCHDL_NIL_PICK_RATE_NMRTR) / SUM(SCHDL_NIL_PICK_RATE_DNMNTR)."
        expr: SUM(SCHDL_NIL_PICK_RATE_NMRTR) / NULLIF(SUM(SCHDL_NIL_PICK_RATE_DNMNTR), 0)
        synonyms: ["nil rate", "miss rate"]
      - name: ko_attribution_rate
        description: "Share of nil picks attributed to RCCB (KO)."
        expr: SUM(CASE WHEN TY_NIL_PICK_KO_FLAG = '1' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN NIL_PICK_QTY > 0 THEN 1 ELSE 0 END), 0)
        synonyms: ["ko rate", "rccb attribution", "supplier attribution"]
      - name: wm_attribution_rate
        description: "Share of nil picks attributed to Walmart."
        expr: SUM(CASE WHEN TY_NIL_PICK_WM_FLAG = '1' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN NIL_PICK_QTY > 0 THEN 1 ELSE 0 END), 0)
        synonyms: ["wm rate", "walmart attribution", "retailer attribution"]
      - name: phantom_inventory_rate
        description: "Share of nil picks flagged as possible phantom inventory."
        expr: SUM(CASE WHEN TY_NIL_PICK_POSSIBLE_PI = '1' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN NIL_PICK_QTY > 0 THEN 1 ELSE 0 END), 0)
        synonyms: ["pi rate", "phantom rate"]
      - name: presub_rate
        description: "Pre-substitution rate."
        expr: SUM(PRESUB_RATE_NMRTR) / NULLIF(SUM(PRESUB_RATE_DNMNTR), 0)
        synonyms: ["pre substitution rate"]
      - name: postsub_rate
        description: "Post-substitution rate."
        expr: SUM(POSTSUB_RATE_NMRTR) / NULLIF(SUM(POSTSUB_RATE_DNMNTR), 0)
        synonyms: ["post substitution rate"]
    filters:
      - name: recent_data
        description: "Filter to data from 2025 onward."
        expr: "DATE_SID >= '20250101'"
      - name: exclude_sentinel_stores
        description: "Exclude store 9999 sentinel/rollup code."
        expr: "STORE_NBR != 9999"

verified_queries:
  - name: overall_ftpr
    question: "What is the overall first time pick rate?"
    sql: |
      SELECT
        SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0) AS ftpr_rate
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999
    use_as_onboarding_question: true

  - name: weekly_ftpr_trend
    question: "What is the weekly FTPR trend?"
    sql: |
      SELECT
        DATE_TRUNC('WEEK', TRY_TO_DATE(DATE_SID, 'YYYYMMDD')) AS week_start,
        SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0) AS ftpr_rate
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999
      GROUP BY 1
      ORDER BY 1
    use_as_onboarding_question: true

  - name: ftpr_by_category
    question: "What is the FTPR by category?"
    sql: |
      SELECT
        CATEGORY,
        SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(FTPR_DNMNTR) AS total_picks
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999
      GROUP BY CATEGORY
      ORDER BY ftpr_rate ASC

  - name: worst_stores_by_ftpr
    question: "Which stores have the worst FTPR?"
    sql: |
      SELECT
        STORE_NBR,
        SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(FTPR_DNMNTR) AS total_picks,
        SUM(NIL_PICK_QTY) AS total_nil_picks
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999
      GROUP BY STORE_NBR
      HAVING SUM(FTPR_DNMNTR) > 1000
      ORDER BY ftpr_rate ASC
      LIMIT 20
    use_as_onboarding_question: true

  - name: nil_pick_attribution_breakdown
    question: "What is the nil pick attribution breakdown between KO and Walmart?"
    sql: |
      SELECT
        SUM(CASE WHEN TY_NIL_PICK_KO_FLAG = '1' THEN 1 ELSE 0 END) AS ko_attributed,
        SUM(CASE WHEN TY_NIL_PICK_WM_FLAG = '1' THEN 1 ELSE 0 END) AS wm_attributed,
        SUM(CASE WHEN TY_NIL_PICK_POSSIBLE_PI = '1' THEN 1 ELSE 0 END) AS phantom_inventory,
        COUNT(CASE WHEN NIL_PICK_QTY > 0 THEN 1 END) AS total_nil_pick_events
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999

  - name: energy_category_performance
    question: "How is the ENERGY category performing compared to other categories?"
    sql: |
      SELECT
        CATEGORY,
        SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(SCHDL_NIL_PICK_RATE_NMRTR) / NULLIF(SUM(SCHDL_NIL_PICK_RATE_DNMNTR), 0) AS nil_pick_rate,
        SUM(FTPR_DNMNTR) AS total_picks
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999
      GROUP BY CATEGORY
      ORDER BY ftpr_rate ASC

  - name: weekly_ftpr_by_category
    question: "What is the weekly FTPR trend by category?"
    sql: |
      SELECT
        DATE_TRUNC('WEEK', TRY_TO_DATE(DATE_SID, 'YYYYMMDD')) AS week_start,
        CATEGORY,
        SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0) AS ftpr_rate
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
      WHERE DATE_SID >= '20250101'
        AND STORE_NBR != 9999
      GROUP BY 1, CATEGORY
      ORDER BY 1, CATEGORY
  $$
);

-- Re-grant access to the ETL service account role
GRANT SELECT ON SEMANTIC VIEW CCB_DATASCIENCE_DEV.WALMART_OPD.WALMART_OPD TO ROLE CCB_DATASCIENCE_SNOWFLAKE;
