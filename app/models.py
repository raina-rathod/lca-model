"""
models.py — Registry of (market × feedstock) models the app can load.

Each *active* model points to a CARB .xlsm + its extracted schema (model.pkl)
and ships a calibrated default scenario so a sensible carbon intensity shows on
load. Everything in the scenario is fully editable in the UI.

Markets are scaffolded so the Canadian Clean Fuel Regulation can be dropped in
later without restructuring.
"""
from __future__ import annotations

# Market identifiers (toggle at the top of the app)
CALIFORNIA = "California (LCFS / CA-GREET4)"
CANADA = "Canada (Clean Fuel Regulation)"

MARKETS = [CALIFORNIA, CANADA]


# --------------------------------------------------------------------------- #
# Default scenarios
# --------------------------------------------------------------------------- #
def _months(n=12):
    return [f"{m:02d}/2024" for m in range(1, n + 1)]


_CAL_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def dairy_default_scenario() -> dict:
    """
    Calibrated 12-month dairy scenario → CNG CI ≈ -264 gCO2e/MJ.

    Cell values may be a scalar (applied to every month) or a 12-item list.
    Keys are spreadsheet cell references so the scenario is independent of UI
    column labels. See app/build_model.py for the schema these map onto.
    """
    return {
        "n_months": 12,
        "n_categories": 1,
        # single-cell setup inputs, keyed by (SHEET, CELL)
        "setup": {
            ("AVOIDED EMISSIONS", "C4"): "Covered Lagoon",
            ("BIOGAS-TO-RNG", "D24"): "CAMX",
            ("BIOGAS-TO-RNG", "C19"): "California",
            ("BIOGAS-TO-RNG", "AH54"): 0.02,
        },
        # per-table scalar inputs (livestock category, baseline reporting period)
        "scalars": {
            "manure_cat1": {"B7": "Dairy cows (on feed)", "B9": "12"},
        },
        # per-table monthly columns, keyed by column letter
        "cells": {
            "production": {
                "B": _months(), "C": 3_000_000, "D": 0.60,
                "G": 3_000_000, "H": 0.60, "AD": 1782, "P": 30, "L": 15000,
            },
            "manure_cat1": {
                "C": _months(), "D": 1100, "E": _CAL_DAYS, "F": _CAL_DAYS,
                "G": 15, "I": 0.9, "K": "Not Applicable",
            },
        },
        "expected_ci": -264.0,  # sanity reference for the dairy CNG pathway
    }


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
MODELS = [
    {
        "id": "ca_dairy",
        "market": CALIFORNIA,
        "feedstock": "Dairy / Swine Manure",
        "status": "active",
        "workbook": "t1_biomethane_ad_dairy_swine_manure_simplified_calculator_07012025_2.xlsm",
        "schema": "model.pkl",
        "default_scenario": dairy_default_scenario,
    },
    {
        "id": "ca_landfill",
        "market": CALIFORNIA,
        "feedstock": "Landfill Gas",
        "status": "coming_soon",
        "note": (
            "The landfill workbook in the repo is corrupted (truncated ZIP — no "
            "central directory). Re-upload a clean "
            "`t1_biomethane_NA_landfill_simplified_calculator_*.xlsm` and this "
            "feedstock will light up. Target default CI ≈ +50 gCO2e/MJ."
        ),
    },
    {
        "id": "cfr_placeholder",
        "market": CANADA,
        "feedstock": "—",
        "status": "coming_soon",
        "note": (
            "Canadian Clean Fuel Regulation support is scaffolded but not yet "
            "wired up. Provide the CFR model/credit methodology to integrate it."
        ),
    },
]


def feedstocks_for(market: str) -> list:
    return [m["feedstock"] for m in MODELS if m["market"] == market]


def get_model(market: str, feedstock: str):
    for m in MODELS:
        if m["market"] == market and m["feedstock"] == feedstock:
            return m
    return None
