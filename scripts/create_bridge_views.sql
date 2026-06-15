-- =============================================================================
-- Bridge Views for Walmart OPD ↔ RCCB Internal Data Integration
-- Run in Snowsight with CCB_DATASCIENCE_SYSADMIN_SNOWFLAKE role
-- =============================================================================

USE ROLE CCB_DATASCIENCE_SYSADMIN_SNOWFLAKE;
USE DATABASE CCB_DATASCIENCE_DEV;
USE SCHEMA WALMART_OPD;

-- =============================================================================
-- 1. V_STORE_CUSTOMER — Walmart Store Number → RCCB Customer + DC
--    Extracts store number from CUSTOMER_DESC (e.g., "WALMART SUPERCENTER #1234")
--    and maps to CUSTOMER_SID, CUSTOMER_ID, and Distribution Center.
--    Excludes pharmacies and deduplicates to one customer per store number.
-- =============================================================================
CREATE OR REPLACE VIEW WALMART_OPD.V_STORE_CUSTOMER AS
WITH ranked AS (
    SELECT
        REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1)::INTEGER  AS STORE_NBR,
        C.CUSTOMER_SID,
        C.CUSTOMER_ID,
        C.CUSTOMER_DESC,
        C.DISTRIBUTION_CENTER_SID,
        C.DISTRIBUTION_CENTER_DESC,
        C.MANAGEDBY_SID,
        ROW_NUMBER() OVER (
            PARTITION BY REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1)::INTEGER
            ORDER BY
                CASE WHEN C.CUSTOMER_DESC ILIKE '%PHARMACY%' THEN 1 ELSE 0 END,  -- prefer non-pharmacy
                C.CUSTOMER_SID DESC  -- tiebreak: most recent customer_sid
        ) AS rn
    FROM CCB_PRD.DM.D_CUSTOMER_V C
    WHERE C.CURRENT_IND = 'Y'
      AND C.ACCOUNT_GROUP_DESC LIKE '%WALMART%'
      AND C.BUSINESS_TYPE_DESC = 'DSD'
      AND REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1) IS NOT NULL
      AND C.CUSTOMER_DESC NOT ILIKE '%PHARMACY%'
)
SELECT STORE_NBR, CUSTOMER_SID, CUSTOMER_ID, CUSTOMER_DESC,
       DISTRIBUTION_CENTER_SID, DISTRIBUTION_CENTER_DESC, MANAGEDBY_SID
FROM ranked
WHERE rn = 1;

-- =============================================================================
-- 2. V_UPC_PRODUCT — CORE_UPC_10 → RCCB Product (Material) + PPG
--    Maps Walmart UPCs to RCCB Product IDs via CONA material master.
--    Uses EA_UPC with PAK_UPC fallback, filtered to finished goods (ZFER).
-- =============================================================================
CREATE OR REPLACE VIEW WALMART_OPD.V_UPC_PRODUCT AS
WITH upc_material AS (
    -- EA_UPC path
    SELECT DISTINCT
        LEFT(LTRIM(EA_UPC::STRING, '0'), 10)  AS CORE_UPC_10,
        MATERIAL_SHORT_ID                      AS PRODUCT_ID,
        MATERIAL_DESC
    FROM CONA_P_EDW.GENERAL_USE_BAS.BAS_MDM_MATERIAL
    WHERE EA_UPC IS NOT NULL AND EA_UPC <> '0'
      AND MATERIAL_TYPE = 'ZFER'
      AND MATERIAL_DESC NOT LIKE '%DELETE%'
      AND MATERIAL_DESC NOT LIKE 'ND%'
    UNION ALL
    -- PAK_UPC path
    SELECT DISTINCT
        LEFT(LTRIM(PAK_UPC::STRING, '0'), 10),
        MATERIAL_SHORT_ID,
        MATERIAL_DESC
    FROM CONA_P_EDW.GENERAL_USE_BAS.BAS_MDM_MATERIAL
    WHERE PAK_UPC IS NOT NULL AND PAK_UPC <> '0'
      AND MATERIAL_TYPE = 'ZFER'
      AND MATERIAL_DESC NOT LIKE '%DELETE%'
      AND MATERIAL_DESC NOT LIKE 'ND%'
),
upc_dedup AS (
    SELECT CORE_UPC_10,
           MIN(PRODUCT_ID) AS PRODUCT_ID,
           MAX(MATERIAL_DESC) AS CONA_PRODUCT_DESC   -- fallback desc from CONA
    FROM upc_material
    GROUP BY CORE_UPC_10
),
product_dedup AS (
    SELECT
        PRODUCT_ID,
        MAX(PRODUCT_SID)                    AS PRODUCT_SID,
        MAX(PRODUCT_DESC)                   AS PRODUCT_DESC,
        MAX(PROMOTED_PACKAGE_GROUP_DESC)    AS PROMOTED_PACKAGE_GROUP_DESC
    FROM CCB_PRD.DM.D_PRODUCT_V
    WHERE MATERIAL_TYPE_CD = 'ZFER'
    GROUP BY PRODUCT_ID
)
SELECT
    U.CORE_UPC_10,
    U.PRODUCT_ID,
    P.PRODUCT_SID,
    COALESCE(P.PRODUCT_DESC, U.CONA_PRODUCT_DESC) AS PRODUCT_DESC,
    P.PROMOTED_PACKAGE_GROUP_DESC
FROM upc_dedup U
LEFT JOIN product_dedup P ON U.PRODUCT_ID = P.PRODUCT_ID;

-- =============================================================================
-- 3. V_PRODUCT — PRODUCT_SID → Product Description + PPG
--    One row per PRODUCT_SID. Used as a direct dimension for delivery_stops
--    so Cortex can join delivery data to product details without going
--    through the UPC bridge (which is keyed on CORE_UPC_10, not PRODUCT_SID).
-- =============================================================================
CREATE OR REPLACE VIEW WALMART_OPD.V_PRODUCT AS
SELECT
    PRODUCT_SID,
    MAX(PRODUCT_ID)                   AS PRODUCT_ID,
    MAX(PRODUCT_DESC)                 AS PRODUCT_DESC,
    MAX(PROMOTED_PACKAGE_GROUP_DESC)  AS PROMOTED_PACKAGE_GROUP_DESC,
    MAX(MATERIAL_TYPE_CD)             AS MATERIAL_TYPE_CD
FROM CCB_PRD.DM.D_PRODUCT_V
WHERE MATERIAL_TYPE_CD = 'ZFER'
GROUP BY PRODUCT_SID;

-- =============================================================================
-- 4. V_WALMART_OPD — Pre-filtered OPD fact table
--    Inner-joins to V_UPC_PRODUCT to exclude ~58 unmatched UPCs with corrupt
--    nil pick data that inflate KPI aggregations. Also excludes sentinel
--    store 9999. This view should be the base table for all Cortex Analyst
--    queries so that data quality filtering happens automatically.
-- =============================================================================
CREATE OR REPLACE VIEW WALMART_OPD.V_WALMART_OPD AS
SELECT
    OPD.*
FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA OPD
INNER JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_UPC_PRODUCT UP
    ON OPD.CORE_UPC_10 = UP.CORE_UPC_10
WHERE OPD.STORE_NBR != 9999;

-- =============================================================================
-- Verify bridge views
-- =============================================================================

-- Check store-customer bridge row count
SELECT 'V_STORE_CUSTOMER' AS VIEW_NAME, COUNT(*) AS ROW_COUNT FROM WALMART_OPD.V_STORE_CUSTOMER;

-- Check UPC-product bridge row count
SELECT 'V_UPC_PRODUCT' AS VIEW_NAME, COUNT(*) AS ROW_COUNT FROM WALMART_OPD.V_UPC_PRODUCT;

-- Check pre-filtered OPD view row count
SELECT 'V_WALMART_OPD' AS VIEW_NAME, COUNT(*) AS ROW_COUNT FROM WALMART_OPD.V_WALMART_OPD;

-- Check product dimension row count
SELECT 'V_PRODUCT' AS VIEW_NAME, COUNT(*) AS ROW_COUNT FROM WALMART_OPD.V_PRODUCT;

-- Sample: OPD stores that match to RCCB customers
SELECT
    OPD.STORE_NBR,
    SC.CUSTOMER_ID,
    SC.CUSTOMER_DESC,
    SC.DISTRIBUTION_CENTER_DESC AS DC
FROM (SELECT DISTINCT STORE_NBR FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA WHERE STORE_NBR != 9999) OPD
LEFT JOIN WALMART_OPD.V_STORE_CUSTOMER SC ON OPD.STORE_NBR = SC.STORE_NBR
ORDER BY OPD.STORE_NBR
LIMIT 20;

-- Sample: OPD UPCs that match to RCCB products
SELECT
    OPD.CORE_UPC_10,
    OPD.BRAND,
    OPD.ORIGINAL_ITEM_DESC,
    UP.PRODUCT_ID,
    UP.PRODUCT_DESC,
    UP.PROMOTED_PACKAGE_GROUP_DESC AS PPG
FROM (SELECT DISTINCT CORE_UPC_10, BRAND, ORIGINAL_ITEM_DESC FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA LIMIT 50) OPD
LEFT JOIN WALMART_OPD.V_UPC_PRODUCT UP ON OPD.CORE_UPC_10 = UP.CORE_UPC_10
ORDER BY OPD.BRAND, OPD.CORE_UPC_10
LIMIT 20;
