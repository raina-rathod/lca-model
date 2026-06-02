# CA-GREET4 Carbon-Intensity Explorer

A friendlier, interactive web front-end to CARB's official **CA-GREET4 Tier 1
Dairy/Swine Manure Biomethane** calculator
(`t1_biomethane_ad_dairy_swine_manure_simplified_calculator_07012025_2.xlsm`).

Toggle inputs, fill in monthly data in clean grids, and get live
**CNG / LNG / L-CNG carbon intensity** results with a contribution breakdown —
without wrestling the 7-sheet spreadsheet.

## How it works

The app never re-implements the spreadsheet's ~1,850 formulas. Instead it
recalculates the **actual `.xlsm`** through the
[`formulas`](https://pypi.org/project/formulas/) engine, so every number
matches CARB's official model exactly.

```
spreadsheet (.xlsm) ──build_model.py──▶ model.pkl  (input/output schema)
                                            │
                          streamlit_app.py ◀┘  renders friendly UI
                                            │
                              engine.py  ───┴──▶ formulas recalculates the .xlsm
```

- **`model.pkl`** — the extracted input schema (labels, units, dropdowns,
  defaults, table layouts). Built once from the spreadsheet.
- **Scenario `.pkl`** — your filled-in inputs can be saved/loaded from the
  sidebar so you can share or revisit a configuration.

## Run locally

```bash
cd app
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The first calculation loads + compiles the workbook (~6s, cached for the
session). Press **⚡ Calculate Carbon Intensity** after entering data.

## Deploy (shareable hosted app)

[Streamlit Community Cloud](https://share.streamlit.io):

1. Push this repo to GitHub.
2. New app → main file path = `app/streamlit_app.py`.
3. Streamlit installs `app/requirements.txt` automatically.

The source `.xlsm` must stay in the repo root (the engine loads it at runtime).

## Rebuilding the schema

If the source spreadsheet is updated, regenerate the schema:

```bash
python app/build_model.py
```

## Files

| File | Purpose |
|------|---------|
| `streamlit_app.py` | The interactive UI |
| `engine.py` | Loads & recalculates the `.xlsm` via `formulas` |
| `build_model.py` | Extracts the input/output schema → `model.pkl` |
| `model.pkl` | Serialized schema the app reads |
| `requirements.txt` | Python dependencies |

## Coverage & notes

- **Setup toggles:** digester type, electricity mix, pipeline distances,
  LNG/L-CNG transport, applicant info.
- **Monthly grids:** full Section-2 metered production table (31 columns) and up
  to 6 baseline livestock-category tables. "Show all data columns" in the
  sidebar reveals every metered column; off shows the common ones.
- Some fields shown in the spreadsheet (average temperature, number of reporting
  months, provisional-pathway flag) are **auto-derived** by the model from your
  monthly data, so they are not editable here — by design.
- A blank/partial scenario can produce a very high or zero CI; that's the real
  model's behaviour until offsetting baseline credits are entered.
