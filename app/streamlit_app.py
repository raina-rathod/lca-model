"""
CA-GREET4 Tier 1 — Dairy/Swine Manure Biomethane
A friendlier, interactive front-end to CARB's official .xlsm calculator.

Run locally:        streamlit run app/streamlit_app.py
Deploy (Streamlit Community Cloud): point it at this file; requirements.txt is
in the same folder.

All carbon-intensity numbers are produced by recalculating the *actual*
spreadsheet via the `formulas` engine, so results match the official model.
"""
from __future__ import annotations

import pickle

import pandas as pd
import streamlit as st

from engine import GreetEngine, load_model

st.set_page_config(page_title="CA-GREET4 Manure Biomethane", layout="wide", page_icon="🐄")


# --------------------------------------------------------------------------- #
# Cached resources
# --------------------------------------------------------------------------- #
@st.cache_data
def get_model():
    return load_model()


@st.cache_resource(show_spinner="Loading CA-GREET4 calculation engine (one-time, ~6s)…")
def get_engine(workbook: str):
    return GreetEngine(workbook)


MODEL = get_model()


# --------------------------------------------------------------------------- #
# Session state helpers
# --------------------------------------------------------------------------- #
def col_header(c: dict) -> str:
    return f"{c['label']} ({c['unit']})" if c["unit"] else c["label"]


def init_state():
    if "init" in st.session_state:
        return
    st.session_state.init = True
    st.session_state.n_months = 12
    st.session_state.n_categories = 1
    # setup field values
    for f in MODEL["setup_fields"]:
        st.session_state[f"setup::{f['key'][0]}::{f['key'][1]}"] = f["default"]
    # table dataframes
    for t in MODEL["tables"]:
        st.session_state[f"table::{t['id']}"] = empty_table_df(t, st.session_state.n_months)


def empty_table_df(t: dict, n_rows: int) -> pd.DataFrame:
    data = {t["index_label"]: ["" for _ in range(n_rows)]}
    for c in t["columns"]:
        data[col_header(c)] = ["" if c["type"] != "number" else None for _ in range(n_rows)]
    return pd.DataFrame(data)


def resize_tables(n_rows: int):
    for t in MODEL["tables"]:
        key = f"table::{t['id']}"
        df = st.session_state.get(key)
        if df is None:
            st.session_state[key] = empty_table_df(t, n_rows)
            continue
        if len(df) < n_rows:
            extra = empty_table_df(t, n_rows - len(df))
            st.session_state[key] = pd.concat([df, extra], ignore_index=True)
        elif len(df) > n_rows:
            st.session_state[key] = df.iloc[:n_rows].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Build inputs dict for the engine
# --------------------------------------------------------------------------- #
def collect_inputs() -> dict:
    inputs = {}
    for f in MODEL["setup_fields"]:
        s, c = f["key"]
        inputs[(s, c)] = st.session_state.get(f"setup::{s}::{c}")

    for t in MODEL["tables"]:
        df = st.session_state.get(f"table::{t['id']}")
        if df is None:
            continue
        sheet = t["sheet"]
        for r in range(len(df)):
            sheet_row = t["row_start"] + r
            month = df.iloc[r][t["index_label"]]
            if month not in (None, ""):
                inputs[(sheet, f"{t['index_col']}{sheet_row}")] = month
            for c in t["columns"]:
                val = df.iloc[r][col_header(c)]
                if val not in (None, ""):
                    inputs[(sheet, f"{c['col']}{sheet_row}")] = val
    return inputs


def serialize_scenario() -> bytes:
    state = {
        "n_months": st.session_state.n_months,
        "n_categories": st.session_state.n_categories,
        "setup": {f"{f['key'][0]}::{f['key'][1]}":
                  st.session_state.get(f"setup::{f['key'][0]}::{f['key'][1]}")
                  for f in MODEL["setup_fields"]},
        "tables": {t["id"]: st.session_state.get(f"table::{t['id']}").to_dict("list")
                   for t in MODEL["tables"]},
    }
    return pickle.dumps(state)


def load_scenario(raw: bytes):
    state = pickle.loads(raw)
    st.session_state.n_months = state.get("n_months", 12)
    st.session_state.n_categories = state.get("n_categories", 1)
    for k, v in state.get("setup", {}).items():
        st.session_state[f"setup::{k}"] = v
    for tid, cols in state.get("tables", {}).items():
        st.session_state[f"table::{tid}"] = pd.DataFrame(cols)


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
init_state()

st.title("🐄 CA-GREET4 Carbon-Intensity Explorer")
st.caption(MODEL["title"] + " — a friendly interface to CARB's official Tier 1 calculator.")

# ---- Sidebar -------------------------------------------------------------- #
with st.sidebar:
    st.header("Scenario")
    st.session_state.n_months = st.number_input(
        "Number of reporting months", 1, 24, st.session_state.n_months, 1,
        help="Controls how many month-rows each data table shows (workbook max is 24).")
    st.session_state.n_categories = st.slider(
        "Livestock categories in use", 1, 6, st.session_state.n_categories,
        help="How many baseline livestock-category tables to display.")
    resize_tables(st.session_state.n_months)

    st.divider()
    st.subheader("Save / Load")
    st.download_button("💾 Download scenario (.pkl)", data=serialize_scenario(),
                       file_name="greet_scenario.pkl", mime="application/octet-stream",
                       width='stretch')
    up = st.file_uploader("Load scenario (.pkl)", type=["pkl"])
    if up is not None and st.button("Apply uploaded scenario", width='stretch'):
        load_scenario(up.read())
        st.success("Scenario loaded.")
        st.rerun()

    st.divider()
    show_advanced = st.toggle("Show all data columns", value=False,
                              help="Off = only the most common metered columns.")
    if st.button("↺ Reset all inputs", width='stretch'):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ---- Setup fields grouped ------------------------------------------------- #
groups: dict[str, list] = {}
for f in MODEL["setup_fields"]:
    groups.setdefault(f["group"], []).append(f)

st.subheader("Project Configuration")
for gname, fields in groups.items():
    with st.expander(gname, expanded=(gname == "Project Setup")):
        cols = st.columns(3)
        for i, f in enumerate(fields):
            s, c = f["key"]
            skey = f"setup::{s}::{c}"
            label = f["label"] + (f"  ({f['unit']})" if f["unit"] else "")
            with cols[i % 3]:
                if f["type"] == "select":
                    opts = f["options"]
                    cur = st.session_state.get(skey)
                    idx = opts.index(cur) if cur in opts else 0
                    st.session_state[skey] = st.selectbox(label, opts, index=idx, key=f"w_{skey}")
                elif f["type"] == "text":
                    st.session_state[skey] = st.text_input(
                        label, value=st.session_state.get(skey) or "", key=f"w_{skey}")
                else:
                    cur = st.session_state.get(skey)
                    cur = cur if isinstance(cur, (int, float)) else None
                    st.session_state[skey] = st.number_input(
                        label, value=cur, key=f"w_{skey}",
                        placeholder="enter a value…")

# ---- Data tables ---------------------------------------------------------- #
PRIMARY_HINT = ("Raw Biogas", "Biomethane Content", "Injected", "Diesel", "Grid Electricity",
                "Population", "Temperature", "Reporting", "Retention", "Volatile", "Flared")


def render_table(t: dict):
    df = st.session_state[f"table::{t['id']}"]
    colcfg = {t["index_label"]: st.column_config.TextColumn(t["index_label"], width="small")}
    visible = [t["index_label"]]
    for c in t["columns"]:
        h = col_header(c)
        if not show_advanced and not any(k in c["label"] for k in PRIMARY_HINT):
            continue
        visible.append(h)
        if c["type"] == "select":
            colcfg[h] = st.column_config.SelectboxColumn(h, options=c["options"], width="medium")
        else:
            colcfg[h] = st.column_config.NumberColumn(h, format="%.4g")
    if t["note"]:
        st.caption(t["note"])
    edited = st.data_editor(df[visible], column_config=colcfg, key=f"ed::{t['id']}",
                            width='stretch', hide_index=True, num_rows="fixed")
    # write edited (visible) columns back into the full df
    for col in visible:
        df[col] = edited[col].values
    st.session_state[f"table::{t['id']}"] = df


st.subheader("Monthly Data Entry")
prod = next(t for t in MODEL["tables"] if t["id"] == "production")
with st.expander("📊 " + prod["title"], expanded=True):
    render_table(prod)

with st.expander("🐮 Baseline Methane — Livestock Categories", expanded=False):
    cats = [t for t in MODEL["tables"] if t["id"].startswith("manure_cat")]
    tabs = st.tabs([f"Category {i+1}" for i in range(st.session_state.n_categories)])
    for i, tab in enumerate(tabs):
        with tab:
            render_table(cats[i])

# ---- Results -------------------------------------------------------------- #
st.divider()
st.subheader("Carbon-Intensity Results")
left, right = st.columns([1, 2])
with left:
    run = st.button("⚡ Calculate Carbon Intensity", type="primary", width='stretch')

if run:
    eng = get_engine(MODEL["workbook"])
    inputs = collect_inputs()
    with st.spinner("Recalculating the CA-GREET4 model…"):
        out_keys = [tuple(o["key"]) for o in MODEL["outputs"]]
        bd_keys = [tuple(o["key"]) for o in MODEL["breakdown"]]
        res = eng.compute(inputs, out_keys + bd_keys)
    st.session_state["results"] = {
        "outputs": [(o["label"], o["unit"], res.get(tuple(o["key"]))) for o in MODEL["outputs"]],
        "breakdown": [(o["label"], res.get(tuple(o["key"]))) for o in MODEL["breakdown"]],
    }

if "results" in st.session_state:
    r = st.session_state["results"]
    mcols = st.columns(len(r["outputs"]))
    for col, (label, unit, val) in zip(mcols, r["outputs"]):
        with col:
            disp = "N/A" if val in (None, "N/A") else f"{float(val):.2f}"
            st.metric(label, f"{disp}", help=unit)
    bd = [(lbl, float(v)) for lbl, v in r["breakdown"] if isinstance(v, (int, float))]
    if bd:
        st.markdown("**CI Breakdown (gCO₂e/MJ)**")
        chart_df = pd.DataFrame(bd, columns=["Component", "gCO2e/MJ"]).set_index("Component")
        st.bar_chart(chart_df, horizontal=True)
else:
    st.info("Fill in the data above, then press **Calculate Carbon Intensity**. "
            "Results match CARB's official spreadsheet.")
