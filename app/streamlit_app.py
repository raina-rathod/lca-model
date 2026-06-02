"""
CA-GREET4 / Clean-Fuel Carbon-Intensity Explorer
A friendly, interactive front-end to CARB's official biomethane calculators,
structured so multiple markets (California LCFS, Canada CFR) and feedstocks
(manure, landfill, …) live behind Market + Feedstock toggles.

Run locally:  streamlit run app/streamlit_app.py
All carbon-intensity numbers are produced by recalculating the *actual*
spreadsheet via the `formulas` engine, so results match the official model.
"""
from __future__ import annotations

import pickle

import pandas as pd
import streamlit as st

import models
from engine import GreetEngine, load_model

st.set_page_config(page_title="Carbon-Intensity Explorer", layout="wide", page_icon="🔥")


# --------------------------------------------------------------------------- #
# Cached resources
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def get_schema(schema_file: str):
    return load_model(schema_file)


@st.cache_resource(show_spinner="Loading calculation engine (one-time, ~6s)…")
def get_engine(workbook: str):
    return GreetEngine(workbook)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def col_header(c: dict) -> str:
    return f"{c['label']} ({c['unit']})" if c["unit"] else c["label"]


def scenario_table_df(t: dict, scenario: dict, n_rows: int) -> pd.DataFrame:
    """Build a table DataFrame, pre-filled from the model's default scenario."""
    cells = (scenario or {}).get("cells", {}).get(t["id"], {})

    def column_values(letter, ctype):
        v = cells.get(letter)
        if v is None:
            return ["" if ctype != "number" else None] * n_rows
        if isinstance(v, list):
            return (v + [None] * n_rows)[:n_rows]
        return [v] * n_rows

    data = {t["index_label"]: column_values(t["index_col"], "text")}
    for c in t["columns"]:
        data[col_header(c)] = column_values(c["col"], c["type"])
    return pd.DataFrame(data)


def apply_scenario(schema: dict, scenario: dict):
    """Reset session_state to a model + its default scenario."""
    scenario = scenario or {"setup": {}, "scalars": {}, "cells": {}}
    st.session_state.n_months = scenario.get("n_months", 12)
    st.session_state.n_categories = scenario.get("n_categories", 1)

    for f in schema["setup_fields"]:
        s, c = f["key"]
        val = scenario.get("setup", {}).get((s, c), f["default"])
        st.session_state[f"setup::{s}::{c}"] = val

    for t in schema["tables"]:
        for sc in t.get("scalars", []):
            dv = scenario.get("scalars", {}).get(t["id"], {}).get(sc["cell"], sc["default"])
            st.session_state[f"scalar::{t['id']}::{sc['cell']}"] = dv
        st.session_state[f"table::{t['id']}"] = scenario_table_df(
            t, scenario, st.session_state.n_months)


def resize_tables(schema: dict, n_rows: int):
    for t in schema["tables"]:
        key = f"table::{t['id']}"
        df = st.session_state.get(key)
        if df is None:
            st.session_state[key] = scenario_table_df(t, None, n_rows)
        elif len(df) < n_rows:
            extra = scenario_table_df(t, None, n_rows - len(df))
            st.session_state[key] = pd.concat([df, extra], ignore_index=True)
        elif len(df) > n_rows:
            st.session_state[key] = df.iloc[:n_rows].reset_index(drop=True)


def collect_inputs(schema: dict) -> dict:
    inputs = {}
    for f in schema["setup_fields"]:
        s, c = f["key"]
        inputs[(s, c)] = st.session_state.get(f"setup::{s}::{c}")

    for t in schema["tables"]:
        sheet = t["sheet"]
        for sc in t.get("scalars", []):
            inputs[(sheet, sc["cell"])] = st.session_state.get(
                f"scalar::{t['id']}::{sc['cell']}")
        df = st.session_state.get(f"table::{t['id']}")
        if df is None:
            continue
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


def compute(model: dict, schema: dict):
    eng = get_engine(model["workbook"])
    inputs = collect_inputs(schema)
    out_keys = [tuple(o["key"]) for o in schema["outputs"]]
    bd_keys = [tuple(o["key"]) for o in schema["breakdown"]]
    res = eng.compute(inputs, out_keys + bd_keys)
    st.session_state["results"] = {
        "outputs": [(o["label"], o["unit"], res.get(tuple(o["key"]))) for o in schema["outputs"]],
        "breakdown": [(o["label"], res.get(tuple(o["key"]))) for o in schema["breakdown"]],
    }


def serialize_scenario(schema: dict) -> bytes:
    state = {
        "n_months": st.session_state.n_months,
        "n_categories": st.session_state.n_categories,
        "setup": {f"{s}::{c}": st.session_state.get(f"setup::{s}::{c}")
                  for (s, c) in [tuple(f["key"]) for f in schema["setup_fields"]]},
        "scalars": {t["id"]: {sc["cell"]: st.session_state.get(f"scalar::{t['id']}::{sc['cell']}")
                              for sc in t.get("scalars", [])} for t in schema["tables"]},
        "tables": {t["id"]: st.session_state.get(f"table::{t['id']}").to_dict("list")
                   for t in schema["tables"]},
    }
    return pickle.dumps(state)


def load_uploaded_scenario(schema: dict, raw: bytes):
    state = pickle.loads(raw)
    st.session_state.n_months = state.get("n_months", 12)
    st.session_state.n_categories = state.get("n_categories", 1)
    for k, v in state.get("setup", {}).items():
        st.session_state[f"setup::{k}"] = v
    for tid, scs in state.get("scalars", {}).items():
        for cell, v in scs.items():
            st.session_state[f"scalar::{tid}::{cell}"] = v
    for tid, cols in state.get("tables", {}).items():
        st.session_state[f"table::{tid}"] = pd.DataFrame(cols)


# --------------------------------------------------------------------------- #
# Sidebar — market & feedstock toggles
# --------------------------------------------------------------------------- #
st.sidebar.header("Market & Feedstock")
market = st.sidebar.selectbox("Market", models.MARKETS)
feedstocks = models.feedstocks_for(market)
feedstock = st.sidebar.selectbox("Feedstock", feedstocks) if feedstocks else None
model = models.get_model(market, feedstock) if feedstock else None

st.title("🔥 Carbon-Intensity Explorer")
st.caption("Friendly interface to CARB's official biomethane calculators — "
           "toggle market and feedstock, edit any value, get a live CI.")

# ---- inactive / placeholder models --------------------------------------- #
if not model or model.get("status") != "active":
    st.info(f"**{market} → {feedstock or '—'}** is not available yet.")
    if model and model.get("note"):
        st.warning(model["note"])
    st.stop()

# ---- active model: load schema + apply defaults on switch ---------------- #
SCHEMA = get_schema(model["schema"])

if st.session_state.get("active_model_id") != model["id"]:
    st.session_state["active_model_id"] = model["id"]
    apply_scenario(SCHEMA, model["default_scenario"]())
    compute(model, SCHEMA)  # default CI on load

st.success(f"**{market} → {model['feedstock']}** · CA-GREET4 Tier 1")

# ---- sidebar scenario controls ------------------------------------------- #
with st.sidebar:
    st.divider()
    st.session_state.n_months = st.number_input(
        "Reporting months", 1, 24, st.session_state.n_months, 1)
    st.session_state.n_categories = st.slider(
        "Livestock categories", 1, 6, st.session_state.n_categories)
    resize_tables(SCHEMA, st.session_state.n_months)

    st.divider()
    show_advanced = st.toggle("Show all data columns", value=False)
    if st.button("↺ Reset to default scenario", width="stretch"):
        apply_scenario(SCHEMA, model["default_scenario"]())
        compute(model, SCHEMA)
        st.rerun()

    st.divider()
    st.subheader("Save / Load")
    st.download_button("💾 Download scenario (.pkl)", data=serialize_scenario(SCHEMA),
                       file_name=f"{model['id']}_scenario.pkl",
                       mime="application/octet-stream", width="stretch")
    up = st.file_uploader("Load scenario (.pkl)", type=["pkl"])
    if up is not None and st.button("Apply uploaded scenario", width="stretch"):
        load_uploaded_scenario(SCHEMA, up.read())
        compute(model, SCHEMA)
        st.rerun()

# --------------------------------------------------------------------------- #
# Results (top — default CI is shown on load)
# --------------------------------------------------------------------------- #
st.subheader("Carbon-Intensity Results")
if st.button("⚡ Recalculate", type="primary"):
    with st.spinner("Recalculating the model…"):
        compute(model, SCHEMA)

if "results" in st.session_state:
    r = st.session_state["results"]
    mcols = st.columns(len(r["outputs"]))
    for col, (label, unit, val) in zip(mcols, r["outputs"]):
        disp = "N/A" if val in (None, "N/A") else f"{float(val):.1f}"
        col.metric(label, disp, help=unit)
    bd = [(lbl, float(v)) for lbl, v in r["breakdown"] if isinstance(v, (int, float))]
    if bd:
        st.markdown("**CI Breakdown (gCO₂e/MJ)**")
        st.bar_chart(pd.DataFrame(bd, columns=["Component", "gCO2e/MJ"]
                                  ).set_index("Component"), horizontal=True)
st.caption("Edit any value below, then press **Recalculate**. Results match "
           "CARB's official spreadsheet.")

# --------------------------------------------------------------------------- #
# Project configuration (setup fields, grouped)
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Project Configuration")
groups: dict[str, list] = {}
for f in SCHEMA["setup_fields"]:
    groups.setdefault(f["group"], []).append(f)

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
                        label, value=cur, key=f"w_{skey}", placeholder="enter a value…")

# --------------------------------------------------------------------------- #
# Data tables
# --------------------------------------------------------------------------- #
PRIMARY_HINT = ("Raw Biogas", "Biomethane Content", "Injected", "Diesel", "Grid Electricity",
                "Population", "Temperature", "Reporting", "Retention", "Volatile", "Flared")


def render_scalars(t: dict):
    if not t.get("scalars"):
        return
    cols = st.columns(len(t["scalars"]))
    for col, sc in zip(cols, t["scalars"]):
        key = f"scalar::{t['id']}::{sc['cell']}"
        with col:
            if sc["type"] == "select":
                opts = sc["options"]
                cur = st.session_state.get(key)
                idx = opts.index(cur) if cur in opts else 0
                st.session_state[key] = st.selectbox(sc["label"], opts, index=idx, key=f"w_{key}")
            else:
                st.session_state[key] = st.text_input(
                    sc["label"], value=st.session_state.get(key) or "", key=f"w_{key}")


def render_table(t: dict):
    render_scalars(t)
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
                            width="stretch", hide_index=True, num_rows="fixed")
    for col in visible:
        df[col] = edited[col].values
    st.session_state[f"table::{t['id']}"] = df


st.divider()
st.subheader("Monthly Data Entry")
prod = next((t for t in SCHEMA["tables"] if t["id"] == "production"), None)
if prod:
    with st.expander("📊 " + prod["title"], expanded=True):
        render_table(prod)

cats = [t for t in SCHEMA["tables"] if t["id"].startswith("manure_cat")]
if cats:
    with st.expander("🐮 Baseline Methane — Livestock Categories", expanded=False):
        tabs = st.tabs([f"Category {i + 1}" for i in range(st.session_state.n_categories)])
        for i, tab in enumerate(tabs):
            with tab:
                render_table(cats[i])
