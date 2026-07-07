"""Generate realistic synthetic Walmart OPD data with embedded analytical patterns.

Produces internally consistent data at UPC × Store × Date grain with:
- Fixed UPC → Category/Size mappings (no random mismatches)
- Correlated metrics: FTPR and nil-picks inversely related
- Numerator ≤ denominator for all rate columns
- Populated KO/WM attribution flags (binary 0/1)
- Embedded patterns for the agents to discover:
    1. TEMPORAL: FTPR declining over time at specific stores (Store cluster A)
    2. CATEGORY: Energy drinks have higher nil-pick rates than other categories
    3. STORE CLUSTER: A subset of stores (cluster B) have consistently high FTPR
    4. KO vs WM: KO-attributed nil-picks spike in March (supply chain disruption)
    5. SIZE: Single-serve packages have lower nil-pick rates than multi-packs
    6. SUBSTITUTION: High pre-sub stores mask true nil-pick severity
    7. PHANTOM INVENTORY: Stores with high possible_PI flag have worse FTPR
    8. BAD STORE: Store 9999 has chronically terrible FTPR (~65-72%) across all products

Usage:
    python -m data.generators.generate_walmart_opd [--rows 50000] [--seed 42]

Output:
    data/sample/synthetic_walmart.csv
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── Product catalog: fixed UPC → (Category, Size) mapping ──────────────────
PRODUCTS = [
    # (UPC, Category, Size)
    # SSD
    ("49000042566", "SSD", "12oz 12pk"),
    ("49000028911", "SSD", "20oz Single"),
    ("49000006346", "SSD", "2 Liter"),
    ("49000045291", "SSD", "7.5oz 15pk Mini"),
    ("49000012842", "SSD", "16.9oz 6pk"),
    # Energy
    ("70847811169", "ENERGY", "16oz Single"),
    ("70847000073", "ENERGY", "12oz Single"),
    ("70847811442", "ENERGY", "16oz 4pk"),
    ("70847032850", "ENERGY", "15.5oz Single"),
    ("70847811237", "ENERGY", "12oz 12pk"),
    # Water
    ("49000031249", "Water", "16.9oz 24pk"),
    ("49000031256", "Water", "500ml 6pk"),
    ("49000057980", "Water", "700ml Single"),
    ("49000045321", "Water", "1 Liter 6pk"),
    # Enh Water
    ("58946936512", "Enh Water", "20oz Single"),
    ("58946936536", "Enh Water", "20oz 6pk"),
    ("58946936543", "Enh Water", "12oz 12pk"),
    # Isotonics
    ("49000050104", "Isotonics", "28oz Single"),
    ("49000050111", "Isotonics", "20oz 8pk"),
    ("49000050128", "Isotonics", "12oz 12pk"),
    # Tea
    ("49000070019", "Tea", "18.5oz Single"),
    ("49000070026", "Tea", "16.9oz 6pk"),
    # RTD Coffee
    ("49000080015", "RTD Coffee", "11oz Single"),
    ("49000080022", "RTD Coffee", "11oz 4pk"),
    # Sparkling Water
    ("49000090018", "Sparkling Wtr", "12oz 8pk"),
    ("49000090025", "Sparkling Wtr", "12oz Single"),
]

# Store clusters with different performance profiles
STORES_CLUSTER_A = [442, 554, 732, 947, 1205, 1301, 1489, 1622, 1780, 1903,
                    2015, 2126, 2237, 2348, 2459]  # Declining FTPR over time (15 stores)
STORES_CLUSTER_B = [856, 1388, 2104, 2567, 3012, 3145, 3287, 3401, 3590, 3712,
                    3823, 3934, 4045, 4156, 4267]  # Consistently high FTPR (15 stores)
STORES_CLUSTER_C = [  # Average performers (bulk of stores — ~120)
    613, 942, 1005, 1744, 2389, 3528, 4746, 5433,
    501, 602, 715, 823, 934, 1048, 1156, 1267,
    1378, 1490, 1601, 1713, 1824, 1935, 2046, 2157,
    2268, 2379, 2491, 2602, 2713, 2824, 2935, 3046,
    3157, 3268, 3379, 3491, 3602, 3713, 3824, 3935,
    4046, 4157, 4268, 4379, 4491, 4602, 4713, 4824,
    4935, 5046, 5157, 5268, 5379, 5491, 5602, 5713,
    5824, 5935, 6046, 6157, 6268, 6379, 6491, 6602,
    6713, 6824, 6935, 7046, 7157, 7268, 7379, 7491,
    7602, 7713, 7824, 7935, 8046, 8157, 8268, 8379,
    8491, 8602, 8713, 8824, 8935, 9046, 9157, 9268,
    9379, 9491, 9602, 9713, 9824, 9935,
]
STORES_BAD = [9999]  # Chronically terrible performer

ALL_STORES = STORES_CLUSTER_A + STORES_CLUSTER_B + STORES_CLUSTER_C + STORES_BAD

# Date range: weekly dates for a full year (52 weeks)
DATES = pd.date_range("2025-07-07", "2026-06-29", freq="W-MON")


def _unique_key(upc: str, store: int, date_sid: int) -> int:
    """Deterministic surrogate key from natural grain."""
    h = hashlib.sha256(f"{upc}|{store}|{date_sid}".encode()).hexdigest()
    return int(h[:16], 16)


def generate(n_rows: int = 100000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # Build a structured panel: each store carries a subset of products each week
    # 26 products × 125 stores × 52 weeks = 169,000 max combos
    import itertools
    all_combos = list(itertools.product(range(len(PRODUCTS)), range(len(ALL_STORES)), range(len(DATES))))
    rng.shuffle(all_combos)

    # Select enough combos to hit target
    target = min(n_rows, len(all_combos))
    selected = all_combos[:target]

    rows = []
    for prod_idx, store_idx, date_idx in selected:
        upc, category, size = PRODUCTS[prod_idx]
        store = ALL_STORES[store_idx]
        date = DATES[date_idx]
        date_sid = int(date.strftime("%Y%m%d"))

        # ── Base demand (denominator for FTPR) ──
        # Multi-packs have higher order volume
        is_multipack = any(x in size for x in ["pk", "Liter", "24pk"])
        base_demand = rng.integers(5, 60) if is_multipack else rng.integers(1, 20)

        # ── FTPR rate — base ~94%, modified by patterns ──
        ftpr_rate = 0.94

        # Pattern 1: Cluster A stores decline over time (starts ~week 26, accelerates)
        if store in STORES_CLUSTER_A:
            weeks_in = (date - DATES[0]).days / 7
            if weeks_in > 26:  # Decline starts mid-year
                ftpr_rate -= 0.004 * (weeks_in - 26)
            ftpr_rate = max(ftpr_rate, 0.78)  # floor

        # Pattern 2: Cluster B stores are high performers
        if store in STORES_CLUSTER_B:
            ftpr_rate = min(ftpr_rate + 0.04, 0.995)

        # Pattern 3: Energy drinks have worse FTPR
        if category == "ENERGY":
            ftpr_rate -= 0.06

        # Pattern 5: Single-serve has better FTPR (easier to shelf)
        if "Single" in size:
            ftpr_rate += 0.02

        # Pattern 7: Some stores have phantom inventory issues
        has_phantom_issue = store in [613, 942, 4746]
        if has_phantom_issue:
            ftpr_rate -= 0.04

        # Pattern 8: Store 9999 is a chronically terrible performer
        if store in STORES_BAD:
            ftpr_rate -= 0.25  # Drops to ~65-72% range

        # Add noise
        ftpr_rate += rng.normal(0, 0.02)
        ftpr_rate = np.clip(ftpr_rate, 0.55, 0.995)

        # Compute FTPR columns
        ftpr_dnmntr = float(base_demand)
        ftpr_nmrtr = float(max(0, round(ftpr_dnmntr * ftpr_rate)))
        ftpr_nmrtr = min(ftpr_nmrtr, ftpr_dnmntr)  # can't exceed denominator
        ftpr_qty = ftpr_nmrtr

        # ── Nil-picks (inversely correlated with FTPR) ──
        nil_pick_qty = float(max(0, round(ftpr_dnmntr - ftpr_nmrtr)))
        nil_pick_count = float(max(0, round(nil_pick_qty * rng.uniform(0.3, 1.0))))

        # ── KO vs WM attribution ──
        # Pattern 4: KO-attributed nil-picks spike in March
        is_march = date.month == 3
        if nil_pick_qty > 0:
            if is_march:
                ko_prob = 0.7  # Supply chain disruption in March
            else:
                ko_prob = 0.3
            ko_flag = 1 if rng.random() < ko_prob else 0
            wm_flag = 1 - ko_flag  # One or the other
        else:
            ko_flag = 0
            wm_flag = 0

        # Pattern 7: Phantom inventory flag
        if has_phantom_issue and nil_pick_qty > 0:
            possible_pi = 1 if rng.random() < 0.6 else 0
        else:
            possible_pi = 1 if rng.random() < 0.05 else 0

        # ── Substitutions ──
        # Pattern 6: High pre-sub stores mask nil-pick severity
        high_presub_stores = [1388, 2104, 3012]
        if store in high_presub_stores and nil_pick_qty > 0:
            presub_qty = float(round(nil_pick_qty * rng.uniform(0.4, 0.7)))
        else:
            presub_qty = float(round(nil_pick_qty * rng.uniform(0.05, 0.2)))

        presub_rate_dnmntr = ftpr_dnmntr
        presub_rate_nmrtr = presub_qty

        # Post-sub: picker substitutes remaining nil-picks not covered by pre-sub
        remaining = nil_pick_qty - presub_qty
        postsub_qty = float(max(0, round(remaining * rng.uniform(0.2, 0.5))))
        postsub_rate_dnmntr = max(1.0, remaining)
        postsub_rate_nmrtr = min(postsub_qty, postsub_rate_dnmntr)

        # ── Scheduled vs unscheduled nil-picks ──
        if nil_pick_qty > 0:
            schdl_frac = rng.uniform(0.6, 0.9)
            schdl_nil_pick_qty = float(round(nil_pick_qty * schdl_frac))
            unschdl_nil_pick_qty = float(max(0, nil_pick_qty - schdl_nil_pick_qty))
        else:
            schdl_nil_pick_qty = 0.0
            unschdl_nil_pick_qty = 0.0

        schdl_nil_pick_rate_dnmntr = ftpr_dnmntr
        schdl_nil_pick_rate_nmrtr = schdl_nil_pick_qty
        unschdl_nil_pick_rate_dnmtr = ftpr_dnmntr
        unschdl_nil_pick_rate_nmtr = unschdl_nil_pick_qty

        rows.append({
            "UNIQUE_KEY": _unique_key(upc, store, date_sid),
            "DATE_SID": date_sid,
            "STORE_NBR": store,
            "CATEGORY": category,
            "SIZE": size,
            "ORIGINAL_UPC": upc,
            "FTPR_QTY": ftpr_qty,
            "FTPR_NMRTR": ftpr_nmrtr,
            "FTPR_DNMNTR": ftpr_dnmntr,
            "NIL_PICK_QTY": nil_pick_qty,
            "NIL_PICK_COUNT": nil_pick_count,
            "TY_NIL_PICK_KO_FLAG": ko_flag,
            "TY_NIL_PICK_WM_FLAG": wm_flag,
            "TY_NIL_PICK_POSSIBLE_PI": possible_pi,
            "PRESUB_QTY": presub_qty,
            "PRESUB_RATE_NMRTR": presub_rate_nmrtr,
            "PRESUB_RATE_DNMNTR": presub_rate_dnmntr,
            "POSTSUB_RATE_NMRTR": postsub_rate_nmrtr,
            "POSTSUB_RATE_DNMNTR": postsub_rate_dnmntr,
            "SCHDL_NIL_PICK_QTY": schdl_nil_pick_qty,
            "SCHDL_NIL_PICK_RATE_NMRTR": schdl_nil_pick_rate_nmrtr,
            "SCHDL_NIL_PICK_RATE_DNMNTR": schdl_nil_pick_rate_dnmntr,
            "UNSCHDL_NIL_PICK_QTY": unschdl_nil_pick_qty,
            "UNSCHDL_NIL_PICK_RATE_NMTR": unschdl_nil_pick_rate_nmtr,
            "UNSCHDL_NIL_PICK_RATE_DNMTR": unschdl_nil_pick_rate_dnmtr,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on natural grain (keep first)
    df = df.drop_duplicates(subset=["ORIGINAL_UPC", "STORE_NBR", "DATE_SID"], keep="first")

    # Sort for readability
    df = df.sort_values(["DATE_SID", "STORE_NBR", "ORIGINAL_UPC"]).reset_index(drop=True)

    return df


def validate(df: pd.DataFrame) -> None:
    """Sanity checks on the generated data."""
    assert df["UNIQUE_KEY"].nunique() == len(df), "UNIQUE_KEY not unique"
    assert (df["FTPR_NMRTR"] <= df["FTPR_DNMNTR"]).all(), "FTPR numerator > denominator"
    assert (df["PRESUB_RATE_NMRTR"] <= df["PRESUB_RATE_DNMNTR"]).all(), "PRESUB numerator > denominator"
    assert (df["POSTSUB_RATE_NMRTR"] <= df["POSTSUB_RATE_DNMNTR"]).all(), "POSTSUB numerator > denominator"
    assert (df["SCHDL_NIL_PICK_RATE_NMRTR"] <= df["SCHDL_NIL_PICK_RATE_DNMNTR"]).all(), "SCHDL numerator > denominator"
    assert df["TY_NIL_PICK_KO_FLAG"].isin([0, 1]).all(), "KO flag not binary"
    assert df["TY_NIL_PICK_WM_FLAG"].isin([0, 1]).all(), "WM flag not binary"
    assert df.isnull().sum().sum() == 0, "Unexpected nulls"

    # Check patterns exist
    cluster_a = df[df["STORE_NBR"].isin(STORES_CLUSTER_A)]
    early = cluster_a[cluster_a["DATE_SID"] < 20260101]  # Pre-decline period
    late = cluster_a[cluster_a["DATE_SID"] > 20260501]   # Late decline period
    early_ftpr = (early["FTPR_NMRTR"] / early["FTPR_DNMNTR"]).mean()
    late_ftpr = (late["FTPR_NMRTR"] / late["FTPR_DNMNTR"]).mean()
    assert late_ftpr < early_ftpr - 0.02, f"Cluster A FTPR decline not visible: {early_ftpr:.3f} → {late_ftpr:.3f}"

    energy = df[df["CATEGORY"] == "ENERGY"]
    non_energy = df[df["CATEGORY"] != "ENERGY"]
    energy_nil_rate = energy["NIL_PICK_QTY"].sum() / energy["FTPR_DNMNTR"].sum()
    non_energy_nil_rate = non_energy["NIL_PICK_QTY"].sum() / non_energy["FTPR_DNMNTR"].sum()
    assert energy_nil_rate > non_energy_nil_rate, "Energy nil-pick rate not higher"

    march = df[df["DATE_SID"].between(20260301, 20260331)]
    non_march = df[~df["DATE_SID"].between(20260301, 20260331)]
    march_ko = march.loc[march["NIL_PICK_QTY"] > 0, "TY_NIL_PICK_KO_FLAG"].mean()
    non_march_ko = non_march.loc[non_march["NIL_PICK_QTY"] > 0, "TY_NIL_PICK_KO_FLAG"].mean()
    assert march_ko > non_march_ko + 0.1, f"March KO spike not visible: {march_ko:.3f} vs {non_march_ko:.3f}"

    # Check bad store
    bad = df[df["STORE_NBR"].isin(STORES_BAD)]
    rest = df[~df["STORE_NBR"].isin(STORES_BAD)]
    bad_ftpr = (bad["FTPR_NMRTR"].sum() / bad["FTPR_DNMNTR"].sum())
    rest_ftpr = (rest["FTPR_NMRTR"].sum() / rest["FTPR_DNMNTR"].sum())
    assert bad_ftpr < rest_ftpr - 0.15, f"Bad store not bad enough: {bad_ftpr:.3f} vs {rest_ftpr:.3f}"

    print(f"  ✓ All validations passed")
    print(f"  ✓ Cluster A FTPR decline: {early_ftpr:.3f} → {late_ftpr:.3f}")
    print(f"  ✓ Energy nil-pick rate: {energy_nil_rate:.3f} vs others: {non_energy_nil_rate:.3f}")
    print(f"  ✓ March KO attribution: {march_ko:.3f} vs other months: {non_march_ko:.3f}")
    print(f"  ✓ Bad store FTPR: {bad_ftpr:.3f} vs rest: {rest_ftpr:.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic Walmart OPD data")
    parser.add_argument("--rows", type=int, default=100000, help="Approximate number of rows")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print(f"Generating ~{args.rows} rows (seed={args.seed})...")
    df = generate(n_rows=args.rows, seed=args.seed)
    print(f"Generated {len(df)} rows after dedup")

    print("Validating...")
    validate(df)

    out_path = REPO_ROOT / "data" / "sample" / "synthetic_walmart.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved to {out_path}")
    print(f"\nEmbedded patterns:")
    print(f"  1. TEMPORAL: Stores {STORES_CLUSTER_A} — FTPR declining ~0.5%/week Jan→Apr")
    print(f"  2. CATEGORY: Energy drinks have ~6pp higher nil-pick rate")
    print(f"  3. STORE: Stores {STORES_CLUSTER_B} — consistently high FTPR (+4pp)")
    print(f"  4. KO SPIKE: March has ~70% KO-attributed nil-picks vs ~30% other months")
    print(f"  5. SIZE: Single-serve items have ~2pp better FTPR")
    print(f"  6. SUBSTITUTION: Stores {[1388, 2104, 3012]} mask nil-picks with high pre-sub")
    print(f"  7. PHANTOM: Stores {[613, 942, 4746]} have phantom inventory issues")
    print(f"  8. BAD STORE: Store 9999 — chronically terrible FTPR (~65-72%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
