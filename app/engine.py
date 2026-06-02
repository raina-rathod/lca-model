"""
engine.py — Thin wrapper around the `formulas` library that drives the actual
CA-GREET4 .xlsm so the app stays 100% faithful to CARB's official math.

Loading + compiling the workbook is slow (~6s) so the app caches one instance.
`compute()` is stateless: it overrides the given input cells and returns the
requested output cells.
"""
from __future__ import annotations

import logging
import os
import pickle
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("TQDM_DISABLE", "1")
logging.getLogger("formulas").setLevel(logging.ERROR)
logging.getLogger("schedula").setLevel(logging.ERROR)

import formulas  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent


def load_model() -> dict:
    """Load the input/output schema, building it from the workbook if missing."""
    pkl = APP_DIR / "model.pkl"
    if not pkl.exists():
        import build_model
        build_model.build()
    with open(pkl, "rb") as fh:
        return pickle.load(fh)


class GreetEngine:
    """Wraps a compiled ExcelModel and translates (sheet, cell) -> engine keys."""

    def __init__(self, workbook: str):
        self.path = ROOT / workbook
        self._fname = workbook.lower()
        self.xl = formulas.ExcelModel().loads(str(self.path)).finish()

    def key(self, sheet: str, cell: str) -> str:
        return f"'[{self._fname}]{sheet.upper()}'!{cell.upper()}"

    @staticmethod
    def _scalar(v):
        """Unwrap a formulas Ranges/array result to a plain Python value."""
        try:
            val = v.value
        except AttributeError:
            return v
        try:
            val = val[0, 0]
        except (TypeError, IndexError):
            try:
                val = val[0]
            except (TypeError, IndexError):
                pass
        return val

    def compute(self, inputs: dict, outputs: list) -> dict:
        """
        inputs  : {(sheet, cell): value, ...}
        outputs : [(sheet, cell), ...]
        returns : {(sheet, cell): value, ...}
        """
        in_keys = {self.key(s, c): v for (s, c), v in inputs.items()
                   if v is not None and v != ""}
        out_keys = [self.key(s, c) for (s, c) in outputs]
        sol = self.xl.calculate(inputs=in_keys or None, outputs=out_keys)

        result = {}
        for (s, c), k in zip(outputs, out_keys):
            try:
                result[(s, c)] = self._scalar(sol[k])
            except KeyError:
                result[(s, c)] = None
        return result
