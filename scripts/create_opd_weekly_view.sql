-- ==========================================================================
-- V_OPD_WEEKLY_<DC>: Pre-joined, weekly-aggregated OPD table with delivery
-- and merch data baked in. Single flat table for pipeline analysis.
-- ==========================================================================
-- Grain: CORE_UPC_10 × STORE_NBR × WEEK_START
-- Joins: OPD fact → V_UPC_PRODUCT (product/PPG)
--                  → V_STORE_CUSTOMER (DC/customer)
--                  → GreenMile delivery (F_STOP ROLE='DC' via D_CUSTOMER_V)
--                  → GreenMile merch (F_STOP ROLE LIKE '%MERCH%' via D_CUSTOMER_V)
-- Filters: 2025+ data, exclude store 9999, INNER JOIN to UPC product
--
-- Usage: Replace <DC_NAME> with the target DC (e.g., 'ALSIP', 'ATLANTA')
--        and <TABLE_SUFFIX> with the DC short name.
--
-- CREATE TABLE (not VIEW) — run once, refresh on schedule.
-- ==========================================================================

CREATE OR REPLACE TABLE CCB_DATASCIENCE_DEV.WALMART_OPD.V_OPD_WEEKLY_ALSIP AS

WITH store_customer_dedup AS (
    -- Deduplicate: one CUSTOMER_ID per store number
    SELECT
        REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1)::INTEGER AS store_nbr,
        MIN(C.CUSTOMER_ID) AS customer_id  -- pick one deterministically
    FROM CCB_PRD.DM.D_CUSTOMER_V C
    WHERE C.CURRENT_IND = 'Y'
      AND C.ACCOUNT_GROUP_DESC LIKE '%WALMART%'
      AND C.BUSINESS_TYPE_DESC = 'DSD'
      AND REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1) IS NOT NULL
    GROUP BY 1
),

-- Step 1: Delivery stops aggregated to store × week
del_weekly AS (
    SELECT
        sc.store_nbr,
        DATE_TRUNC('WEEK', DATE(GM.ROUTE_DATE))                              AS week_start,
        COUNT(*)                                                              AS delivery_stop_count,
        AVG(DATEDIFF('minute', GM.ACTUAL_ARRIVAL_DATE, GM.ACTUAL_DEPARTURE_DATE)) AS avg_delivery_duration_mins,
        SUM(DATEDIFF('minute', GM.ACTUAL_ARRIVAL_DATE, GM.ACTUAL_DEPARTURE_DATE)) AS total_delivery_duration_mins
    FROM CCB_PRD.GREEN_MILE_CORE.F_STOP GM
    JOIN store_customer_dedup sc
        ON GM.CUSTOMER_ID = sc.customer_id
    WHERE DATE(GM.ROUTE_DATE) >= '2025-01-01'
      AND GM.ROLE = 'DC'
      AND GM.ACTUAL_DEPARTURE_DATE IS NOT NULL
    GROUP BY 1, 2
),

-- Step 2: Merch stops aggregated to store × week
merch_weekly AS (
    SELECT
        sc.store_nbr,
        DATE_TRUNC('WEEK', DATE(GM.ROUTE_DATE))                              AS week_start,
        COUNT(*)                                                              AS merch_visit_count,
        AVG(DATEDIFF('minute', GM.ACTUAL_ARRIVAL_DATE, GM.ACTUAL_DEPARTURE_DATE)) AS avg_merch_duration_mins,
        SUM(DATEDIFF('minute', GM.ACTUAL_ARRIVAL_DATE, GM.ACTUAL_DEPARTURE_DATE)) AS total_merch_duration_mins
    FROM CCB_PRD.GREEN_MILE_CORE.F_STOP GM
    JOIN store_customer_dedup sc
        ON GM.CUSTOMER_ID = sc.customer_id
    WHERE DATE(GM.ROUTE_DATE) >= '2025-01-01'
      AND GM.ROLE LIKE '%MERCH%'
      AND GM.ACTUAL_DEPARTURE_DATE IS NOT NULL
    GROUP BY 1, 2
),

-- Step 3: OPD weekly aggregated to UPC × store × week
opd_weekly AS (
    SELECT
        -- Time
        DATE_TRUNC('WEEK', TRY_TO_DATE(opd.DATE_SID, 'YYYYMMDD'))  AS WEEK_START,
        COUNT(DISTINCT opd.DATE_SID)                                AS DAYS_IN_WEEK,

        -- Store / Customer / DC
        opd.STORE_NBR,
        sc.CUSTOMER_SID,
        sc.CUSTOMER_ID,
        sc.CUSTOMER_DESC,
        sc.DISTRIBUTION_CENTER_DESC,
        sc.DISTRIBUTION_CENTER_SID,
        sc.MANAGEDBY_SID,

        -- Product / PPG
        opd.CORE_UPC_10,
        up.PRODUCT_ID,
        up.PRODUCT_SID,
        up.PRODUCT_DESC,
        up.PROMOTED_PACKAGE_GROUP_DESC                              AS PPG,

        -- OPD product attributes
        opd.BRAND,
        opd.CATEGORY,
        opd.FLAVOR,
        opd.SIZE,
        opd.ORIGINAL_ITEM_DESC,

        -- FTPR
        SUM(opd.FTPR_NMRTR)                    AS FTPR_NMRTR,
        SUM(opd.FTPR_DNMNTR)                   AS FTPR_DNMNTR,
        SUM(opd.FTPR_QTY)                      AS FTPR_QTY,

        -- Nil pick
        SUM(opd.NIL_PICK_QTY)                  AS NIL_PICK_QTY,
        SUM(opd.NIL_PICK_COUNT)                AS NIL_PICK_COUNT,

        -- Substitution
        SUM(opd.PRESUB_QTY)                    AS PRESUB_QTY,
        SUM(opd.PRESUB_RATE_NMRTR)             AS PRESUB_RATE_NMRTR,
        SUM(opd.PRESUB_RATE_DNMNTR)            AS PRESUB_RATE_DNMNTR,
        SUM(opd.POSTSUB_RATE_NMRTR)            AS POSTSUB_RATE_NMRTR,
        SUM(opd.POSTSUB_RATE_DNMNTR)           AS POSTSUB_RATE_DNMNTR,

        -- Scheduled / unscheduled nil picks
        SUM(opd.SCHDL_NIL_PICK_QTY)            AS SCHDL_NIL_PICK_QTY,
        SUM(opd.SCHDL_NIL_PICK_RATE_NMRTR)     AS SCHDL_NIL_PICK_RATE_NMRTR,
        SUM(opd.SCHDL_NIL_PICK_RATE_DNMNTR)    AS SCHDL_NIL_PICK_RATE_DNMNTR,
        SUM(opd.UNSCHDL_NIL_PICK_QTY)          AS UNSCHDL_NIL_PICK_QTY,
        SUM(opd.UNSCHDL_NIL_PICK_RATE_NMTR)    AS UNSCHDL_NIL_PICK_RATE_NMRTR,
        SUM(opd.UNSCHDL_NIL_PICK_RATE_DNMTR)   AS UNSCHDL_NIL_PICK_RATE_DNMNTR,

        -- Convenience rates
        SUM(opd.FTPR_NMRTR) / NULLIF(SUM(opd.FTPR_DNMNTR), 0)                                  AS FTPR_RATE,
        SUM(opd.SCHDL_NIL_PICK_RATE_NMRTR) / NULLIF(SUM(opd.SCHDL_NIL_PICK_RATE_DNMNTR), 0)    AS NIL_PICK_RATE,
        SUM(opd.PRESUB_RATE_NMRTR) / NULLIF(SUM(opd.PRESUB_RATE_DNMNTR), 0)                     AS PRESUB_RATE,
        SUM(opd.POSTSUB_RATE_NMRTR) / NULLIF(SUM(opd.POSTSUB_RATE_DNMNTR), 0)                   AS POSTSUB_RATE

    FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA  opd
    INNER JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_UPC_PRODUCT  up
        ON opd.CORE_UPC_10 = up.CORE_UPC_10
    LEFT JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER  sc
        ON opd.STORE_NBR = sc.STORE_NBR
    WHERE
        opd.DATE_SID >= '20250101'
        AND opd.STORE_NBR != 9999
        -- DC filter: change for each market
        AND sc.DISTRIBUTION_CENTER_DESC ILIKE '%ALSIP%'
    GROUP BY
        DATE_TRUNC('WEEK', TRY_TO_DATE(opd.DATE_SID, 'YYYYMMDD')),
        opd.STORE_NBR, sc.CUSTOMER_SID, sc.CUSTOMER_ID, sc.CUSTOMER_DESC,
        sc.DISTRIBUTION_CENTER_DESC, sc.DISTRIBUTION_CENTER_SID, sc.MANAGEDBY_SID,
        opd.CORE_UPC_10, up.PRODUCT_ID, up.PRODUCT_SID, up.PRODUCT_DESC,
        up.PROMOTED_PACKAGE_GROUP_DESC,
        opd.BRAND, opd.CATEGORY, opd.FLAVOR, opd.SIZE, opd.ORIGINAL_ITEM_DESC
)

-- Step 4: Final join — OPD + delivery + merch, all at store × week
SELECT
    o.*,

    -- Delivery (store × week level, left joined)
    COALESCE(d.delivery_stop_count, 0)          AS DELIVERY_STOP_COUNT,
    d.avg_delivery_duration_mins                AS AVG_DELIVERY_DURATION_MINS,
    d.total_delivery_duration_mins              AS TOTAL_DELIVERY_DURATION_MINS,
    CASE WHEN d.store_nbr IS NOT NULL THEN 1 ELSE 0 END AS IS_DELIVERY_ACTIVE_WEEK,

    -- Merch (store × week level, left joined)
    COALESCE(m.merch_visit_count, 0)            AS MERCH_VISIT_COUNT,
    m.avg_merch_duration_mins                   AS AVG_MERCH_DURATION_MINS,
    m.total_merch_duration_mins                 AS TOTAL_MERCH_DURATION_MINS,
    CASE WHEN m.store_nbr IS NOT NULL THEN 1 ELSE 0 END AS IS_MERCH_ACTIVE_WEEK

FROM opd_weekly o
LEFT JOIN del_weekly d
    ON o.STORE_NBR = d.store_nbr AND o.WEEK_START = d.week_start
LEFT JOIN merch_weekly m
    ON o.STORE_NBR = m.store_nbr AND o.WEEK_START = m.week_start
;
