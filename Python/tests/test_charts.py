"""Tests for the client-side chart rendering engine (spec §8.5)."""

from __future__ import annotations

import pytest

from sashiny import chart_backends, render_chart


def _value() -> dict:
    return {
        "columns": [
            {"name": "x", "type": "numeric", "label": "X", "format": ""},
            {"name": "y", "type": "numeric", "label": "Y", "format": ""},
        ],
        "rows": [[1, 2], [2, 4], [3, 6]],
        "total_rows": 3,
        "truncated": False,
        "formatted": False,
    }


def test_chart_backends_reports_availability() -> None:
    backends = chart_backends()
    assert set(backends) == {"plotnine", "matplotlib", "plotly"}
    assert all(isinstance(v, bool) for v in backends.values())


def test_render_chart_requires_spec_or_callback() -> None:
    with pytest.raises(ValueError, match="no spec and no render"):
        render_chart(_value(), None, backend="plotnine")


def test_render_chart_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown chart backend"):
        render_chart(_value(), {"kind": "scatter", "x": "x", "y": "y"}, backend="nope")


def test_render_chart_callback_takes_precedence() -> None:
    called = []

    def cb(value: dict, spec: dict | None) -> str:
        called.append((value, spec))
        return "custom-plot"

    result = render_chart(_value(), {"kind": "scatter", "x": "x"}, backend="plotnine", render=cb)
    assert result == "custom-plot"
    assert len(called) == 1


def test_render_chart_unknown_column() -> None:
    with pytest.raises(ValueError, match="unknown column"):
        render_chart(_value(), {"kind": "scatter", "x": "nope", "y": "y"}, backend="matplotlib")


def test_render_chart_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown chart kind"):
        render_chart(_value(), {"kind": "pie", "x": "x"}, backend="matplotlib")


def test_render_chart_plotnine_when_installed() -> None:
    pytest.importorskip("plotnine")
    plot = render_chart(_value(), {"kind": "scatter", "x": "x", "y": "y"}, backend="plotnine")
    assert plot is not None


def test_render_chart_matplotlib_when_installed() -> None:
    pytest.importorskip("matplotlib")
    plot = render_chart(_value(), {"kind": "scatter", "x": "x", "y": "y"}, backend="matplotlib")
    assert plot is not None


def test_render_chart_plotly_when_installed() -> None:
    pytest.importorskip("plotly")
    plot = render_chart(_value(), {"kind": "scatter", "x": "x", "y": "y"}, backend="plotly")
    assert plot is not None
