"""Tests for the client-side chart rendering engine (spec §8.5)."""

from __future__ import annotations

import pytest

from sashiny import chart_backends, render_chart
from sashiny.charts import _frame, _resolve_spec


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


# A chart value as collected from SAS: upper-case names, a SAS label, a
# character column and a SAS missing value (None).
def _class_value() -> dict:
    return {
        "columns": [
            {"name": "Height", "type": "numeric", "label": "Height (in)", "format": ""},
            {"name": "Weight", "type": "numeric", "label": "", "format": ""},
            {"name": "Sex", "type": "character", "label": "", "format": ""},
        ],
        "rows": [
            [51.3, 50.5, "M"],
            [56.5, 84.0, "F"],
            [62.8, 102.5, "F"],
            [69.0, 112.5, "M"],
            [57.3, None, "F"],
            [63.5, 102.5, "M"],
        ],
        "total_rows": 6,
        "truncated": False,
        "formatted": False,
    }


KINDS = ["scatter", "line", "bar", "histogram", "box"]


def _spec(kind: str, **extra: object) -> dict:
    spec: dict = {"kind": kind, "x": "sex" if kind == "box" else "HEIGHT", "y": "weight"}
    spec.update(extra)
    return spec


def test_frame_is_typed_with_missing_as_nan() -> None:
    pd = pytest.importorskip("pandas")
    df = _frame(_class_value())
    assert list(df.columns) == ["Height", "Weight", "Sex"]
    assert pd.api.types.is_numeric_dtype(df["Height"])
    assert pd.isna(df["Weight"][4])
    assert list(df["Sex"]) == ["M", "F", "F", "M", "F", "M"]

    formatted = _class_value()
    formatted["formatted"] = True
    formatted["rows"] = [[str(c) for c in row] for row in formatted["rows"]]
    assert not pd.api.types.is_numeric_dtype(_frame(formatted)["Height"])


def test_spec_columns_resolve_case_insensitively() -> None:
    spec = _resolve_spec(
        _class_value(), {"kind": "scatter", "x": "HEIGHT", "y": "weight", "color": "sex"}
    )
    assert (spec["x"], spec["y"], spec["color"]) == ("Height", "Weight", "Sex")
    assert "y" not in _resolve_spec(
        _class_value(), {"kind": "histogram", "x": "height", "y": "weight"}
    )
    with pytest.raises(ValueError, match="unknown column 'nope'"):
        _resolve_spec(_class_value(), {"kind": "scatter", "x": "height", "facet": "nope"})


@pytest.mark.parametrize("kind", KINDS)
def test_plotnine_draws_every_kind(kind: str) -> None:
    pytest.importorskip("plotnine")
    pytest.importorskip("shiny")
    from sashiny.modules import _plot_to_png  # noqa: PLC0415 - needs the shiny extra

    plot = render_chart(_class_value(), _spec(kind, color="SEX", title="T"), backend="plotnine")
    assert len(_plot_to_png(plot)) > 1000


def test_plotnine_facets() -> None:
    pytest.importorskip("plotnine")
    pytest.importorskip("shiny")
    from sashiny.modules import _plot_to_png  # noqa: PLC0415 - needs the shiny extra

    plot = render_chart(_class_value(), _spec("scatter", facet="sex"), backend="plotnine")
    assert len(_plot_to_png(plot)) > 1000


@pytest.mark.parametrize("kind", KINDS)
def test_matplotlib_draws_every_kind(kind: str) -> None:
    pytest.importorskip("matplotlib")
    pytest.importorskip("shiny")
    from sashiny.modules import _plot_to_png  # noqa: PLC0415 - needs the shiny extra

    plot = render_chart(_class_value(), _spec(kind, title="T"), backend="matplotlib")
    assert len(_plot_to_png(plot)) > 1000


@pytest.mark.parametrize("kind", KINDS)
def test_plotly_builds_every_kind(kind: str) -> None:
    pytest.importorskip("plotly")
    fig = render_chart(_class_value(), _spec(kind, color="sex", title="T"), backend="plotly")
    assert fig.to_plotly_json()["data"]


def test_chart_tag_png_and_interactive() -> None:
    pytest.importorskip("shiny")
    from sashiny.modules import chart_tag  # noqa: PLC0415 - needs the shiny extra

    value = _class_value()
    if chart_backends()["matplotlib"]:
        tag = chart_tag(value, {"spec": _spec("scatter", backend="matplotlib")})
        assert "data:image/png;base64," in str(tag)
    if chart_backends()["plotnine"]:
        assert "data:image/png;base64," in str(chart_tag(value, {"spec": _spec("scatter")}))
    if chart_backends()["plotly"]:
        tag = chart_tag(value, {"spec": _spec("scatter", backend="plotly")})
        html = str(tag)
        assert "Plotly.newPlot" in html
        assert "data:image" not in html


def test_chart_tag_reports_the_reason() -> None:
    pytest.importorskip("shiny")
    from sashiny.modules import chart_tag  # noqa: PLC0415 - needs the shiny extra

    tag = chart_tag(
        _class_value(),
        {"spec": {"kind": "scatter", "x": "nope", "y": "weight", "backend": "matplotlib"}},
    )
    assert "Could not render this chart: unknown column" in str(tag)
