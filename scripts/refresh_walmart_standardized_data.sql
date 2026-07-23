-- refresh_walmart_standardized_data.sql
-- Stored procedure + daily task to refresh WALMART_STANDARDIZED_EXTERNAL_DATA
--
-- This is the source table for V_OPD_WEEKLY_ALSIP (which can be a view on top).
-- Runs daily at 5am UTC (11pm CT previous day) so data is fresh for any analysis.
--
-- To deploy: run this entire script in Snowflake once.
-- To check status: SHOW TASKS IN SCHEMA CCB_DATASCIENCE_DEV.WALMART_OPD;

-- =============================================================================
-- STORED PROCEDURE
-- =============================================================================
CREATE OR REPLACE PROCEDURE CCB_DATASCIENCE_DEV.WALMART_OPD.REFRESH_WALMART_STANDARDIZED_DATA()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
    CREATE OR REPLACE TABLE CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
    CLUSTER BY (DATE_SID)
    AS
    SELECT M.UNIQUE_ID UNIQUE_KEY
      , M.DATE_SID
      , M.STORE_NBR
      , M.BRAND
      , M.CATEGORY
      , M.FLAVOR
      , M.ITEM_NAME AS ORIGINAL_ITEM_DESC
      , M.SIZE
      , M.UPC AS ORIGINAL_UPC
      , C.CUSTOMER_CODES_LIST
      , C.CUSTOMER_CODES_ARRAY
      , CASE WHEN LENGTH(LTRIM(M.UPC::STRING,'0')) = 12 THEN LEFT(LTRIM(M.UPC::STRING, '0'),11)
             WHEN LENGTH(LTRIM(M.UPC::STRING,'0')) = 11 THEN LTRIM(M.UPC::STRING, '0')
             WHEN LENGTH(LTRIM(M.UPC::STRING,'0')) = 10 THEN LTRIM(M.UPC::STRING, '0')
             ELSE LTRIM(M.UPC::STRING, '0')
        END AS UPC_NO_LEADING_ZEROS
      , CASE WHEN LENGTH(LTRIM(M.UPC::STRING,'0')) >= 10 THEN LEFT(LTRIM(M.UPC::STRING,'0'),10)
             ELSE LPAD(LTRIM(M.UPC::STRING,'0'),10,'0')
        END AS CORE_UPC_10
      , M.FTPR_QTY
      , M.FTPR_NMRTR
      , M.FTPR_DNMNTR
      , M.NIL_PICK_QTY
      , M.NIL_PICK_COUNT
      , M.TY_NIL_PICK_KO_FLAG
      , M.TY_NIL_PICK_WM_FLAG
      , M.TY_NIL_PICK_POSSIBLE_PI
      , M.PRESUB_QTY
      , M.PRESUB_RATE_NMRTR
      , M.PRESUB_RATE_DNMNTR
      , M.POSTSUB_RATE_NMRTR
      , M.POSTSUB_RATE_DNMNTR
      , M.SCHDL_NIL_PICK_QTY
      , M.SCHDL_NIL_PICK_RATE_NMRTR
      , M.SCHDL_NIL_PICK_RATE_DNMNTR
      , M.UNSCHDL_NIL_PICK_QTY
      , M.UNSCHDL_NIL_PICK_RATE_NMTR
      , M.UNSCHDL_NIL_PICK_RATE_DNMTR
    FROM CCB_PRD.DM.F_MOOKSTR_OMNI_DAILY_V M
    LEFT JOIN ( SELECT
                  REGEXP_SUBSTR(UPPER(CUSTOMER_DESC), '^([A-Z]+)', 1, 1, 'e', 1) AS CUSTOMER,
                  REGEXP_SUBSTR(CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1)::INTEGER AS STORE_NUMBER,
                  ARRAY_AGG(CUSTOMER_ID) AS CUSTOMER_CODES_ARRAY,
                  LISTAGG(CUSTOMER_ID, ', ') AS CUSTOMER_CODES_LIST,
                  COUNT(*) AS CUSTOMER_COUNT
                FROM CCB_PRD.DM.D_CUSTOMER_V
                WHERE REGEXP_SUBSTR(CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1) IS NOT NULL
                  AND CURRENT_IND = 'Y'
                  AND BUSINESS_TYPE_DESC = 'DSD'
                  AND ACCOUNT_GROUP_DESC ILIKE '%WALMART%'
                  AND CUSTOMER_DESC NOT ILIKE '%VEND%'
                  AND CUSTOMER_ID NOT IN ('601116080')
                GROUP BY ALL) C
      ON M.STORE_NBR = C.STORE_NUMBER
    WHERE M.DATE_SID IS NOT NULL
      AND M.DATE_SID >= 20250101;

    RETURN 'WALMART_STANDARDIZED_EXTERNAL_DATA refreshed at ' || CURRENT_TIMESTAMP()::STRING;
END;
$$;

-- =============================================================================
-- DAILY TASK (runs every day at 5am UTC = 11pm CT previous day)
-- =============================================================================
CREATE OR REPLACE TASK CCB_DATASCIENCE_DEV.WALMART_OPD.REFRESH_WALMART_STANDARDIZED_DAILY
    WAREHOUSE = 'CCB_DATASCIENCE_S_WH'
    SCHEDULE = 'USING CRON 0 5 * * * UTC'
    COMMENT = 'Daily refresh of WALMART_STANDARDIZED_EXTERNAL_DATA from F_MOOKSTR_OMNI_DAILY_V'
AS
    CALL CCB_DATASCIENCE_DEV.WALMART_OPD.REFRESH_WALMART_STANDARDIZED_DATA();

-- Enable the task (tasks start suspended)
ALTER TASK CCB_DATASCIENCE_DEV.WALMART_OPD.REFRESH_WALMART_STANDARDIZED_DAILY RESUME;

-- =============================================================================
-- VERIFY
-- =============================================================================
-- SHOW TASKS IN SCHEMA CCB_DATASCIENCE_DEV.WALMART_OPD;
-- SELECT * FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY()) WHERE NAME = 'REFRESH_WALMART_STANDARDIZED_DAILY' ORDER BY SCHEDULED_TIME DESC LIMIT 5;
