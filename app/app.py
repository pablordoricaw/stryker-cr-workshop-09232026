"""The provided workshop data app (Streamlit).

Three tabs:

  * **Data app**: a KPI strip, Lakebase-powered charts, an interactive serving
    table, and an **Ask Genie** chat. The serving read and the Genie call are the
    two participant gaps in :mod:`backend`.
  * **Congratulations**: a recap of the end-to-end pipeline each participant
    built across the workshop checkpoints.
  * **About**: an overview of Databricks Apps with links to more resources.

The data surfaces delegate to :mod:`backend`, where the **two participant gaps**
live (the Genie call and the Lakebase read). This file (layout, widgets, charts,
and error handling) is already complete and does **not** need editing.

Run locally:  ``streamlit run app.py``
Deployed:     the ``app.yaml`` command runs the same under the Apps runtime,
              which auto-binds ``DATABRICKS_APP_PORT`` for Streamlit.

The app **renders cleanly even with the gaps unfilled**: the initial page never
calls a gap, and the serving/chat actions catch the ``NotImplementedError`` a
gap raises and show a friendly panel, so the app can be deployed and started
(and the ``07_app`` checkpoint's app-side can pass) before the gaps are filled.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from backend import SERVING_LIMIT, SERVING_TABLE, Backend

st.set_page_config(page_title="Workshop data app", page_icon="📊", layout="wide")

# The backend is lazy: constructing it builds no SDK client, so this is safe at
# startup even with no workspace credentials and both gaps unfilled.
backend = Backend()

_GAP_HELP = (
    "This is a **participant gap**. Open `app/backend.py`, fill the function "
    "behind this banner, and redeploy. See `solutions/<domain>/07_app.py`."
)


@st.cache_data(ttl=60, show_spinner=False)
def _load_serving(limit: int) -> list[dict]:
    """Cached read of the Lakebase serving table (per the Streamlit data tip).

    Delegates to participant GAP 2. ``cache_data`` never caches the
    ``NotImplementedError`` an unfilled gap raises, so the friendly panel keeps
    showing until the gap is filled.
    """
    return backend.fetch_serving_rows(limit=limit)


def _current_user() -> str | None:
    """Best-effort signed-in identity from the Apps user-auth headers."""
    try:
        headers = st.context.headers or {}
        return headers.get("x-forwarded-preferred-username") or headers.get(
            "x-forwarded-email"
        )
    except Exception:  # noqa: BLE001 - headers exist only when deployed
        return None


def _kpi_row(df: pd.DataFrame) -> None:
    """A compact metric strip over the served rows (domain-neutral)."""
    numeric = df.select_dtypes("number")
    cols = st.columns(3)
    cols[0].metric("Rows", f"{len(df):,}")
    cols[1].metric("Columns", f"{df.shape[1]:,}")
    if not numeric.empty:
        first = numeric.columns[0]
        cols[2].metric(f"Avg {first}", f"{numeric[first].mean():,.2f}")
    else:
        cols[2].metric("Numeric columns", "0")


def _charts(df: pd.DataFrame) -> None:
    """Two domain-neutral charts over the served rows, powered by Lakebase.

    Picks the first numeric column as the metric and the first low-cardinality
    non-numeric column as a category. Falls back gracefully when the shape does
    not support a grouped view.
    """
    numeric = df.select_dtypes("number")
    if numeric.empty:
        st.info("No numeric columns in the serving table to visualize.")
        return
    metric = numeric.columns[0]
    category = next(
        (
            c
            for c in df.columns
            if c not in numeric.columns and 1 < df[c].nunique() <= 25
        ),
        None,
    )
    left, right = st.columns(2)
    with left:
        if category:
            st.caption(f"Total **{metric}** by **{category}** (top 10)")
            agg = (
                df.groupby(category)[metric].sum().sort_values(ascending=False).head(10)
            )
            st.bar_chart(agg)
        else:
            st.caption(f"**{metric}** across rows")
            st.bar_chart(numeric[metric].reset_index(drop=True))
    with right:
        label = category or df.columns[0]
        st.caption(f"Top 10 rows by **{metric}**")
        st.bar_chart(df.nlargest(10, metric).set_index(label)[metric])


def _render_chat() -> None:
    """The Ask-Genie chat (participant GAP 1)."""
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sql"):
                with st.expander("SQL"):
                    st.code(msg["sql"], language="sql")

    if prompt := st.chat_input("e.g. Which contract had the highest net sales?"):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Asking your Genie agent…"):
                    result = backend.ask_genie(prompt)
                status = str(result.get("status", "unknown"))
                answer = result.get("answer") or f"_(Genie returned status: {status})_"
                sql = result.get("sql")
                st.markdown(answer)
                if sql:
                    with st.expander("SQL"):
                        st.code(sql, language="sql")
                st.session_state["messages"].append(
                    {"role": "assistant", "content": answer, "sql": sql}
                )
            except NotImplementedError as exc:
                body = f"🧩 {exc}\n\n{_GAP_HELP}"
                st.markdown(body)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": body}
                )
            except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
                body = f"🚫 Genie call failed: {exc}"
                st.error(body)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": body}
                )


def _render_data_app() -> None:
    """The working data app: serving table + KPIs + charts, then the chat."""
    st.subheader("Serving table (Lakebase)")
    st.caption(f"Source: `{SERVING_TABLE}`")

    if st.button("Load rows", type="primary"):
        with st.spinner("Reading the Lakebase synced serving table…"):
            try:
                st.session_state["serving_rows"] = _load_serving(SERVING_LIMIT)
                st.session_state.pop("serving_error", None)
            except NotImplementedError as exc:
                st.session_state["serving_error"] = ("gap", str(exc))
                st.session_state.pop("serving_rows", None)
            except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
                st.session_state["serving_error"] = ("error", str(exc))
                st.session_state.pop("serving_rows", None)

    error = st.session_state.get("serving_error")
    if error is not None:
        kind, message = error
        if kind == "gap":
            st.warning(message, icon="🧩")
            st.info(_GAP_HELP)
        else:
            st.error(f"Could not read the serving table: {message}", icon="🚫")
    elif "serving_rows" in st.session_state:
        rows = st.session_state["serving_rows"]
        if rows:
            df = pd.DataFrame(rows)
            _kpi_row(df)
            st.markdown("#### Visualizations")
            _charts(df)
            st.markdown("#### Rows")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("The serving table returned no rows yet.")
    else:
        st.caption(
            "Click **Load rows** to read from Lakebase; the KPIs, charts, and "
            "table populate once the Lakebase gap is wired."
        )

    st.divider()
    st.subheader("Ask your Genie agent")
    _render_chat()


def _render_congrats() -> None:
    """A recap of the end-to-end pipeline built across the checkpoints."""
    st.subheader("🎉 Congratulations: you built an end-to-end lakehouse app!")
    st.success(
        "From raw documents and transactional data to a governed semantic layer, "
        "a natural-language Genie agent, and this data app, all on Databricks."
    )
    st.markdown("#### What you built")
    st.markdown(
        """
- **Setup** (`00_setup`): your own schema + UC Volume inside the team catalog.
- **Bronze** (`01_bronze_docs`, `01_bronze_txn`): landed domain PDFs into a
  governed Volume and ingested transactional data (Lakebase CDF, or the Delta
  fallback).
- **Silver** (`02_silver_docs`): `ai_classify` → `ai_parse_document` →
  `ai_extract` turned unstructured PDFs into structured tables.
- **Gold** (`03_gold`): medallion business tables ready for analytics.
- **Metadata** (`04_metadata`): `dbxmetagen` generated comments, PI
  classification, and domain tags for your gold tables.
- **Semantic layer** (`05_metric_views`): governed, reusable UC Metric Views.
- **Genie agent** (`06_genie`): ask questions of your data in plain language.
- **Data app** (`07_app`): this Streamlit app, wired to your Genie agent and a
  Lakebase-synced serving table.
"""
    )
    st.markdown("#### Every checkpoint is green")
    st.caption(
        "Each step was validated by `workshop.check(...)` against your own "
        "per-participant objects: schema, gold tables, metric views, Genie "
        "agent, app, and Lakebase synced table."
    )
    if st.button("Celebrate 🎈"):
        st.balloons()


def _render_about() -> None:
    """An overview of Databricks Apps with links to more resources."""
    st.subheader("About Databricks Apps")
    st.markdown(
        """
**Databricks Apps** let you build and host interactive data & AI applications
directly on Databricks, with no separate infrastructure to manage. This app is
one of them.

**Why it's a good fit for this app**

- **Python-native UI.** Supported frameworks include Streamlit (this app), Dash,
  Gradio, Flask, and FastAPI, all pre-installed in the runtime.
- **Built-in identity & governance.** Apps run with SSO and a service-principal
  identity; access to data flows through Unity Catalog, so the app only sees
  what it's granted.
- **First-class resources.** Wire a **Genie space**, a **Lakebase** database, a
  **SQL warehouse**, model-serving endpoints, or secrets to the app; their ids
  and credentials are injected as environment variables (never hardcoded).
- **Managed runtime.** Python 3.11, 2 vCPU / 6 GB by default; dependencies come
  from `requirements.txt` (pip) or `pyproject.toml` + `uv.lock` (uv).
"""
    )
    st.markdown("#### How *this* app is wired")
    st.markdown(
        """
- A **Genie space** resource (`genie-space`) → `GENIE_SPACE_ID` powers the chat.
- A **Lakebase** database resource (`postgres`) → `PG*` / `LAKEBASE_ENDPOINT`
  powers the serving table and charts.
- `SERVING_TABLE` points at your per-participant Lakebase-synced serving table.
"""
    )
    st.markdown("#### Learn more")
    cols = st.columns(2)
    with cols[0]:
        st.link_button(
            "Databricks Apps overview",
            "https://docs.databricks.com/dev-tools/databricks-apps/",
        )
        st.link_button(
            "Authorization (app & user auth)",
            "https://docs.databricks.com/dev-tools/databricks-apps/auth",
        )
    with cols[1]:
        st.link_button(
            "App resources",
            "https://docs.databricks.com/dev-tools/databricks-apps/resources",
        )
        st.link_button(
            "app.yaml & runtime",
            "https://docs.databricks.com/dev-tools/databricks-apps/app-runtime",
        )


st.title("📊 Workshop data app")
st.caption(
    "Reads a Lakebase-synced serving table and answers questions through your "
    "Genie agent."
)

_user = _current_user()
if _user:
    st.caption(f"Signed in as **{_user}**")

_tab_app, _tab_congrats, _tab_about = st.tabs(
    ["📊 Data app", "🎉 Congratulations", "ℹ️ About"]
)
with _tab_app:
    _render_data_app()
with _tab_congrats:
    _render_congrats()
with _tab_about:
    _render_about()
