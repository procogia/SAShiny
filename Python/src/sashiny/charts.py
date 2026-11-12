"""Client-side chart rendering for SAShiny.

A ``chart`` output carries the collected data (the same shape as a ``table``
value, spec §8.1) and is rendered by the Shiny module, not by SAS. This module
turns that data plus a declarative ``spec`` (spec §8.5) into a plot object for
one of three optional backends: plotnine, matplotlib or plotly.

The backends are optional dependencies. The core package imports without them;
each backend is imported lazily inside its renderer.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

__all__ = ["chart_backends", "render_chart"]

# A chart value is the same shape as a table value (spec §8.1).
ChartValue = dict[str, Any]
# A declarative chart spec (spec §8.5).
ChartSpec = dict[str, Any]
# A user-supplied render callback: (value, spec) -> plot object.
RenderCallback = Callable[[ChartValue, ChartSpec | None], Any]


def _column_index(value: ChartValue, name: str) -> int:
    """Return the 0-based index of a column, matched case-insensitively."""
    for i, col in enumerate(value.get("columns", [])):
        if col["name"].lower() == name.lower():
            return i
    raise ValueError(f"unknown column {name!r}")


def _series(value: ChartValue, name: str) -> list[Any]:
    idx = _column_index(value, name)
    return [row[idx] for row in value.get("rows", [])]


_KINDS = ("scatter", "line", "bar", "histogram", "box")
_FIELDS = ("x", "y", "color", "fill", "facet")


def _plot_series(value: ChartValue, name: str) -> list[Any]:
    """Column values for plotting: SAS missing numerics (``None``) become NaN."""
    idx = _column_index(value, name)
    if value["columns"][idx].get("type") == "numeric" and not value.get("formatted", False):
        return [float("nan") if v is None else v for v in _series(value, name)]
    return _series(value, name)


def _label(value: ChartValue, name: str) -> str:
    idx = _column_index(value, name)
    col = value["columns"][idx]
    label = col.get("label") or col["name"]
    return str(label)


def render_chart(
    value: ChartValue,
    spec: ChartSpec | None,
    backend: str = "plotnine",
    render: RenderCallback | None = None,
) -> Any:
    """Render a chart value to a plot object.

    Args:
        value: The collected chart value (spec §8.1 table shape).
        spec: The declarative chart spec (spec §8.5), or ``None``.
        backend: ``plotnine``, ``matplotlib`` or ``plotly``.
        render: An optional user callback ``(value, spec) -> object`` that
            takes precedence over the declarative spec.

    Returns:
        A plot object for the chosen backend: a plotnine ``ggplot``, a
        matplotlib ``Figure`` or a plotly ``Figure``.

    Raises:
        ValueError: If the backend or kind is unknown or a column is missing.

    """
    if render is not None:
        return render(value, spec)
    if spec is None:
        raise ValueError("chart has no spec and no render callback")
    if backend not in ("plotnine", "matplotlib", "plotly"):
        raise ValueError(f"unknown chart backend {backend!r}")
    resolved = _resolve_spec(value, spec)
    if backend == "plotnine":
        return _render_plotnine(value, resolved)
    if backend == "matplotlib":
        return _render_matplotlib(value, resolved)
    return _render_plotly(value, resolved)


def _resolve_spec(value: ChartValue, spec: ChartSpec) -> ChartSpec:
    """Validate a spec and resolve its column fields to the collected names.

    Column names in the spec are matched case-insensitively (spec §8.5), so
    ``x: height`` names the SAS column ``Height``. An unknown kind or column is
    an error, as is a missing ``y`` for every kind except ``histogram``.
    """
    kind = spec.get("kind")
    if kind not in _KINDS:
        raise ValueError(f"unknown chart kind {kind!r}")
    resolved = dict(spec)
    for field in _FIELDS:
        name = spec.get(field)
        if name is not None:
            resolved[field] = value["columns"][_column_index(value, name)]["name"]
    if kind == "histogram":
        resolved.pop("y", None)
    elif resolved.get("y") is None:
        raise ValueError(f"chart kind {kind!r} requires a 'y' column")
    return resolved


def _frame(value: ChartValue) -> Any:
    """Return a chart value as a ``pandas.DataFrame``.

    One column per collected column, in order and under its own name. Numeric
    columns of an unformatted value are numeric, with SAS missing (``None``) as
    ``NaN``; other columns keep their strings.
    """
    import pandas as pd  # noqa: PLC0415 - needed only by the data-frame backends

    columns = value.get("columns", [])
    rows = value.get("rows", [])
    numeric_ok = not value.get("formatted", False)
    data: dict[str, Any] = {}
    for i, col in enumerate(columns):
        cells = [row[i] for row in rows]
        if numeric_ok and col.get("type") == "numeric":
            data[col["name"]] = pd.to_numeric(pd.Series(cells, dtype=object), errors="coerce")
        else:
            data[col["name"]] = pd.Series(cells, dtype=object)
    return pd.DataFrame(data)


def chart_backends() -> dict[str, bool]:
    """Return which optional chart backends are importable."""
    out: dict[str, bool] = {}
    backends = (("plotnine", "plotnine"), ("matplotlib", "matplotlib"), ("plotly", "plotly"))
    for name, module in backends:
        try:
            __import__(module)
            out[name] = True
        except ImportError:
            out[name] = False
    return out


def _render_plotnine(value: ChartValue, spec: ChartSpec) -> Any:
    from plotnine import (  # noqa: PLC0415 - optional dependency
        aes,
        facet_wrap,
        geom_boxplot,
        geom_col,
        geom_histogram,
        geom_line,
        geom_point,
        ggplot,
        labs,
    )

    geoms = {
        "scatter": geom_point,
        "line": geom_line,
        "bar": geom_col,
        "histogram": lambda: geom_histogram(bins=30),
        "box": geom_boxplot,
    }
    mapping: dict[str, str] = {"x": str(spec["x"])}
    for field, aesthetic in (("y", "y"), ("color", "color"), ("fill", "fill")):
        if spec.get(field) is not None:
            mapping[aesthetic] = str(spec[field])

    plot = ggplot(_frame(value), aes(**mapping)) + geoms[spec["kind"]]()
    if spec.get("facet") is not None:
        plot += facet_wrap(spec["facet"])

    labels: dict[str, str] = {"x": str(spec.get("xlab", spec["x"]))}
    if spec.get("y") is not None or "ylab" in spec:
        labels["y"] = str(spec.get("ylab", spec.get("y", "")))
    for field in ("title", "subtitle"):
        if field in spec:
            labels[field] = str(spec[field])
    return plot + labs(**labels)


def _render_matplotlib(value: ChartValue, spec: ChartSpec) -> Any:
    from matplotlib.figure import Figure  # noqa: PLC0415 - optional dependency

    kind = spec["kind"]
    x = spec["x"]
    y = spec.get("y")
    xs = _plot_series(value, x)
    ys = _plot_series(value, y) if y is not None else None

    # A Figure created directly (not through pyplot) is not tracked by pyplot's
    # global figure manager, so a long-running Shiny server does not leak it.
    fig = Figure()
    ax = fig.subplots()
    if kind == "scatter":
        assert ys is not None  # noqa: S101 - scatter requires y (spec §8.5)
        ax.scatter(xs, ys)
    elif kind == "line":
        assert ys is not None  # noqa: S101 - line requires y (spec §8.5)
        ax.plot(xs, ys)
    elif kind == "bar":
        assert ys is not None  # noqa: S101 - bar requires y (spec §8.5)
        ax.bar([str(v) for v in xs], ys)
    elif kind == "histogram":
        ax.hist([v for v in xs if not _missing(v)])
    elif ys is None:
        ax.boxplot([v for v in xs if not _missing(v)])
    else:
        groups = sorted({str(v) for v in xs})
        ax.boxplot(
            [
                [b for a, b in zip(xs, ys, strict=True) if str(a) == g and not _missing(b)]
                for g in groups
            ]
        )
        ax.set_xticks(range(1, len(groups) + 1), groups)

    if "title" in spec:
        ax.set_title(spec["title"])
    ax.set_xlabel(str(spec.get("xlab", x)))
    if y is not None:
        ax.set_ylabel(str(spec.get("ylab", y)))
    if "subtitle" in spec:
        fig.text(0.5, 0.01, spec["subtitle"], ha="center")
    return fig


def _missing(v: Any) -> bool:
    """Whether a plotted value is missing (``None`` or NaN)."""
    return v is None or (isinstance(v, float) and math.isnan(v))


def _render_plotly(value: ChartValue, spec: ChartSpec) -> Any:
    import plotly.express as px  # noqa: PLC0415 - optional dependency

    functions = {
        "scatter": px.scatter,
        "line": px.line,
        "bar": px.bar,
        "histogram": px.histogram,
        "box": px.box,
    }
    kwargs: dict[str, Any] = {"x": spec["x"]}
    if spec.get("y") is not None:
        kwargs["y"] = spec["y"]
    if spec.get("color") is not None:
        kwargs["color"] = spec["color"]
    if spec.get("facet") is not None:
        kwargs["facet_col"] = spec["facet"]
    labels = {}
    if "xlab" in spec:
        labels[spec["x"]] = spec["xlab"]
    if "ylab" in spec and spec.get("y") is not None:
        labels[spec["y"]] = spec["ylab"]
    fig = functions[spec["kind"]](_frame(value), labels=labels, **kwargs)
    if "title" in spec:
        title = spec["title"]
        if "subtitle" in spec:
            title = f"{title}<br><sup>{spec['subtitle']}</sup>"
        fig.update_layout(title=title)
    return fig
