"""Direct join validation for delivery and merch pipeline data paths.

Bypasses Cortex Analyst completely — runs the exact SQL patterns the
pipeline's verified-query hints use, against Snowflake directly.

Run:
    cd /home/azureuser/cloudfiles/code/Users/Tyler.Chia/agentic-data-analyst
    python scratch/test_delivery_merch_joins.py

Pass criteria printed at the end. Any FAIL line needs investigation.
"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

import textwrap
from src.data_access.snowflake_client import SnowflakeClient, SnowflakeConfig
import pandas as pd

# ── connection ───────────────────────────────────────────────────────────────
sf_config = SnowflakeConfig.from_team_keyvault()
sf = SnowflakeClient(sf_config)
conn = sf.connect()

def run(label: str, sql: str) -> pd.DataFrame:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    cur = conn.cursor()
    try:
        cur.execute(sql)
        cols = [c[0].upper() for c in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        cur.close()
    print(df.to_string(index=False))
    return df

results: dict[str, bool] = {}

# ── TEST 1: Bridge coverage ──────────────────────────────────────────────────
df1 = run("TEST 1 — OPD → V_STORE_CUSTOMER bridge coverage", """
    SELECT
        COUNT(DISTINCT opd.STORE_NBR)                            AS opd_stores_total,
        COUNT(DISTINCT sc.CUSTOMER_SID)                          AS stores_with_customer_sid,
        COUNT(DISTINCT opd.STORE_NBR)
            - COUNT(DISTINCT sc.CUSTOMER_SID)                    AS bridge_miss_count
    FROM (
        SELECT DISTINCT STORE_NBR
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
        WHERE DATE_SID >= '20250101' AND STORE_NBR <> 9999
    ) opd
    LEFT JOIN CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER sc
        ON opd.STORE_NBR = sc.STORE_NBR
""")
bridge_miss = int(df1["BRIDGE_MISS_COUNT"].iloc[0])
total_stores = int(df1["OPD_STORES_TOTAL"].iloc[0])
results["TEST1_bridge_miss_lt_30"] = bridge_miss <= 30
print(f"  → bridge_miss={bridge_miss}, total={total_stores}  {'PASS' if results['TEST1_bridge_miss_lt_30'] else 'FAIL'}")

# ── TEST 2: Delivery join — store-week coverage (dashboard pattern) ──────────
df2 = run("TEST 2 — Delivery via F_STOP ROLE=DC + D_CUSTOMER_V.CUSTOMER_ID", """
    WITH
    opd_stores AS (
        SELECT DISTINCT STORE_NBR
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
        WHERE DATE_SID >= '20250101' AND STORE_NBR <> 9999
    ),
    delivery_stores AS (
        SELECT DISTINCT
            REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1)::INTEGER AS STORE_NBR
        FROM CCB_PRD.GREEN_MILE_CORE.F_STOP GM
        JOIN CCB_PRD.DM.D_CUSTOMER_V C
            ON GM.CUSTOMER_ID = C.CUSTOMER_ID
            AND C.CURRENT_IND = 'Y'
            AND C.ACCOUNT_GROUP_DESC LIKE '%WALMART%'
            AND C.BUSINESS_TYPE_DESC = 'DSD'
            AND REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1) IS NOT NULL
        WHERE DATE(GM.ROUTE_DATE) >= '2025-01-01'
          AND GM.ROLE = 'DC'
          AND GM.ACTUAL_DEPARTURE_DATE IS NOT NULL
    )
    SELECT
        COUNT(DISTINCT o.STORE_NBR)                                  AS opd_stores,
        COUNT(DISTINCT d.STORE_NBR)                                  AS delivery_active_stores,
        ROUND(100.0 * COUNT(DISTINCT d.STORE_NBR)
              / NULLIF(COUNT(DISTINCT o.STORE_NBR), 0), 1)           AS delivery_coverage_pct
    FROM opd_stores o
    LEFT JOIN delivery_stores d ON o.STORE_NBR = d.STORE_NBR
""")
delivery_active = int(df2["DELIVERY_ACTIVE_STORES"].iloc[0])
delivery_pct = float(df2["DELIVERY_COVERAGE_PCT"].iloc[0])
results["TEST2_delivery_active_gte_500"] = delivery_active >= 500
results["TEST2_delivery_pct_gte_80"] = delivery_pct >= 80.0
print(f"  → delivery_active_stores={delivery_active} (expected ~563)  {'PASS' if results['TEST2_delivery_active_gte_500'] else 'FAIL'}")
print(f"  → delivery_coverage_pct={delivery_pct}% (expected ~90%)     {'PASS' if results['TEST2_delivery_pct_gte_80'] else 'FAIL'}")

# ── TEST 3: Merch join — store-week coverage ─────────────────────────────────
df3 = run("TEST 3 — Merch join (GreenMile F_STOP) coverage", """
    WITH
    opd_stores AS (
        SELECT DISTINCT STORE_NBR
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
        WHERE DATE_SID >= '20250101' AND STORE_NBR <> 9999
    ),
    merch_stores AS (
        SELECT DISTINCT sc.STORE_NBR
        FROM CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER sc
        INNER JOIN CCB_PRD.GREEN_MILE_CORE.F_STOP m
            ON sc.CUSTOMER_SID = m.CUSTOMER_SID
        WHERE m.ROUTE_DATE >= '2025-01-01'
          AND (m.ROLE LIKE '%MERCH%' OR m.INSTRUCTIONS LIKE '%MERCH%')
    )
    SELECT
        COUNT(DISTINCT s.STORE_NBR)                                AS opd_stores,
        COUNT(DISTINCT m.STORE_NBR)                                AS merch_active_stores,
        ROUND(100.0 * COUNT(DISTINCT m.STORE_NBR)
              / NULLIF(COUNT(DISTINCT s.STORE_NBR), 0), 1)         AS merch_coverage_pct
    FROM opd_stores s
    LEFT JOIN merch_stores m ON s.STORE_NBR = m.STORE_NBR
""")
merch_active = int(df3["MERCH_ACTIVE_STORES"].iloc[0])
merch_pct = float(df3["MERCH_COVERAGE_PCT"].iloc[0])
results["TEST3_merch_active_gte_100"] = merch_active >= 100
print(f"  → merch_active_stores={merch_active}  {'PASS' if results['TEST3_merch_active_gte_100'] else 'FAIL'}")
print(f"  → merch_coverage_pct={merch_pct}%")

# ── TEST 4: Full 3-way join — row count and null rate sanity ─────────────────
df4 = run("TEST 4 — Full OPD × Delivery × Merch join shape (recent 4 weeks)", """
    WITH
    opd_weekly AS (
        SELECT
            STORE_NBR,
            DATE_TRUNC('WEEK', TRY_TO_DATE(DATE_SID, 'YYYYMMDD')) AS week_start,
            SUM(FTPR_NMRTR)   AS ftpr_nmrtr,
            SUM(FTPR_DNMNTR)  AS ftpr_dnmntr
        FROM CCB_DATASCIENCE_DEV.PUBLIC.WALMART_STANDARDIZED_EXTERNAL_DATA
        WHERE DATE_SID >= '20250101' AND STORE_NBR <> 9999
        GROUP BY 1, 2
    ),
    delivery_weekly AS (
        SELECT
            REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1)::INTEGER AS STORE_NBR,
            DATE_TRUNC('WEEK', DATE(GM.ROUTE_DATE))                             AS week_start,
            COUNT(*)                                                             AS delivery_stop_count
        FROM CCB_PRD.GREEN_MILE_CORE.F_STOP GM
        JOIN CCB_PRD.DM.D_CUSTOMER_V C
            ON GM.CUSTOMER_ID = C.CUSTOMER_ID
            AND C.CURRENT_IND = 'Y'
            AND C.ACCOUNT_GROUP_DESC LIKE '%WALMART%'
            AND C.BUSINESS_TYPE_DESC = 'DSD'
            AND REGEXP_SUBSTR(C.CUSTOMER_DESC, '#([0-9]+)', 1, 1, 'e', 1) IS NOT NULL
        WHERE DATE(GM.ROUTE_DATE) >= '2025-01-01'
          AND GM.ROLE = 'DC'
          AND GM.ACTUAL_DEPARTURE_DATE IS NOT NULL
        GROUP BY 1, 2
    ),
    merch_weekly AS (
        SELECT
            sc.STORE_NBR,
            DATE_TRUNC('WEEK', m.ROUTE_DATE::DATE) AS week_start,
            COUNT(*) AS merch_visit_count
        FROM CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER sc
        INNER JOIN CCB_PRD.GREEN_MILE_CORE.F_STOP m
            ON sc.CUSTOMER_SID = m.CUSTOMER_SID
        WHERE m.ROUTE_DATE >= '2025-01-01'
          AND (m.ROLE LIKE '%MERCH%' OR m.INSTRUCTIONS LIKE '%MERCH%')
        GROUP BY sc.STORE_NBR, 2
    ),
    combined AS (
        SELECT
            opd.STORE_NBR,
            opd.week_start,
            opd.ftpr_nmrtr,
            opd.ftpr_dnmntr,
            COALESCE(dw.delivery_stop_count, 0)           AS delivery_stop_count,
            CASE WHEN dw.STORE_NBR IS NOT NULL THEN 1 ELSE 0 END AS is_delivery_active_week,
            mw.merch_visit_count
        FROM opd_weekly opd
        LEFT JOIN delivery_weekly dw
            ON opd.STORE_NBR = dw.STORE_NBR AND opd.week_start = dw.week_start
        LEFT JOIN merch_weekly mw
            ON opd.STORE_NBR = mw.STORE_NBR AND opd.week_start = mw.week_start
    )
    SELECT
        COUNT(*)                                                          AS total_rows,
        COUNT(DISTINCT STORE_NBR)                                         AS distinct_stores,
        COUNT(DISTINCT week_start)                                        AS distinct_weeks,
        SUM(CASE WHEN is_delivery_active_week = 1 THEN 1 ELSE 0 END)     AS delivery_active_rows,
        ROUND(100.0 * SUM(CASE WHEN is_delivery_active_week = 0 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 1)                                   AS pct_no_delivery,
        SUM(CASE WHEN merch_visit_count IS NOT NULL THEN 1 ELSE 0 END)    AS merch_rows,
        ROUND(100.0 * SUM(CASE WHEN merch_visit_count IS NULL THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 1)                                   AS pct_no_merch,
        ROUND(SUM(ftpr_nmrtr) / NULLIF(SUM(ftpr_dnmntr), 0) * 100, 2)   AS overall_ftpr_pct
    FROM combined
""")
total_rows = int(df4["TOTAL_ROWS"].iloc[0])
no_delivery_pct = float(df4["PCT_NO_DELIVERY"].iloc[0])
results["TEST4_row_count_in_range"] = 5_000 <= total_rows <= 500_000
results["TEST4_delivery_null_lt_50pct"] = no_delivery_pct < 50.0
print(f"  → total_rows={total_rows:,}  {'PASS' if results['TEST4_row_count_in_range'] else 'FAIL'}")
print(f"  → pct_no_delivery={no_delivery_pct}%  {'PASS (< 50%)' if results['TEST4_delivery_null_lt_50pct'] else 'FAIL (>= 50%)'}")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  SUMMARY")
print('='*60)
all_pass = True
for name, passed in results.items():
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if not passed:
        all_pass = False

print()
print("OVERALL:", "ALL PASS ✓" if all_pass else "FAILURES DETECTED — see above")
conn.close()
