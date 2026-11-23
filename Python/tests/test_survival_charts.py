"""Tests for the survival example's forest-plot render callback (spec 8.5).

The callback lives in examples/survival/survival_charts.py, outside the package
and the cross-language fixtures. R/tests/testthat/test-survival-charts.R checks
the ggplot2 twin against the same value and the same expected layout, so the
two cannot drift apart unnoticed.
"""

from __future__ import annotations

import importlib.util
from types import ModuleType
from typing import Any

import pytest

from _repo import repo_root

PATH = repo_root() / "examples" / "survival" / "survival_charts.py"


def _module() -> ModuleType:
    if not PATH.is_file():
        pytest.skip("examples/survival is not available")
    spec = importlib.util.spec_from_file_location("survival_charts", PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _col(name: str, kind: str = "numeric", label: str = "") -> dict[str, str]:
    return {"name": name, "type": kind, "label": label, "format": ""}


# The shape of work.cox_estimates as collected (upper-case SAS names), with one
# row that must be dropped (no hazard ratio).
VALUE: dict[str, Any] = {
    "columns": [
        _col("TERM", "character"),
        _col("HAZARD_RATIO"),
        _col("HR_LOWER"),
        _col("HR_UPPER"),
        _col("HR_CI", "character", "HR (95% CI)"),
    ],
    "rows": [
        ["RX-101 vs Control", 0.82, 0.67, 0.99, "0.82 (0.67, 0.99)"],
        ["Age (per year)", 1.01, 1.00, 1.02, "1.01 (1.00, 1.02)"],
        ["Stage III vs I", None, None, None, None],
        ["Male vs Female", 1.2, 0.95, 1.5, "1.20 (0.95, 1.50)"],
    ],
    "formatted": False,
}
TERMS = ["RX-101 vs Control", "Age (per year)", "Male vs Female"]


def test_frame_keeps_model_order_and_drops_missing() -> None:
    df = _module()._forest_frame(VALUE)
    assert list(df["term"]) == TERMS
    assert list(df["pos"]) == [3, 2, 1]  # first term on top


def test_frame_fills_missing_ci_text() -> None:
    value = {
        "columns": [
            _col("term", "character"),
            _col("hazard_ratio"),
            _col("hr_lower"),
            _col("hr_upper"),
        ],
        "rows": [["a", 0.5, 0.4, 0.6]],
    }
    assert list(_module()._forest_frame(value)["hr_ci"]) == ["0.50"]


def test_frame_without_hazard_ratios_is_an_error() -> None:
    value = {**VALUE, "rows": [["a", None, None, None, None], ["b", 0, 0, 0, "0"]]}
    with pytest.raises(ValueError, match="no hazard ratios"):
        _module()._forest_frame(value)


def test_forest_chart_layout_and_render() -> None:
    pytest.importorskip("plotnine")
    plot = _module().forest_chart(VALUE, None)
    x = next(s for s in plot.scales if "x" in s.aesthetics)
    y = next(s for s in plot.scales if "y" in s.aesthetics)
    # lo = 0.67 / 1.15 and hi = 1.5 * 1.15: the breaks inside [lo, hi].
    assert list(x.breaks) == [0.75, 1, 1.5]
    assert list(y.labels) == TERMS
    geoms = [type(layer.geom).__name__ for layer in plot.layers]
    assert geoms == ["geom_vline", "geom_segment", "geom_point", "geom_text", "geom_text"]
    assert plot.layers[-1].geom.aes_params["label"] == "HR (95% CI)"
    figure = plot.draw()
    assert figure is not None
