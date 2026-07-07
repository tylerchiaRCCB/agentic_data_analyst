"""Semantic View Builder — Streamlit in Snowflake (SiS) version.

Single-file app. Deploy to Snowsight:
  1. Open Snowsight → Streamlit → + Streamlit App
  2. Paste this file, or upload to a stage and reference it.
  3. No external API keys — auth and LLM are provided by Snowflake.

LLM: snowflake.cortex.Complete() — runs entirely inside Snowflake.
Data: session.sql() — uses the active Snowpark session.

Workflow:
  1. User enters source table/view names
  2. App pulls schema + sample values from Snowflake
  3. App sends metadata to Cortex LLM
  4. User reviews, edits, and downloads the generated YAML
"""

from __future__ import annotations

import json

import streamlit as st
from snowflake.snowpark.context import get_active_session

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Semantic View Builder",
    page_icon="🏗️",
    layout="wide",
)

# ── active Snowpark session ───────────────────────────────────────────────────
session = get_active_session()

# ── constants ─────────────────────────────────────────────────────────────────
_SAMPLE_ROWS = 5000
_MAX_SAMPLE_VALUES = 10

# Approximate context window per model (tokens). Used for pre-flight warning only.
# Rough estimate: 1 token ≈ 4 chars.
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-6":  1_000_000,
    "claude-opus-4-7":    1_000_000,
    "claude-opus-4-6":    1_000_000,
    "claude-opus-4-5":      200_000,
    "claude-sonnet-4-5":    200_000,
    "claude-haiku-4-5":     200_000,
    "llama4-maverick":      128_000,
    "llama4-scout":         128_000,
    "llama3.1-405b":        128_000,
    "llama3.3-70b":         128_000,
    "llama3.1-70b":         128_000,
    "llama3.1-8b":          128_000,
    "mistral-large2":       128_000,
    "openai-gpt-4.1":       128_000,
}
_DEFAULT_CONTEXT_WINDOW = 128_000

_SYSTEM_PROMPT = """You are an expert Snowflake data modeler and semantic layer architect.
Your job is to generate first-pass Snowflake Cortex Analyst semantic model YAML files
from raw table metadata.

Rules:
1. Follow the standard Snowflake Cortex Analyst semantic model spec exactly.
2. Write business-friendly names and descriptions in plain English.
3. Classify each column correctly: dimension, time_dimension, or measure.
4. For measures that are rates or ratios, always write the formula as SUM(numerator)/SUM(denominator).
5. Add realistic synonyms (2-4 per field) that a business user would say out loud.
6. Add sample_values for dimension columns only.
7. Flag low-confidence fields with a comment starting: # LOW_CONFIDENCE:
8. Do NOT invent top-level sections outside the Cortex Analyst semantic model schema.
9. Output ONLY valid YAML — no explanation, no markdown fences, no extra text.
10. Do NOT include YAML document markers: never write --- or ... anywhere in the output.
    Start the output directly with 'name:' on the very first line.
11. If multiple tables are provided, infer likely join relationships between them.
    - Look for columns with matching names or semantics (e.g. STORE_NBR, CUSTOMER_ID, PRODUCT_ID).
    - Add a relationships: section listing each inferred join.
    - For each relationship include: name, left_table, left_column, right_table, right_column,
      join_type (many_to_one / one_to_many / one_to_one), and a confidence comment
      (# HIGH / # MEDIUM / # LOW_CONFIDENCE) based on how certain the join is.
    - Flag ambiguous or risky joins (e.g. many-to-many) with # LOW_CONFIDENCE.

The YAML structure must follow this shape:
name: <domain_name>
description: |
  <description>
tables:
  - name: <table_name>
    description: <description>
    base_table:
      database: <database>
      schema: <schema>
      table: <table>
    dimensions:
      - name: <col>
        description: <business meaning>
        expr: <col>
        data_type: <type>
        synonyms: [<synonym1>, <synonym2>]
        sample_values: [<val1>, <val2>]
    time_dimensions:
      - name: <col>
        description: <business meaning>
        expr: <col>
        data_type: DATE
        synonyms: [<synonym>]
    measures:
      - name: <metric>
        description: <business meaning>
        expr: <aggregation SQL>
        data_type: NUMBER
        default_aggregation: avg
        synonyms: [<synonym>]
# Include relationships only when multiple tables are provided:
relationships:
  - name: <relationship_name>  # e.g. orders_to_customers
    left_table: <table_name>
    left_column: <join_key>
    right_table: <table_name>
    right_column: <join_key>
    join_type: many_to_one  # many_to_one | one_to_many | one_to_one
    # HIGH / MEDIUM / LOW_CONFIDENCE based on name match and cardinality
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def profile_table(database: str, schema: str, table: str) -> dict:
    """Pull schema + sample data for one table using the active session."""
    qualified = f'"{database}"."{schema}"."{table}"'

    # Row count
    row_count = session.sql(f"SELECT COUNT(*) AS N FROM {qualified}").collect()[0]["N"]

    # Column schema
    col_rows = session.sql(f"""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM "{database}".INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}'
          AND TABLE_NAME   = '{table}'
        ORDER BY ORDINAL_POSITION
    """).collect()

    # Random sample rows (bounded) for better profile coverage.
    sample_df = session.sql(
        f"SELECT * FROM {qualified} ORDER BY RANDOM() LIMIT {_SAMPLE_ROWS}"
    ).to_pandas()

    columns = []
    for row in col_rows:
        col = row["COLUMN_NAME"]
        dtype = row["DATA_TYPE"]
        nullable = row["IS_NULLABLE"] != "NO"

        null_rate = 0.0
        sample_values = []
        distinct_count = None

        if col in sample_df.columns:
            series = sample_df[col]
            null_rate = round(float(series.isna().mean()), 4)
            non_null = series.dropna()
            unique_vals = non_null.unique().tolist()
            distinct_count = len(unique_vals)
            sample_values = [str(v) for v in unique_vals[:_MAX_SAMPLE_VALUES]]

        columns.append({
            "name": col,
            "data_type": dtype,
            "nullable": nullable,
            "null_rate": null_rate,
            "distinct_count": distinct_count,
            "sample_values": sample_values,
        })

    return {
        "database": database,
        "schema": schema,
        "table": table,
        "row_count": row_count,
        "columns": columns,
    }


def parse_table_ref(ref: str, default_db: str, default_schema: str) -> tuple[str, str, str]:
    parts = [p.strip().upper() for p in ref.split(".")]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return default_db.upper(), parts[0], parts[1]
    return default_db.upper(), default_schema.upper(), parts[0]


def profiles_to_markdown(profiles: list[dict]) -> str:
    lines: list[str] = []
    for p in profiles:
        lines.append(f"## Table: {p['database']}.{p['schema']}.{p['table']}")
        lines.append(f"- Row count: {p['row_count']:,}")
        lines.append("")
        lines.append("| Column | Type | Nullable | Null% | Distinct | Sample values | User definition |")
        lines.append("|--------|------|----------|-------|----------|---------------|-----------------|")
        for c in p["columns"]:
            null_pct = f"{c['null_rate'] * 100:.1f}%"
            distinct = str(c["distinct_count"]) if c["distinct_count"] is not None else "?"
            samples = ", ".join(c["sample_values"][:5]) if c["sample_values"] else "—"
            user_def = c.get("user_description", "—")
            lines.append(
                f"| {c['name']} | {c['data_type']} | {'Y' if c['nullable'] else 'N'} "
                f"| {null_pct} | {distinct} | `{samples}` | {user_def} |"
            )
        lines.append("")
    return "\n".join(lines)


def _parse_derived_metrics_text(text: str) -> list[dict]:
    """Parse derived metric lines.

    Expected line format:
      METRIC_NAME = SQL_EXPRESSION | optional description
    """
    metrics: list[dict] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        name = left.strip()
        expr_desc = right.strip()
        desc = ""
        expr = expr_desc
        if "|" in expr_desc:
            expr, desc = [p.strip() for p in expr_desc.split("|", 1)]
        if name and expr:
            metrics.append({"name": name, "expr": expr, "description": desc})
    return metrics


def derived_metrics_to_markdown(derived_metrics: dict[str, list[dict]]) -> str:
    """Render user-defined derived metrics into markdown for prompt context."""
    lines: list[str] = []
    if not derived_metrics:
        return ""

    lines.append("## User-defined derived metrics (highest priority)")
    for table_key, metrics in derived_metrics.items():
        if not metrics:
            continue
        lines.append(f"### Table: {table_key}")
        for m in metrics:
            desc = m.get("description", "").strip()
            if desc:
                lines.append(f"- {m['name']} = {m['expr']} | {desc}")
            else:
                lines.append(f"- {m['name']} = {m['expr']}")
        lines.append("")
    return "\n".join(lines).strip()


def filter_rules_to_markdown(filter_rules: dict[str, str]) -> str:
    """Render user-provided row-level filters into markdown for prompt context."""
    lines: list[str] = []
    if not filter_rules:
        return ""

    lines.append("## User-defined row-level filters (mandatory constraints)")
    for table_key, rule in filter_rules.items():
        text = (rule or "").strip()
        if not text:
            continue
        lines.append(f"- {table_key}: {text}")
    return "\n".join(lines).strip()


def generate_yaml(
    domain_name: str,
    domain_description: str,
    business_question: str,
    metadata_markdown: str,
    model: str,
    derived_metrics_markdown: str = "",
    filter_rules_markdown: str = "",
) -> tuple[str, str, str | None]:
    """Returns (cleaned_yaml, raw_llm_output, parse_error_or_None)."""
    import re
    import yaml

    unsupported_top_level_keys = {
        "guardrail_metric_pairings",
        "thresholds",
        "known_data_quirks",
    }

    prompt = f"""{_SYSTEM_PROMPT}

Using the metadata below, generate a complete Snowflake Cortex Analyst semantic model YAML
for domain: {domain_name!r}

Business context / domain description:
{domain_description}

Primary business question this model must answer:
{business_question}

--- TABLE METADATA ---
{metadata_markdown}

--- USER-DERIVED METRICS (IF PROVIDED) ---
{derived_metrics_markdown or "None provided."}

If user-derived metrics are provided, include them as measures using the exact metric names
and SQL expressions unless there is a clear syntax issue.

--- USER-DEFINED ROW-LEVEL FILTERS (IF PROVIDED) ---
{filter_rules_markdown or "None provided."}

If row-level filters are provided, treat them as mandatory scope constraints.
Prefer implementing those constraints directly in metric expressions (for example via CASE WHEN),
and make the filtering assumptions explicit in field descriptions.

Generate the full YAML now. Output only YAML, nothing else.
"""
    row = session.sql(
        "SELECT AI_COMPLETE(?, ?, {'max_tokens': 8192})",
        params=[model, prompt],
    ).collect()[0][0]

    raw = (row or "").strip()

    result = raw
    # AI_COMPLETE sometimes returns a JSON-encoded string — the entire YAML
    # is wrapped in outer double quotes with \n and \" as escape sequences.
    # json.loads cleanly decodes this in one step (removes outer quotes,
    # unescapes \n → newlines, \" → ").
    if result.startswith('"'):
        try:
            import json as _json
            decoded = _json.loads(result)
            if isinstance(decoded, str):
                result = decoded
        except (ValueError, Exception):
            pass  # Not JSON-encoded; fall through to manual unescaping below
    # Fallback: manually unescape \n sequences if not handled above
    if "\\n" in result and "\n" not in result:
        result = result.replace("\\n", "\n").replace("\\t", "\t")
    # Fix any remaining JSON-style escaped quotes
    if '\\"' in result:
        result = result.replace('\\"', '"')
    # Strip markdown fences
    if result.startswith("```"):
        result = "\n".join(
            l for l in result.splitlines() if not l.strip().startswith("```")
        ).strip()
    # Normalise line endings (handle \r\n or bare \r from some LLM outputs)
    result = result.replace('\r\n', '\n').replace('\r', '\n')
    # Strip document separator lines (--- and ...) using regex so trailing
    # whitespace / carriage returns are handled too.
    result = re.sub(r'^[ \t\r]*---[ \t\r]*$', '', result, flags=re.MULTILINE)
    result = re.sub(r'^[ \t\r]*\.\.\.[ \t\r]*$', '', result, flags=re.MULTILINE)
    result = result.strip()

    # Round-trip through YAML to normalise structure.
    # width=float('inf') prevents reflowing long strings.
    parse_error: str | None = None

    class _NoWrapDumper(yaml.SafeDumper):
        def ignore_aliases(self, data: object) -> bool:
            return True

    def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
        # Use block literal (|) for multi-line strings so descriptions stay readable.
        # Strip trailing whitespace/newlines that folded scalars accumulate.
        if "\n" in data:
            data = data.strip()
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    _NoWrapDumper.add_representer(str, _str_representer)

    try:
        parsed = yaml.safe_load(result)
        if isinstance(parsed, dict):
            for key in unsupported_top_level_keys:
                parsed.pop(key, None)
        if parsed is not None:
            result = yaml.dump(
                parsed,
                Dumper=_NoWrapDumper,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                indent=2,
                width=float("inf"),
            ).strip()
    except yaml.YAMLError as exc:
        # Extract the problem line number from the error and show context
        problem_line: int | None = None
        try:
            if hasattr(exc, 'problem_mark') and exc.problem_mark is not None:
                problem_line = exc.problem_mark.line  # 0-indexed
        except Exception:
            pass
        if problem_line is not None:
            lines = result.splitlines()
            start = max(0, problem_line - 15)
            end = min(len(lines), problem_line + 5)
            context = "\n".join(
                f"{'>>>' if i == problem_line else '   '} {i+1:3d}: {repr(lines[i])}"
                for i in range(start, end)
            )
            parse_error = f"{exc}\n\nLines around problem:\n{context}"
        else:
            parse_error = str(exc)

    return result, raw, parse_error


def _filter_profiles(profiles: list[dict], column_selections: dict[str, list[str]]) -> list[dict]:
    """Return a deep copy of profiles with columns filtered to only selected ones."""
    import copy
    filtered = copy.deepcopy(profiles)
    for p in filtered:
        key = f"{p['database']}.{p['schema']}.{p['table']}"
        selected = column_selections.get(key)
        if selected is not None:
            p["columns"] = [c for c in p["columns"] if c["name"] in selected]
    return filtered


def _apply_user_definitions(
    profiles: list[dict],
    user_definitions: dict[str, dict[str, str]],
) -> list[dict]:
    """Inject user-provided descriptions into column profiles.

    user_definitions: {"DB.SCHEMA.TABLE": {"COL_NAME": "user description", ...}}
    Stored as a 'user_description' key on each column dict.
    """
    for p in profiles:
        key = f"{p['database']}.{p['schema']}.{p['table']}"
        defs = user_definitions.get(key, {})
        for c in p["columns"]:
            if c["name"] in defs and defs[c["name"]].strip():
                c["user_description"] = defs[c["name"]].strip()
    return profiles


def validate_yaml(text: str) -> tuple[bool, str]:
    try:
        import yaml
        # safe_load_all tolerates multiple documents; we just need at least one valid one.
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
        if not docs:
            return False, "YAML parsed but produced no content."
        return True, ""
    except Exception as e:
        return False, str(e)


# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    # Get current database/schema from session context
    try:
        ctx = session.sql("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()").collect()[0]
        session_db = ctx[0] or "CCB_DATASCIENCE_DEV"
        session_schema = ctx[1] or "PUBLIC"
    except Exception:
        session_db = "CCB_DATASCIENCE_DEV"
        session_schema = "PUBLIC"

    default_db = st.text_input("Default database", value=session_db)
    default_schema = st.text_input("Default schema", value=session_schema)

    st.markdown("---")
    model = st.selectbox(
        "Cortex LLM model",
        options=[
            # ── Best quality (large context, high reasoning) ──────────────
            "claude-sonnet-4-6",      # 1M context, 64K output — best overall
            "claude-opus-4-7",        # 1M context, 128K output — most capable
            "claude-opus-4-5",        # 200K context, 64K output
            "claude-sonnet-4-5",      # 200K context, 64K output
            "claude-haiku-4-5",       # 200K context — fast + cheap
            # ── Open source ───────────────────────────────────────────────
            "llama4-maverick",        # 128K context — strong open source
            "llama4-scout",           # 128K context — fast open source
            "llama3.1-405b",          # 128K context — large open source
            "llama3.3-70b",           # 128K context — cost-efficient
            "llama3.1-70b",           # 128K context
            "llama3.1-8b",            # 128K context — fastest/cheapest
            # ── Other providers ───────────────────────────────────────────
            "mistral-large2",         # 128K context — good for structured output
            "openai-gpt-4.1",         # 128K context (Azure East US 2 only)
        ],
        index=0,
        help=(
            "All models run natively inside Snowflake via AI_COMPLETE — no external API key needed. "
            "claude-sonnet-4-6 is recommended for YAML generation (large context + strong structured output)."
        ),
    )
    st.caption(f"Connected as: `{session.get_current_user()}`")
    st.caption(f"Role: `{session.get_current_role()}`")

# ── main ──────────────────────────────────────────────────────────────────────
st.title("🏗️ Semantic View Builder")
st.caption(
    "Enter your source tables, answer a few questions, and get a first-pass "
    "Cortex Analyst semantic view YAML — powered by Snowflake Cortex LLM."
)

# Step 1
st.header("Step 1 — Source tables / views")
tables_raw = st.text_area(
    "Enter table or view references, one per line",
    placeholder=(
        "CCB_DATASCIENCE_DEV.WALMART_STANDARDIZED_EXTERNAL_DATA.OPD_WEEKLY_METRICS\n"
        "SCHEMA.MY_VIEW\n"
        "JUST_TABLE_NAME"
    ),
    height=140,
)

# Step 2
st.header("Step 2 — Domain information")
col1, col2 = st.columns(2)
with col1:
    domain_name = st.text_input("Domain name", placeholder="walmart-opd")
with col2:
    output_filename = st.text_input(
        "Output filename",
        value=f"{domain_name.lower().replace(' ', '-')}.yaml" if domain_name else "",
        placeholder="auto-filled from domain name",
    )

domain_description = st.text_area(
    "Domain description",
    placeholder=(
        "Walmart OPD performance metrics for RCCB-served stores. "
        "Covers FTPR, nil pick rates, delivery activity, and merchandising coverage."
    ),
    height=90,
)

business_question = st.text_area(
    "Primary business question this model must answer",
    placeholder=(
        "Which DCs, stores, and brands have the worst FTPR and nil-pick rates, "
        "and what trends are improving or declining over time?"
    ),
    height=70,
)

# Step 3
st.header("Step 3 — Generate")

ready = bool(tables_raw.strip() and domain_name.strip() and business_question.strip())
profile_btn = st.button(
    "🔍 Profile tables",
    type="secondary",
    disabled=not ready,
)

if profile_btn:
    table_refs = [t.strip() for t in tables_raw.splitlines() if t.strip()]
    profiles: list[dict] = []

    with st.spinner("Pulling metadata from Snowflake…"):
        errors = []
        for ref in table_refs:
            db, sch, tbl = parse_table_ref(ref, default_db, default_schema)
            qualified = f"{db}.{sch}.{tbl}"
            try:
                p = profile_table(db, sch, tbl)
                profiles.append(p)
                st.toast(f"✅ Profiled {qualified}", icon="✅")
            except Exception as exc:
                err_str = str(exc)
                if "does not exist" in err_str or "not authorized" in err_str or "Object" in err_str:
                    friendly = (
                        f"**{qualified}** — table not found or you don't have access. "
                        "Check the name, schema, and your role permissions."
                    )
                elif "INFORMATION_SCHEMA" in err_str:
                    friendly = (
                        f"**{qualified}** — could not read column metadata. "
                        "Ensure your role has USAGE on the database and schema."
                    )
                else:
                    friendly = f"**{qualified}** — {err_str}"
                errors.append(friendly)

        for e in errors:
            st.warning(f"⚠️ Skipped: {e}", icon="⚠️")

        if not profiles:
            st.error(
                "No tables could be profiled. "
                "Check that the table names are correct and your role has SELECT access.",
                icon="🚫",
            )
            st.stop()

        st.session_state["profiles"] = profiles
        st.session_state.pop("column_selections", None)  # reset selections on re-profile
        st.success(f"Profiled {len(profiles)} table(s). Select columns below, then generate.")

# ── Step 3b — column selector (shown after profiling) ─────────────────────────
if "profiles" in st.session_state:
    st.subheader("Step 3b — Select columns to include")
    st.caption(
        "Deselect columns that are irrelevant, PII-sensitive, or metadata-only. "
        "Fewer columns = faster generation and cleaner YAML."
    )

    profiles = st.session_state["profiles"]
    column_selections: dict[str, list[str]] = {}

    for p in profiles:
        key = f"{p['database']}.{p['schema']}.{p['table']}"
        all_cols = [c["name"] for c in p["columns"]]
        col_count = len(all_cols)

        with st.expander(
            f"📋 {p['table']}  ({col_count} columns)",
            expanded=(col_count <= 30),
        ):
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("Select all", key=f"sel_all_{key}"):
                    st.session_state[f"cols_{key}"] = all_cols
                if st.button("Clear all", key=f"clr_all_{key}"):
                    st.session_state[f"cols_{key}"] = []

            with col2:
                # Show null% hint next to each column name
                options_with_hint = [
                    f"{c['name']}  ({c['null_rate']*100:.0f}% null)"
                    for c in p["columns"]
                ]
                default_selected = st.session_state.get(f"cols_{key}", all_cols)

                selected_hints = st.multiselect(
                    f"Columns for {p['table']}",
                    options=options_with_hint,
                    default=[
                        h for h in options_with_hint
                        if h.split("  (")[0] in default_selected
                    ],
                    label_visibility="collapsed",
                    key=f"ms_{key}",
                )
            # Strip the hint suffix to get plain column names
            selected_cols = [h.split("  (")[0] for h in selected_hints]
            column_selections[key] = selected_cols
            st.caption(f"{len(selected_cols)} / {col_count} columns selected")

    st.session_state["column_selections"] = column_selections

    # ── Step 3c — column definitions (optional) ───────────────────────────────
    st.subheader("Step 3c — Add column definitions (optional)")
    st.caption(
        "Provide plain-English definitions for columns with cryptic names or "
        "domain-specific meaning. Leave blank to let the LLM infer from context."
    )

    user_definitions: dict[str, dict[str, str]] = {}

    for p in profiles:
        key = f"{p['database']}.{p['schema']}.{p['table']}"
        selected_cols = column_selections.get(key, [])
        if not selected_cols:
            continue

        with st.expander(f"📝 {p['table']}  — define columns", expanded=False):
            table_defs: dict[str, str] = {}
            # Show in two-column layout to save vertical space
            pairs = list(selected_cols)
            left_cols = pairs[::2]
            right_cols = pairs[1::2]
            col_left, col_right = st.columns(2)
            for col_name in left_cols:
                with col_left:
                    val = st.text_input(
                        col_name,
                        value=st.session_state.get(f"def_{key}_{col_name}", ""),
                        placeholder=f"e.g. First-time pick rate numerator",
                        key=f"defi_{key}_{col_name}",
                    )
                    safe_val = val or ""
                    if safe_val.strip():
                        table_defs[col_name] = safe_val
            for col_name in right_cols:
                with col_right:
                    val = st.text_input(
                        col_name,
                        value=st.session_state.get(f"def_{key}_{col_name}", ""),
                        placeholder=f"e.g. First-time pick rate denominator",
                        key=f"defr_{key}_{col_name}",
                    )
                    safe_val = val or ""
                    if safe_val.strip():
                        table_defs[col_name] = safe_val
            user_definitions[key] = table_defs
            defined = sum(1 for v in table_defs.values() if v.strip())
            if defined:
                st.caption(f"{defined} definition(s) provided")

    st.session_state["user_definitions"] = user_definitions

    # ── Step 3d — derived metrics (optional) ──────────────────────────────────
    st.subheader("Step 3d — Add derived calculations (optional)")
    st.caption(
        "Define calculated metrics to force into the semantic model. "
        "Use one line per metric: METRIC_NAME = SQL_EXPRESSION | optional description"
    )

    derived_metrics: dict[str, list[dict]] = {}
    for p in profiles:
        key = f"{p['database']}.{p['schema']}.{p['table']}"
        selected_cols = column_selections.get(key, [])
        if not selected_cols:
            continue

        with st.expander(f"🧮 {p['table']}  — derived metrics", expanded=False):
            txt = st.text_area(
                "One metric per line",
                value=st.session_state.get(f"derived_{key}", ""),
                placeholder=(
                    "FTPR_RATE = SUM(FTPR_NUMERATOR) / NULLIF(SUM(FTPR_DENOMINATOR), 0) | "
                    "First-time pick rate\n"
                    "NIL_PICK_RATE = SUM(NIL_PICK_NUMERATOR) / NULLIF(SUM(NIL_PICK_DENOMINATOR), 0)"
                ),
                height=120,
                key=f"derived_input_{key}",
            )
            parsed = _parse_derived_metrics_text(txt or "")
            derived_metrics[key] = parsed
            st.caption(f"{len(parsed)} derived metric(s) parsed")

    st.session_state["derived_metrics"] = derived_metrics

    # ── Step 3e — row-level filters (optional) ───────────────────────────────
    st.subheader("Step 3e — Add row-level filters (optional)")
    st.caption(
        "Constrain the analysis scope with SQL predicates per table. "
        "Example: FTPR_DENOMINATOR IS NOT NULL"
    )

    filter_rules: dict[str, str] = {}
    for p in profiles:
        key = f"{p['database']}.{p['schema']}.{p['table']}"
        selected_cols = column_selections.get(key, [])
        if not selected_cols:
            continue

        with st.expander(f"🔒 {p['table']}  — filter rules", expanded=False):
            rule = st.text_area(
                "SQL predicate (without WHERE)",
                value=st.session_state.get(f"filter_{key}", ""),
                placeholder=(
                    "FTPR_DENOMINATOR IS NOT NULL\n"
                    "AND WEEK_END_DATE >= DATEADD('year', -1, CURRENT_DATE())"
                ),
                height=90,
                key=f"filter_input_{key}",
            )
            filter_rules[key] = (rule or "").strip()

    st.session_state["filter_rules"] = filter_rules

    # ── Generate button ────────────────────────────────────────────────────────
    any_selected = any(len(v) > 0 for v in column_selections.values())
    generate_btn = st.button(
        "🚀 Generate YAML",
        type="primary",
        disabled=not any_selected,
    )

    if generate_btn:
        filtered = _filter_profiles(profiles, column_selections)
        filtered = _apply_user_definitions(filtered, st.session_state.get("user_definitions", {}))
        metadata_md = profiles_to_markdown(filtered)
        derived_md = derived_metrics_to_markdown(st.session_state.get("derived_metrics", {}))
        filters_md = filter_rules_to_markdown(st.session_state.get("filter_rules", {}))
        st.session_state["metadata_md"] = metadata_md
        st.session_state["derived_md"] = derived_md
        st.session_state["filters_md"] = filters_md

        # ── token estimate pre-flight check ──────────────────────────────────
        prompt_chars = (
            len(metadata_md)
            + len(derived_md)
            + len(filters_md)
            + len(domain_description)
            + len(business_question)
            + 4000
        )
        estimated_tokens = prompt_chars // 4
        context_limit = _MODEL_CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOW)
        pct_used = estimated_tokens / context_limit
        if pct_used > 0.85:
            st.error(
                f"⚠️ Estimated prompt size (~{estimated_tokens:,} tokens) exceeds the safe limit for "
                f"`{model}`. Switch to a model with a larger context window (e.g. `claude-sonnet-4-6`) "
                "or reduce the number of columns selected."
            )
            st.stop()
        elif pct_used > 0.60:
            st.warning(
                f"ℹ️ Large prompt (~{estimated_tokens:,} tokens). "
                "Consider deselecting more columns or switching to a larger-context model if output is truncated."
            )
        else:
            st.caption(f"Estimated prompt size: ~{estimated_tokens:,} tokens.")

        with st.spinner(f"Sending to {model} via Snowflake Cortex…"):
            try:
                yaml_text, raw_output, parse_err = generate_yaml(
                    domain_name=domain_name,
                    domain_description=domain_description,
                    business_question=business_question,
                    metadata_markdown=metadata_md,
                    model=model,
                    derived_metrics_markdown=derived_md,
                    filter_rules_markdown=filters_md,
                )
                is_valid, err = validate_yaml(yaml_text)
                st.session_state["generated_yaml"] = yaml_text
                st.session_state["raw_llm_output"] = raw_output
                st.session_state["yaml_parse_err"] = parse_err
                st.session_state["yaml_valid"] = is_valid
                st.session_state["yaml_err"] = err
                st.session_state["output_filename"] = (
                    output_filename or f"{domain_name.lower().replace(' ', '-')}.yaml"
                )
                if parse_err:
                    st.warning(
                        f"⚠️ YAML cleanup hit a parse error (raw output preserved): {parse_err}. "
                        "Expand 'Raw LLM output' below to inspect and fix manually."
                    )
                elif is_valid:
                    st.success("YAML generated and validated.")
                else:
                    st.warning(f"YAML generated but has parse issues: {err}")
            except Exception as exc:
                st.error(f"Generation failed: {exc}")
                st.stop()

# Step 4
if "generated_yaml" in st.session_state:
    st.header("Step 4 — Review and edit")

    with st.expander("📋 Table metadata used", expanded=False):
        st.markdown(st.session_state.get("metadata_md", ""))
        derived_context = st.session_state.get("derived_md", "")
        if derived_context:
            st.markdown("---")
            st.markdown(derived_context)
        filter_context = st.session_state.get("filters_md", "")
        if filter_context:
            st.markdown("---")
            st.markdown(filter_context)

    st.caption(
        "Edit the YAML inline. "
        "`# LOW_CONFIDENCE:` comments mark fields the model was uncertain about — review those first."
    )

    edited_yaml = st.text_area(
        "Generated semantic view YAML",
        value=st.session_state["generated_yaml"],
        height=600,
        key="yaml_editor",
    ) or ""

    try:
        import yaml as _yaml
        _docs = [d for d in _yaml.safe_load_all(edited_yaml) if d is not None]
        if _docs:
            st.success("✅ YAML is valid")
        else:
            st.error("❌ YAML parsed but produced no content.")
    except Exception as _e:
        st.error(f"❌ YAML parse error: {_e}")

    st.header("Step 5 — Save / deploy")
    fname = st.session_state.get("output_filename", "semantic_model.yaml")

    dl_col, deploy_col = st.columns(2)
    with dl_col:
        st.download_button(
            label="⬇️ Download YAML",
            data=edited_yaml,
            file_name=fname,
            mime="text/yaml",
        )

    with deploy_col:
        st.info(
            "To deploy directly from here, run in a Snowflake worksheet:\n\n"
            "```sql\n"
            "SELECT SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(\n"
            "  'DATABASE.SCHEMA',\n"
            "  $$ <paste YAML here> $$\n"
            ");\n"
            "```"
        )

    # Optional: save to stage
    with st.expander("📤 Save to Snowflake stage (optional)", expanded=False):
        stage_path = st.text_input(
            "Stage path",
            value=f"@CCB_DATASCIENCE_DEV.PUBLIC.SEMANTIC_MODELS/{fname}",
        )
        if st.button("Upload to stage"):
            try:
                import tempfile, os
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as tmp:
                    tmp.write(edited_yaml)
                    tmp_path = tmp.name
                session.file.put(
                    tmp_path,
                    stage_path.rsplit("/", 1)[0],
                    overwrite=True,
                    auto_compress=False,
                )
                os.unlink(tmp_path)
                st.success(f"Uploaded to {stage_path}")
            except Exception as exc:
                st.error(f"Upload failed: {exc}")
