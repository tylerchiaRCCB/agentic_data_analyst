-- ============================================================
-- Delivery coverage diagnostic for Walmart OPD stores
-- Run in Snowsight to understand the true join breakdown.
--
-- Answers:
--   A) How many stores have NO rows at all in F_DELIVERY_STOP_DTL_V?
--      (LEFT JOIN → NULL → pipeline shows DELIVERED_QTY = 0 via COALESCE)
--   B) How many stores have rows but ALL with DELIVERED_QTY = 0?
--      (records exist, just zero quantity)
--   C) How many stores have at least one row with DELIVERED_QTY > 0?
--      (active delivery stores)
-- ============================================================

WITH

-- Step 1: All distinct stores in the OPD panel (excl. sentinel 9999)
opd_stores AS (
  SELECT DISTINCT STORE_NBR
  FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
  WHERE DATE_SID >= '20250101'
    AND STORE_NBR <> 9999
),

-- Step 2: Map each OPD store to its RCCB CUSTOMER_SID
store_customers AS (
  SELECT
    s.STORE_NBR,
    sc.CUSTOMER_SID
  FROM opd_stores s
  LEFT JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER sc
    ON s.STORE_NBR = sc.STORE_NBR
),

-- Step 3: Summarise delivery activity per CUSTOMER_SID
delivery_summary AS (
  SELECT
    d.CUSTOMER_SID,
    COUNT(*)                                AS total_delivery_rows,
    SUM(d.DELIVERED_QTY)                    AS total_delivered_qty,
    COUNT(CASE WHEN d.DELIVERED_QTY > 0 THEN 1 END) AS rows_with_nonzero_qty,
    MAX(d.DELIVERED_QTY)                    AS max_delivered_qty
  FROM CCB_PRD.DM.F_DELIVERY_STOP_DTL_V d
  WHERE d.DELIVERY_DATE_SID >= 20250101
  GROUP BY d.CUSTOMER_SID
)

-- Step 4: Join and categorise every OPD store
SELECT
  CASE
    WHEN sc.CUSTOMER_SID IS NULL
      THEN 'A: No CUSTOMER_SID (bridge miss)'
    WHEN ds.CUSTOMER_SID IS NULL
      THEN 'B: CUSTOMER_SID exists, NO rows in F_DELIVERY_STOP_DTL_V'
    WHEN ds.rows_with_nonzero_qty = 0
      THEN 'C: Rows in delivery table, but ALL DELIVERED_QTY = 0'
    ELSE 'D: Active delivery (DELIVERED_QTY > 0 in at least one stop)'
  END                             AS store_category,
  COUNT(DISTINCT sc.STORE_NBR)    AS store_count,
  ROUND(100.0 * COUNT(DISTINCT sc.STORE_NBR)
        / SUM(COUNT(DISTINCT sc.STORE_NBR)) OVER (), 1) AS pct_of_total

FROM store_customers sc
LEFT JOIN delivery_summary ds ON sc.CUSTOMER_SID = ds.CUSTOMER_SID

GROUP BY 1
ORDER BY 1;
