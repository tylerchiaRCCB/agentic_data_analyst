-- =============================================================================
-- Deploy Walmart OPD Multi-Table Semantic View
-- =============================================================================
-- This script creates a semantic view in CCB_DATASCIENCE_DEV.WALMART_OPD
-- using SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML.
--
-- Prerequisites:
--   1. Run scripts/create_bridge_views.sql first (creates V_STORE_CUSTOMER and V_UPC_PRODUCT)
--   2. Ensure role CCB_DATASCIENCE_SYSADMIN_SNOWFLAKE has access to:
--      - CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
--      - CCB_DATASCIENCE_DEV.WALMART_OPD schema (for bridge views)
--      - CCB_PRD.GREEN_MILE_CORE.F_STOP
--      - CCB_PRD.DM.F_DELIVERY_STOP_DTL_V
--      - CCB_PRD.DM.D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V
--
-- Usage: Execute in Snowsight with role CCB_DATASCIENCE_SYSADMIN_SNOWFLAKE
-- =============================================================================

USE ROLE CCB_DATASCIENCE_SYSADMIN_SNOWFLAKE;
USE WAREHOUSE CCB_DATASCIENCE_WH;
USE DATABASE CCB_DATASCIENCE_DEV;
USE SCHEMA WALMART_OPD;

-- Drop existing semantic view if it exists
DROP  VIEW IF EXISTS WALMART_OPD;

-- Create the semantic view from YAML specification
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  'CCB_DATASCIENCE_DEV.WALMART_OPD',
  $$
name: walmart_opd
description: >
  Walmart Online, Pickup, and Delivery (OPD) in-stock execution data enriched
  with RCCB internal product, customer, distribution center, delivery execution,
  and merchandising data. Enables analysis of in-stock performance drivers across
  the RCCB supply chain.

tables:
  # =========================================================================
  # FACT: OPD Daily Performance
  # =========================================================================
  - name: walmart_opd_daily
    description: >
      Fact table at UPC × Store × Date grain. Each row is one product-store-day
      observation of OPD pick performance. Contains numerators and denominators
      for rate calculations — always use SUM(numerator)/SUM(denominator) for
      aggregated rates, never AVG of pre-computed rates.
    base_table:
      database: CCB_DATASCIENCE_DEV
      schema: PUBLIC
      table: WALMART_STANDARDIZED_EXTERNAL_DATA

    dimensions:
      - name: store_nbr
        description: "Walmart store number. Integer identifier for each physical store location."
        expr: STORE_NBR
        data_type: NUMBER
        synonyms:
          - "store"
          - "store number"
          - "store id"
          - "location"

      - name: brand
        description: "Product brand name (e.g., Coca-Cola, Monster, Dasani, Topo Chico)."
        expr: BRAND
        data_type: VARCHAR
        synonyms:
          - "brand name"
          - "product brand"
        sample_values:
          - "Coca-Cola"
          - "Monster"
          - "Dasani"
          - "Powerade"
          - "Gold Peak"
          - "Topo Chico"
          - "smartwater"

      - name: category
        description: >
          Product category. 18 categories covering RCCB's full beverage portfolio.
          Key categories: SSD (Sparkling Soft Drinks), ENERGY, Water, Isotonics,
          Tea, RTD Coffee, Enh Water (Enhanced Water), Sparkling Wtr, CSD, Juice.
        expr: CATEGORY
        data_type: VARCHAR
        synonyms:
          - "product category"
          - "category name"
          - "beverage category"
        sample_values:
          - "SSD"
          - "ENERGY"
          - "Water"
          - "Isotonics"
          - "Tea"
          - "RTD Coffee"
          - "Enh Water"
          - "Sparkling Wtr"
          - "CSD"
          - "Juice"
          - "Still"
          - "Protein"
          - "Milk"
          - "Topo Chico"
          - "Shelf Stable Juice"
          - "Drops"
          - "SH Coconut Water"
          - "Powdered Soft Drinks"
        is_enum: true

      - name: flavor
        description: "Product flavor variant."
        expr: FLAVOR
        data_type: VARCHAR
        synonyms:
          - "flavor name"
          - "variant"

      - name: original_item_desc
        description: "Full product description from Walmart (includes brand, flavor, size, pack)."
        expr: ORIGINAL_ITEM_DESC
        data_type: VARCHAR
        synonyms:
          - "item description"
          - "product name"
          - "product description"
          - "item name"

      - name: size
        description: "Package size descriptor (e.g., 12 OZ, 20 OZ, 12PK 12OZ)."
        expr: SIZE
        data_type: VARCHAR
        synonyms:
          - "package size"
          - "pack size"

      - name: original_upc
        description: "Universal Product Code — unique product identifier."
        expr: ORIGINAL_UPC
        data_type: VARCHAR
        synonyms:
          - "upc"
          - "upc code"
          - "product code"
          - "item code"

      - name: upc_no_leading_zeros
        description: "UPC with leading zeros stripped for join compatibility."
        expr: UPC_NO_LEADING_ZEROS
        data_type: VARCHAR

      - name: core_upc_10
        description: "10-digit core UPC for cross-reference with RCCB product master and Nielsen/IRI data."
        expr: CORE_UPC_10
        data_type: VARCHAR

      - name: ko_attribution_flag
        description: >
          KO (RCCB) attribution flag for nil picks. '1' means the nil pick is
          attributed to RCCB (supplier-side) — e.g., delivery miss, DC out-of-stock.
        expr: TY_NIL_PICK_KO_FLAG
        data_type: VARCHAR
        synonyms:
          - "ko flag"
          - "rccb flag"
          - "supplier flag"
        sample_values:
          - "0"
          - "1"
        is_enum: true

      - name: wm_attribution_flag
        description: >
          Walmart attribution flag for nil picks. '1' means the nil pick is
          attributed to Walmart (retailer-side) — e.g., shelf not stocked,
          planogram issue, store-ops failure.
        expr: TY_NIL_PICK_WM_FLAG
        data_type: VARCHAR
        synonyms:
          - "wm flag"
          - "walmart flag"
          - "retailer flag"
        sample_values:
          - "0"
          - "1"
        is_enum: true

      - name: phantom_inventory_flag
        description: >
          Phantom inventory flag. '1' means the nil pick may be due to phantom
          inventory — the system shows the item in stock but it cannot be found
          on the shelf. Indicates inventory record inaccuracy.
        expr: TY_NIL_PICK_POSSIBLE_PI
        data_type: VARCHAR
        synonyms:
          - "phantom inventory"
          - "pi flag"
          - "phantom flag"
        sample_values:
          - "0"
          - "1"
        is_enum: true

    time_dimensions:
      - name: date_sid
        description: >
          Date identifier in YYYYMMDD string format (e.g., '20260115').
          Use TRY_TO_DATE(DATE_SID, 'YYYYMMDD') to convert to DATE type
          for date arithmetic and time-series analysis.
        expr: DATE_SID
        data_type: VARCHAR
        synonyms:
          - "date"
          - "day"
          - "observation date"
          - "pick date"

    facts:
      - name: ftpr_numerator
        description: "First Time Pick Rate numerator — number of successful first-time picks."
        expr: FTPR_NMRTR
        data_type: NUMBER
        synonyms:
          - "successful picks"
          - "first time picks"

      - name: ftpr_denominator
        description: "First Time Pick Rate denominator — total pick attempts."
        expr: FTPR_DNMNTR
        data_type: NUMBER
        synonyms:
          - "total picks"
          - "pick attempts"
          - "total orders"

      - name: ftpr_qty
        description: "First Time Pick Rate quantity (units successfully picked first time)."
        expr: FTPR_QTY
        data_type: NUMBER

      - name: nil_pick_qty
        description: "Total nil-pick quantity — items that could not be picked."
        expr: NIL_PICK_QTY
        data_type: NUMBER
        synonyms:
          - "nil picks"
          - "missed picks"
          - "failed picks"

      - name: nil_pick_count
        description: "Count of nil-pick events."
        expr: NIL_PICK_COUNT
        data_type: NUMBER

      - name: presub_qty
        description: "Pre-substitution quantity — customer-initiated substitutions before pick."
        expr: PRESUB_QTY
        data_type: NUMBER
        synonyms:
          - "pre substitution"

      - name: presub_rate_numerator
        description: "Pre-substitution rate numerator."
        expr: PRESUB_RATE_NMRTR
        data_type: NUMBER

      - name: presub_rate_denominator
        description: "Pre-substitution rate denominator."
        expr: PRESUB_RATE_DNMNTR
        data_type: NUMBER

      - name: postsub_rate_numerator
        description: "Post-substitution rate numerator — picker-initiated substitutions after nil pick."
        expr: POSTSUB_RATE_NMRTR
        data_type: NUMBER

      - name: postsub_rate_denominator
        description: "Post-substitution rate denominator."
        expr: POSTSUB_RATE_DNMNTR
        data_type: NUMBER

      - name: scheduled_nil_pick_qty
        description: "Scheduled nil-pick quantity — nil picks on items with scheduled delivery."
        expr: SCHDL_NIL_PICK_QTY
        data_type: NUMBER
        synonyms:
          - "scheduled nil picks"

      - name: scheduled_nil_pick_rate_numerator
        description: "Scheduled nil-pick rate numerator."
        expr: SCHDL_NIL_PICK_RATE_NMRTR
        data_type: NUMBER

      - name: scheduled_nil_pick_rate_denominator
        description: "Scheduled nil-pick rate denominator."
        expr: SCHDL_NIL_PICK_RATE_DNMNTR
        data_type: NUMBER

      - name: unscheduled_nil_pick_qty
        description: "Unscheduled nil-pick quantity — nil picks on items without scheduled delivery."
        expr: UNSCHDL_NIL_PICK_QTY
        data_type: NUMBER
        synonyms:
          - "unscheduled nil picks"

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
        description: >
          First Time Pick Rate = SUM(FTPR_NMRTR) / SUM(FTPR_DNMNTR).
          Always compute from numerator/denominator sums. Never average
          pre-computed row-level rates — that introduces Simpson's Paradox.
          Target is >= 95%.
        expr: SUM(FTPR_NMRTR) / NULLIF(SUM(FTPR_DNMNTR), 0)
        synonyms:
          - "ftpr"
          - "first time pick rate"
          - "pick rate"
          - "fill rate"

      - name: nil_pick_rate
        description: >
          Nil Pick Rate = SUM(SCHDL_NIL_PICK_RATE_NMRTR) / SUM(SCHDL_NIL_PICK_RATE_DNMNTR).
          Inverse relationship with FTPR but not exact complement due to substitutions.
        expr: SUM(SCHDL_NIL_PICK_RATE_NMRTR) / NULLIF(SUM(SCHDL_NIL_PICK_RATE_DNMNTR), 0)
        synonyms:
          - "nil rate"
          - "miss rate"

      - name: ko_attribution_rate
        description: "Share of nil picks attributed to RCCB (KO)."
        expr: SUM(CASE WHEN TY_NIL_PICK_KO_FLAG = '1' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN NIL_PICK_QTY > 0 THEN 1 ELSE 0 END), 0)
        synonyms:
          - "ko rate"
          - "rccb attribution"
          - "supplier attribution"

      - name: wm_attribution_rate
        description: "Share of nil picks attributed to Walmart (WM)."
        expr: SUM(CASE WHEN TY_NIL_PICK_WM_FLAG = '1' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN NIL_PICK_QTY > 0 THEN 1 ELSE 0 END), 0)
        synonyms:
          - "wm rate"
          - "walmart attribution"
          - "retailer attribution"

      - name: phantom_inventory_rate
        description: "Share of nil picks flagged as possible phantom inventory."
        expr: SUM(CASE WHEN TY_NIL_PICK_POSSIBLE_PI = '1' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN NIL_PICK_QTY > 0 THEN 1 ELSE 0 END), 0)
        synonyms:
          - "pi rate"
          - "phantom rate"

      - name: presub_rate
        description: "Pre-substitution rate = SUM(PRESUB_RATE_NMRTR) / SUM(PRESUB_RATE_DNMNTR)."
        expr: SUM(PRESUB_RATE_NMRTR) / NULLIF(SUM(PRESUB_RATE_DNMNTR), 0)
        synonyms:
          - "pre substitution rate"

      - name: postsub_rate
        description: "Post-substitution rate = SUM(POSTSUB_RATE_NMRTR) / SUM(POSTSUB_RATE_DNMNTR)."
        expr: SUM(POSTSUB_RATE_NMRTR) / NULLIF(SUM(POSTSUB_RATE_DNMNTR), 0)
        synonyms:
          - "post substitution rate"

    filters:
      - name: recent_data
        description: "Filter to data from 2025 onward (most relevant for analysis)."
        expr: "DATE_SID >= '20250101'"

      - name: exclude_sentinel_stores
        description: "Exclude store 9999 which may be a sentinel/rollup code."
        expr: "STORE_NBR != 9999"

  # =========================================================================
  # DIMENSION: Store → Customer → Distribution Center (Bridge View)
  # =========================================================================
  - name: store_customer
    description: >
      Bridge table mapping Walmart store numbers to RCCB customer records and
      distribution centers. Extracted from D_CUSTOMER_V where the store number
      is parsed from the customer description (e.g., "WALMART SUPERCENTER #1234").
      Filtered to current, active, DSD Walmart accounts only.
    base_table:
      database: CCB_DATASCIENCE_DEV
      schema: WALMART_OPD
      table: V_STORE_CUSTOMER

    primary_key:
      columns:
        - STORE_NBR

    dimensions:
      - name: store_nbr
        description: "Walmart store number — join key to OPD data."
        expr: STORE_NBR
        data_type: NUMBER

      - name: customer_sid
        description: "RCCB customer surrogate ID — join key to delivery and merch tables."
        expr: CUSTOMER_SID
        data_type: NUMBER

      - name: customer_id
        description: "RCCB customer natural key."
        expr: CUSTOMER_ID
        data_type: VARCHAR

      - name: customer_desc
        description: "Full customer description (e.g., WALMART SUPERCENTER #1234)."
        expr: CUSTOMER_DESC
        data_type: VARCHAR

      - name: distribution_center_desc
        description: >
          RCCB distribution center name serving this Walmart store.
          Use for DC-level performance analysis.
        expr: DISTRIBUTION_CENTER_DESC
        data_type: VARCHAR
        synonyms:
          - "dc"
          - "distribution center"
          - "dc name"
          - "warehouse"

      - name: distribution_center_sid
        description: "Distribution center surrogate key."
        expr: DISTRIBUTION_CENTER_SID
        data_type: NUMBER

      - name: managedby_sid
        description: "Territory/management hierarchy key — for org-level rollups."
        expr: MANAGEDBY_SID
        data_type: NUMBER

  # =========================================================================
  # DIMENSION: UPC → Product → PPG (Bridge View)
  # =========================================================================
  - name: upc_product
    description: >
      Bridge table mapping 10-digit core UPCs to RCCB product (material) IDs
      and Promoted Package Groups (PPG). Built from CONA material master
      (EA_UPC and PAK_UPC) joined to CCB product dimension. Filtered to
      finished goods (ZFER) only.
    base_table:
      database: CCB_DATASCIENCE_DEV
      schema: WALMART_OPD
      table: V_UPC_PRODUCT

    primary_key:
      columns:
        - CORE_UPC_10

    dimensions:
      - name: core_upc_10
        description: "10-digit core UPC — join key to OPD data."
        expr: CORE_UPC_10
        data_type: VARCHAR

      - name: product_id
        description: "RCCB product (material) ID — 6-digit identifier."
        expr: PRODUCT_ID
        data_type: VARCHAR
        synonyms:
          - "material id"
          - "sku"
          - "material number"

      - name: product_sid
        description: "RCCB product surrogate key — join key to delivery tables."
        expr: PRODUCT_SID
        data_type: NUMBER

      - name: product_desc
        description: "RCCB product description from material master."
        expr: PRODUCT_DESC
        data_type: VARCHAR
        synonyms:
          - "rccb product name"
          - "material description"

      - name: promoted_package_group_desc
        description: >
          Promoted Package Group (PPG) description. Groups related products
          for trade promotion planning. Join key to promo calendar (TPO).
        expr: PROMOTED_PACKAGE_GROUP_DESC
        data_type: VARCHAR
        synonyms:
          - "ppg"
          - "package group"
          - "promo group"

  # =========================================================================
  # FACT: Delivery Stop Detail — RCCB delivery execution at customer × product
  # =========================================================================
  - name: delivery_stops
    description: >
      RCCB delivery stop detail fact table. Contains actual delivery quantities
      at the customer × product × date grain. Join to store_customer via
      CUSTOMER_SID and to upc_product via PRODUCT_SID to correlate delivery
      execution with OPD in-stock performance. Higher delivery frequency and
      volume may correlate with better FTPR.
    base_table:
      database: CCB_PRD
      schema: DM
      table: F_DELIVERY_STOP_DTL_V

    dimensions:
      - name: customer_sid
        description: "Customer surrogate key — join to store_customer."
        expr: CUSTOMER_SID
        data_type: NUMBER

      - name: product_sid
        description: "Product surrogate key — join to upc_product."
        expr: PRODUCT_SID
        data_type: NUMBER

      - name: distribution_center_sid
        description: "DC surrogate key for the fulfilling distribution center."
        expr: DISTRIBUTION_CENTER_SID
        data_type: NUMBER

    time_dimensions:
      - name: delivery_date_sid
        description: "Delivery date in YYYYMMDD numeric format (e.g., 20250115)."
        expr: DELIVERY_DATE_SID
        data_type: NUMBER
        synonyms:
          - "delivery date"
          - "date"

    facts:
      - name: ordered_qty
        description: "Quantity ordered for delivery."
        expr: ORDERED_QTY
        data_type: NUMBER
        synonyms:
          - "ordered quantity"

      - name: loaded_qty
        description: "Quantity loaded onto the truck."
        expr: LOADED_QTY
        data_type: NUMBER
        synonyms:
          - "loaded quantity"

      - name: delivered_qty
        description: "Quantity actually delivered to the customer."
        expr: DELIVERED_QTY
        data_type: NUMBER
        synonyms:
          - "cases delivered"
          - "delivery cases"
          - "delivered quantity"

      - name: returned_qty
        description: "Quantity returned (not accepted by customer)."
        expr: RETURNED_QTY
        data_type: NUMBER
        synonyms:
          - "returns"

      - name: out_of_stock_qty
        description: "Quantity that could not be fulfilled due to out-of-stock at DC."
        expr: OUT_OF_STOCK_QTY
        data_type: NUMBER
        synonyms:
          - "OOS quantity"
          - "out of stock"

      - name: damaged_qty
        description: "Quantity marked as damaged."
        expr: DAMAGED_QTY
        data_type: NUMBER
        synonyms:
          - "damaged"

    metrics:
      - name: total_delivered
        description: "Total quantity delivered."
        expr: SUM(DELIVERED_QTY)
        synonyms:
          - "total delivery volume"
          - "total cases delivered"

      - name: total_ordered
        description: "Total quantity ordered for delivery."
        expr: SUM(ORDERED_QTY)
        synonyms:
          - "total ordered"

      - name: delivery_fill_rate
        description: "Delivery fill rate — delivered vs ordered."
        expr: SUM(DELIVERED_QTY) / NULLIF(SUM(ORDERED_QTY), 0)
        synonyms:
          - "fill rate"

      - name: delivery_stop_count
        description: "Number of delivery line items (proxy for delivery frequency)."
        expr: COUNT(*)
        synonyms:
          - "delivery count"
          - "delivery frequency"

  # =========================================================================
  # FACT: GreenMile Merchandising Stops — merch execution at customer level
  # =========================================================================
  - name: merch_stops
    description: >
      GreenMile merchandising and delivery stop data. Each row is one stop event
      at a customer location. ROLE distinguishes delivery ('DC') from merchandising
      ('MERCH'-containing). Use to analyze whether merch visit frequency and
      duration correlate with in-stock improvement.
    base_table:
      database: CCB_PRD
      schema: GREEN_MILE_CORE
      table: F_STOP

    dimensions:
      - name: customer_sid
        description: "Customer surrogate key — join to store_customer."
        expr: CUSTOMER_SID
        data_type: NUMBER

      - name: role
        description: >
          Stop role: 'DC' = delivery driver, values containing 'MERCH' = merchandiser.
          Filter to ROLE = 'DC' for delivery stops or ROLE LIKE '%MERCH%' for merch stops.
        expr: ROLE
        data_type: VARCHAR
        synonyms:
          - "stop type"
          - "visit type"
        sample_values:
          - "DC"
          - "MERCH"

      - name: instructions
        description: >
          Stop instructions. For merch stops, filter INSTRUCTIONS LIKE '%MERCH%'
          to confirm merchandising activity.
        expr: INSTRUCTIONS
        data_type: VARCHAR

    time_dimensions:
      - name: route_date
        description: "Route date for the stop. Use for date-range filtering on GreenMile data."
        expr: ROUTE_DATE
        data_type: TIMESTAMP
        synonyms:
          - "stop date"
          - "visit date"

      - name: actual_arrival_date
        description: "Actual arrival timestamp at the customer location."
        expr: ACTUAL_ARRIVAL_DATE
        data_type: TIMESTAMP
        synonyms:
          - "arrival time"
          - "check in"

      - name: actual_departure_date
        description: "Actual departure timestamp from the customer location."
        expr: ACTUAL_DEPARTURE_DATE
        data_type: TIMESTAMP
        synonyms:
          - "departure time"
          - "check out"

    metrics:
      - name: merch_visit_count
        description: "Count of merchandising visits (ROLE LIKE '%MERCH%')."
        expr: COUNT(CASE WHEN ROLE LIKE '%MERCH%' THEN 1 END)
        synonyms:
          - "merch frequency"
          - "number of merch visits"

      - name: delivery_visit_count
        description: "Count of delivery visits (ROLE = 'DC')."
        expr: COUNT(CASE WHEN ROLE = 'DC' THEN 1 END)
        synonyms:
          - "delivery frequency"

      - name: avg_merch_duration_mins
        description: "Average merchandising stop duration in minutes."
        expr: >
          AVG(CASE WHEN ROLE LIKE '%MERCH%'
            THEN DATEDIFF('minute', ACTUAL_ARRIVAL_DATE, ACTUAL_DEPARTURE_DATE)
          END)
        synonyms:
          - "merch time"
          - "time in store"

  # =========================================================================
  # DIMENSION: Fiscal Calendar
  # =========================================================================
  - name: fiscal_calendar
    description: >
      RCCB fiscal calendar with Coke fiscal year and week numbers.
      Join on DATE_SID to align OPD data with fiscal periods.
    base_table:
      database: CCB_PRD
      schema: DM
      table: D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V

    dimensions:
      - name: fiscal_year
        description: "Coke fiscal year."
        expr: FISCAL_YEAR
        data_type: NUMBER
        synonyms:
          - "year"

      - name: fiscal_week_num
        description: "Coke fiscal week number within the year."
        expr: FISCAL_WEEK_NUM
        data_type: NUMBER
        synonyms:
          - "week"
          - "fiscal week"

    time_dimensions:
      - name: date_sid
        description: "Date key in YYYYMMDD numeric format — join to OPD and delivery tables."
        expr: DATE_SID
        data_type: NUMBER

# =============================================================================
# RELATIONSHIPS — Define how tables join
# =============================================================================
# Bridge views guarantee uniqueness on STORE_NBR and CORE_UPC_10 via dedup logic.
# Fiscal calendar and delivery/merch joins are not declared here (no unique key)
# but are demonstrated in verified_queries.
relationships:
  # OPD → Store/Customer/DC bridge (STORE_NBR is unique in V_STORE_CUSTOMER)
  - name: opd_to_store_customer
    left_table: walmart_opd_daily
    right_table: store_customer
    relationship_columns:
      - left_column: STORE_NBR
        right_column: STORE_NBR

  # OPD → UPC/Product bridge (CORE_UPC_10 is unique in V_UPC_PRODUCT)
  - name: opd_to_upc_product
    left_table: walmart_opd_daily
    right_table: upc_product
    relationship_columns:
      - left_column: CORE_UPC_10
        right_column: CORE_UPC_10

# =============================================================================
# VERIFIED QUERIES — Teach Cortex Analyst the correct join patterns
# =============================================================================
verified_queries:
  # --- Single-table OPD queries ---
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

  # --- Cross-table: OPD × DC (via store_customer bridge) ---
  - name: ftpr_by_dc
    question: "Which distribution center has the worst in-stock metrics?"
    sql: |
      SELECT
        SC.DISTRIBUTION_CENTER_DESC AS dc,
        SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(OPD.SCHDL_NIL_PICK_RATE_NMRTR) / NULLIF(SUM(OPD.SCHDL_NIL_PICK_RATE_DNMNTR), 0) AS nil_pick_rate,
        SUM(OPD.FTPR_DNMNTR) AS total_picks,
        COUNT(DISTINCT OPD.STORE_NBR) AS store_count
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
      JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
        ON OPD.STORE_NBR = SC.STORE_NBR
      WHERE OPD.DATE_SID >= '20250101'
        AND OPD.STORE_NBR != 9999
      GROUP BY SC.DISTRIBUTION_CENTER_DESC
      ORDER BY ftpr_rate ASC
    use_as_onboarding_question: true

  - name: weekly_ftpr_by_dc
    question: "What is the weekly FTPR trend by distribution center?"
    sql: |
      SELECT
        DATE_TRUNC('WEEK', TRY_TO_DATE(OPD.DATE_SID, 'YYYYMMDD')) AS week_start,
        SC.DISTRIBUTION_CENTER_DESC AS dc,
        SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
      JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
        ON OPD.STORE_NBR = SC.STORE_NBR
      WHERE OPD.DATE_SID >= '20250101'
        AND OPD.STORE_NBR != 9999
      GROUP BY 1, SC.DISTRIBUTION_CENTER_DESC
      ORDER BY 1, SC.DISTRIBUTION_CENTER_DESC

  - name: ko_attribution_by_dc
    question: "Which DC has the highest KO (RCCB) attributed nil pick rate?"
    sql: |
      SELECT
        SC.DISTRIBUTION_CENTER_DESC AS dc,
        SUM(CASE WHEN OPD.TY_NIL_PICK_KO_FLAG = '1' THEN 1 ELSE 0 END) AS ko_nil_picks,
        COUNT(CASE WHEN OPD.NIL_PICK_QTY > 0 THEN 1 END) AS total_nil_picks,
        SUM(CASE WHEN OPD.TY_NIL_PICK_KO_FLAG = '1' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(CASE WHEN OPD.NIL_PICK_QTY > 0 THEN 1 END), 0) AS ko_attribution_rate
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
      JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
        ON OPD.STORE_NBR = SC.STORE_NBR
      WHERE OPD.DATE_SID >= '20250101'
        AND OPD.STORE_NBR != 9999
      GROUP BY SC.DISTRIBUTION_CENTER_DESC
      HAVING COUNT(CASE WHEN OPD.NIL_PICK_QTY > 0 THEN 1 END) > 100
      ORDER BY ko_attribution_rate DESC

  # --- Cross-table: OPD × Product (via upc_product bridge) ---
  - name: ftpr_by_ppg
    question: "What is the FTPR by promoted package group (PPG)?"
    sql: |
      SELECT
        UP.PROMOTED_PACKAGE_GROUP_DESC AS ppg,
        SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(OPD.FTPR_DNMNTR) AS total_picks
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
      JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_UPC_PRODUCT UP
        ON OPD.CORE_UPC_10 = UP.CORE_UPC_10
      WHERE OPD.DATE_SID >= '20250101'
        AND OPD.STORE_NBR != 9999
      GROUP BY UP.PROMOTED_PACKAGE_GROUP_DESC
      HAVING SUM(OPD.FTPR_DNMNTR) > 500
      ORDER BY ftpr_rate ASC

  # --- Cross-table: OPD × Delivery (via store_customer → delivery) ---
  - name: delivery_volume_vs_ftpr
    question: "Is there a relationship between delivery volume and FTPR?"
    sql: |
      WITH store_ftpr AS (
        SELECT
          OPD.STORE_NBR,
          SC.CUSTOMER_SID,
          SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
          SUM(OPD.FTPR_DNMNTR) AS total_picks
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
        JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
          ON OPD.STORE_NBR = SC.STORE_NBR
        WHERE OPD.DATE_SID >= '20250101'
          AND OPD.STORE_NBR != 9999
        GROUP BY OPD.STORE_NBR, SC.CUSTOMER_SID
        HAVING SUM(OPD.FTPR_DNMNTR) > 500
      ),
      store_delivery AS (
        SELECT
          D.CUSTOMER_SID,
          SUM(D.DELIVERED_QTY) AS total_cases_delivered,
          COUNT(DISTINCT D.DELIVERY_DATE_SID) AS delivery_days
        FROM CCB_PRD.DM.F_DELIVERY_STOP_DTL_V D
        WHERE D.DELIVERY_DATE_SID >= 20250101
        GROUP BY D.CUSTOMER_SID
      )
      SELECT
        F.STORE_NBR,
        F.ftpr_rate,
        F.total_picks,
        COALESCE(DEL.total_cases_delivered, 0) AS total_cases_delivered,
        COALESCE(DEL.delivery_days, 0) AS delivery_days,
        CASE
          WHEN DEL.delivery_days > 0
          THEN DEL.total_cases_delivered / DEL.delivery_days
          ELSE 0
        END AS avg_cases_per_delivery_day
      FROM store_ftpr F
      LEFT JOIN store_delivery DEL ON F.CUSTOMER_SID = DEL.CUSTOMER_SID
      ORDER BY F.ftpr_rate ASC
      LIMIT 50
    use_as_onboarding_question: true

  # --- Cross-table: OPD × Merch (via store_customer → merch_stops) ---
  - name: merch_visits_vs_ftpr
    question: "Do stores with more merch visits have better FTPR?"
    sql: |
      WITH store_ftpr AS (
        SELECT
          OPD.STORE_NBR,
          SC.CUSTOMER_SID,
          SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
          SUM(OPD.FTPR_DNMNTR) AS total_picks
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
        JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
          ON OPD.STORE_NBR = SC.STORE_NBR
        WHERE OPD.DATE_SID >= '20250101'
          AND OPD.STORE_NBR != 9999
        GROUP BY OPD.STORE_NBR, SC.CUSTOMER_SID
        HAVING SUM(OPD.FTPR_DNMNTR) > 500
      ),
      store_merch AS (
        SELECT
          GM.CUSTOMER_SID,
          COUNT(CASE WHEN GM.ROLE LIKE '%MERCH%' THEN 1 END) AS merch_visits,
          COUNT(CASE WHEN GM.ROLE = 'DC' THEN 1 END) AS delivery_visits,
          AVG(CASE WHEN GM.ROLE LIKE '%MERCH%'
            THEN DATEDIFF('minute', GM.ACTUAL_ARRIVAL_DATE, GM.ACTUAL_DEPARTURE_DATE)
          END) AS avg_merch_duration_mins
        FROM CCB_PRD.GREEN_MILE_CORE.F_STOP GM
        WHERE GM.ROUTE_DATE >= '2025-01-01'
        GROUP BY GM.CUSTOMER_SID
      )
      SELECT
        F.STORE_NBR,
        F.ftpr_rate,
        F.total_picks,
        COALESCE(M.merch_visits, 0) AS merch_visits,
        COALESCE(M.delivery_visits, 0) AS delivery_visits,
        M.avg_merch_duration_mins
      FROM store_ftpr F
      LEFT JOIN store_merch M ON F.CUSTOMER_SID = M.CUSTOMER_SID
      ORDER BY F.ftpr_rate ASC
      LIMIT 50
    use_as_onboarding_question: true

  # --- Cross-table: OPD × Fiscal Calendar ---
  - name: ftpr_by_fiscal_week
    question: "What is the FTPR trend by fiscal week?"
    sql: |
      SELECT
        CAL.FISCAL_YEAR,
        CAL.FISCAL_WEEK_NUM,
        SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(OPD.FTPR_DNMNTR) AS total_picks
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
      JOIN CCB_PRD.DM.D_FISCAL_CALENDAR_DATE_COKE_CY_PY_V CAL
        ON OPD.DATE_SID = CAL.DATE_SID
      WHERE OPD.DATE_SID >= '20250101'
        AND OPD.STORE_NBR != 9999
      GROUP BY CAL.FISCAL_YEAR, CAL.FISCAL_WEEK_NUM
      ORDER BY CAL.FISCAL_YEAR, CAL.FISCAL_WEEK_NUM

  - name: ftpr_by_day_of_week
    question: "Which day of the week has the worst FTPR?"
    sql: |
      SELECT
        DAYNAME(TRY_TO_DATE(OPD.DATE_SID, 'YYYYMMDD')) AS day_of_week,
        SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
        SUM(OPD.FTPR_DNMNTR) AS total_picks
      FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
      WHERE OPD.DATE_SID >= '20250101'
        AND OPD.STORE_NBR != 9999
      GROUP BY DAYNAME(TRY_TO_DATE(OPD.DATE_SID, 'YYYYMMDD'))
      ORDER BY ftpr_rate ASC

  # --- Cross-table: OPD × DC × Delivery (full chain) ---
  - name: dc_delivery_and_ftpr
    question: "How does delivery volume per DC relate to in-stock performance?"
    sql: |
      WITH dc_ftpr AS (
        SELECT
          SC.DISTRIBUTION_CENTER_DESC AS dc,
          SUM(OPD.FTPR_NMRTR) / NULLIF(SUM(OPD.FTPR_DNMNTR), 0) AS ftpr_rate,
          SUM(OPD.NIL_PICK_QTY) AS total_nil_picks,
          COUNT(DISTINCT OPD.STORE_NBR) AS store_count
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
        JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
          ON OPD.STORE_NBR = SC.STORE_NBR
        WHERE OPD.DATE_SID >= '20250101'
          AND OPD.STORE_NBR != 9999
        GROUP BY SC.DISTRIBUTION_CENTER_DESC
      ),
      dc_delivery AS (
        SELECT
          SC.DISTRIBUTION_CENTER_DESC AS dc,
          SUM(D.DELIVERED_QTY) AS total_cases,
          COUNT(DISTINCT D.DELIVERY_DATE_SID) AS delivery_days,
          COUNT(DISTINCT D.CUSTOMER_SID) AS customers_delivered
        FROM CCB_PRD.DM.F_DELIVERY_STOP_DTL_V D
        JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER SC
          ON D.CUSTOMER_SID = SC.CUSTOMER_SID
        WHERE D.DELIVERY_DATE_SID >= 20250101
        GROUP BY SC.DISTRIBUTION_CENTER_DESC
      )
      SELECT
        F.dc,
        F.ftpr_rate,
        F.total_nil_picks,
        F.store_count,
        COALESCE(DEL.total_cases, 0) AS total_cases_delivered,
        COALESCE(DEL.delivery_days, 0) AS active_delivery_days,
        COALESCE(DEL.customers_delivered, 0) AS customers_delivered
      FROM dc_ftpr F
      LEFT JOIN dc_delivery DEL ON F.dc = DEL.dc
      ORDER BY F.ftpr_rate ASC
  $$
);
