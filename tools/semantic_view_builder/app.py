"""Semantic View Builder — Streamlit front-end.

Workflow:
  1. User enters source tables/views (one per line)
  2. User fills in domain name, description, and primary business question
  3. App pulls Snowflake metadata (schema + sample values) via profiler.py
  4. App sends metadata to Claude via generator.py
  5. User reviews the generated YAML, edits inline, then downloads

Run locally:
    cd Users/Tyler.Chia/agentic-data-analyst
    streamlit run tools/semantic_view_builder/app.py

Environment vars required (or set in .env):
    ANTHROPIC_API_KEY
    SNOWFLAKE_MOCK=1  ← set this to skip real Snowflake during local dev
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable when running directly
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env", override=False)

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Semantic View Builder",
    page_icon="🏗️",
    layout="wide",
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _import_profiler():
    from tools.semantic_view_builder.profiler import profile_tables, profiles_to_markdown
    return profile_tables, profiles_to_markdown


def _import_generator():
    from tools.semantic_view_builder.generator import generate_semantic_yaml, validate_yaml
    return generate_semantic_yaml, validate_yaml


# ── sidebar — connection settings ────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Connection settings")

    mock_mode = st.toggle(
        "Mock mode (no Snowflake)",
        value=False,
        help="Enable to skip real Snowflake calls and use placeholder metadata.",
    )
    if mock_mode:
        import os
        os.environ["SNOWFLAKE_MOCK"] = "1"
    else:
        import os
        os.environ.pop("SNOWFLAKE_MOCK", None)

    st.markdown("---")
    default_db = st.text_input("Default database", value="CCB_DATASCIENCE_DEV")
    default_schema = st.text_input(
        "Default schema", value="WALMART_STANDARDIZED_EXTERNAL_DATA"
    )

    st.markdown("---")
    claude_model = st.selectbox(
        "Claude model",
        options=[
            "claude-sonnet-4-5",
            "claude-opus-4-5",
            "claude-haiku-4-5",
        ],
        index=0,
    )

    st.markdown("---")
    st.caption("Auth: Azure Key Vault (team pattern). ANTHROPIC_API_KEY from .env.")

# ── main UI ───────────────────────────────────────────────────────────────────
st.title("🏗️ Semantic View Builder")
st.caption(
    "Enter your source tables, answer a few questions, and get a first-pass "
    "Cortex Analyst semantic view YAML in seconds."
)

# Step 1 — Source tables
st.header("Step 1 — Source tables / views")
tables_raw = st.text_area(
    "Enter table or view references, one per line",
    placeholder=(
        "CCB_DATASCIENCE_DEV.WALMART_STANDARDIZED_EXTERNAL_DATA.OPD_WEEKLY_METRICS\n"
        "CCB_DATASCIENCE_DEV.WALMART_OPD.V_STORE_CUSTOMER\n"
        "SCHEMA.MY_VIEW"
    ),
    height=160,
)

# Step 2 — Domain info
st.header("Step 2 — Domain information")
col1, col2 = st.columns(2)

with col1:
    domain_name = st.text_input(
        "Domain name (short identifier)",
        placeholder="walmart-opd",
    )

with col2:
    output_filename = st.text_input(
        "Output filename",
        value="",
        placeholder="auto-filled from domain name",
    )
    if not output_filename and domain_name:
        output_filename = f"{domain_name.lower().replace(' ', '-')}.yaml"

domain_description = st.text_area(
    "Domain description",
    placeholder=(
        "Walmart OPD (Order Picking and Delivery) performance metrics for RCCB-served "
        "stores. Covers first-time pick rate (FTPR), nil pick rates, delivery activity, "
        "and merchandising coverage. Owned by the Walmart Sales Execution team."
    ),
    height=100,
)

business_question = st.text_area(
    "Primary business question this model must answer",
    placeholder=(
        "Which distribution centers, stores, and brands have the worst FTPR and nil-pick "
        "rates, and what trends are improving or declining over time?"
    ),
    height=80,
)

# Step 3 — Generate
st.header("Step 3 — Generate")

run_col, status_col = st.columns([2, 3])

with run_col:
    generate_btn = st.button(
        "🚀 Pull metadata & generate YAML",
        type="primary",
        disabled=not (tables_raw.strip() and domain_name.strip() and business_question.strip()),
    )

# ── generation logic ──────────────────────────────────────────────────────────
if generate_btn:
    table_refs = [t.strip() for t in tables_raw.splitlines() if t.strip()]

    with st.spinner("Connecting to Snowflake and profiling tables…"):
        try:
            profile_tables, profiles_to_markdown = _import_profiler()

            if mock_mode:
                # Generate synthetic metadata for demo/dev purposes
                from tools.semantic_view_builder.profiler import (
                    ColumnProfile,
                    TableProfile,
                )

                mock_profiles = []
                for ref in table_refs:
                    parts = ref.split(".")
                    tbl_name = parts[-1]
                    mock_profiles.append(
                        TableProfile(
                            database=default_db,
                            schema=default_schema,
                            table=tbl_name,
                            row_count=100_000,
                            columns=[
                                ColumnProfile("STORE_NBR", "NUMBER", False, 0.0, 623, ["1001", "1002", "1003"]),
                                ColumnProfile("WEEK_DT", "DATE", False, 0.0, 52, ["2026-01-04", "2026-01-11"]),
                                ColumnProfile("DC_NAME", "VARCHAR", True, 0.02, 41, ["ALSIP", "MADISON"]),
                                ColumnProfile("FTPR_NMRTR", "NUMBER", False, 0.0, 8000, ["9823", "7654"]),
                                ColumnProfile("FTPR_DNMNTR", "NUMBER", False, 0.0, 9000, ["10000", "8500"]),
                                ColumnProfile("NIL_PICK_QTY", "NUMBER", True, 0.15, 500, ["0", "1", "2"]),
                                ColumnProfile("CATEGORY", "VARCHAR", True, 0.05, 14, ["ENERGY", "SSD", "WATER"]),
                                ColumnProfile("BRAND_NAME", "VARCHAR", True, 0.05, 112, ["MONSTER", "REIGN", "NOS"]),
                            ],
                        )
                    )
                profiles = mock_profiles
                st.info("Mock mode: synthetic metadata used instead of real Snowflake.")
            else:
                profiles = profile_tables(
                    table_refs,
                    database=default_db,
                    schema=default_schema,
                )

            metadata_md = profiles_to_markdown(profiles)
            st.session_state["metadata_md"] = metadata_md
            st.success(f"Profiled {len(profiles)} table(s).")

        except Exception as exc:
            st.error(f"Metadata profiling failed: {exc}")
            st.stop()

    with st.spinner("Sending metadata to Claude — generating YAML…"):
        try:
            generate_semantic_yaml, validate_yaml = _import_generator()
            yaml_text = generate_semantic_yaml(
                domain_name=domain_name,
                domain_description=domain_description,
                business_question=business_question,
                metadata_markdown=st.session_state["metadata_md"],
                model=claude_model,
            )
            is_valid, err = validate_yaml(yaml_text)
            st.session_state["generated_yaml"] = yaml_text
            st.session_state["yaml_valid"] = is_valid
            st.session_state["yaml_err"] = err
            st.session_state["output_filename"] = output_filename or f"{domain_name}.yaml"

            if is_valid:
                st.success("YAML generated and validated successfully.")
            else:
                st.warning(f"YAML generated but has parse issues: {err}")

        except Exception as exc:
            st.error(f"Generation failed: {exc}")
            st.stop()

# ── review + edit ─────────────────────────────────────────────────────────────
if "generated_yaml" in st.session_state:
    st.header("Step 4 — Review and edit")

    with st.expander("📋 Table metadata used", expanded=False):
        st.markdown(st.session_state.get("metadata_md", ""))

    st.caption(
        "Edit the YAML below directly. "
        "LOW_CONFIDENCE comments mark fields the model was uncertain about — review those first."
    )

    edited_yaml = st.text_area(
        "Generated semantic view YAML",
        value=st.session_state["generated_yaml"],
        height=600,
        key="yaml_editor",
    )

    # Live validation on edits
    try:
        import yaml as _yaml
        _yaml.safe_load(edited_yaml)
        st.success("✅ YAML is valid")
    except Exception as _e:
        st.error(f"❌ YAML parse error: {_e}")

    st.header("Step 5 — Save / deploy")
    dl_col, deploy_col = st.columns(2)

    fname = st.session_state.get("output_filename", "semantic_model.yaml")

    with dl_col:
        st.download_button(
            label="⬇️ Download YAML",
            data=edited_yaml,
            file_name=fname,
            mime="text/yaml",
        )
        st.caption(f"Save to: `context/semantic_models/{fname}`")

    with deploy_col:
        st.info(
            "To deploy to Snowflake, run:\n\n"
            "```sql\n"
            "SELECT SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(\n"
            "  'DATABASE.SCHEMA',\n"
            "  $$ <paste YAML here> $$\n"
            ");\n"
            "```\n\n"
            "Or use `scripts/recreate_semantic_view.sql` as a template."
        )
