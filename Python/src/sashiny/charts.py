"""Client-side chart rendering for SAShiny.

A ``chart`` output carries the collected data (the same shape as a ``table``
value, spec §8.1) and is rendered by the Shiny module, not by SAS. This module
turns that data plus a declarative ``spec`` (spec §8.5) into a plot object for
one of three optional backends: plotnine, matplotlib or plotly.

The backends are optional dependencies. The core package imports without them;
each backend is imported lazily inside its renderer.
"""

from __future__ import annotations

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
        A plot object for the chosen backend.

    Raises:
        ValueError: If the backend is unknown or a required column is missing.

    """
    if render is not None:
        return render(value, spec)
    if spec is None:
        raise ValueError("chart has no spec and no render callback")
    if backend not in ("plotnine", "matplotlib", "plotly"):
        raise ValueError(f"unknown chart backend {backend!r}")
    _validate_spec(value, spec)
    if backend == "plotnine":
        return _render_plotnine(value, spec)
    if backend == "matplotlib":
        return _render_matplotlib(value, spec)
    return _render_plotly(value, spec)


def _validate_spec(value: ChartValue, spec: ChartSpec) -> None:
    """Validate the declarative spec against the collected columns."""
    kind = spec["kind"]
    if kind not in ("scatter", "line", "bar", "histogram", "box"):
        raise ValueError(f"unknown chart kind {kind!r}")
    _column_index(value, spec["x"])
    for field in ("y", "color", "fill", "facet"):
        if field in spec and spec[field] is not None:
            _column_index(value, spec[field])


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


def _render_plotnine(value: ChartValue, spec: ChartSpec) -> Any:  # noqa: PLR0912 - chart-kind dispatch
    from plotnine import (  # noqa: PLC0415 - optional dependency
        aes,
        geom_bar,
        geom_boxplot,
        geom_histogram,
        geom_line,
        geom_point,
        ggplot,
        labs,
    )

    kind = spec["kind"]
    x = spec["x"]
    y = spec.get("y")
    color = spec.get("color")
    fill = spec.get("fill")
    facet = spec.get("facet")

    mapping: dict[str, str] = {"x": x}
    if y is not None:
        mapping["y"] = y
    if color is not None:
        mapping["color"] = color
    if fill is not None:
        mapping["fill"] = fill

    plot = ggplot(value, aes(**mapping))
    if kind == "scatter":
        plot += geom_point()
    elif kind == "line":
        plot += geom_line()
    elif kind == "bar":
        plot += geom_bar(stat="identity")
    elif kind == "histogram":
        plot += geom_histogram()
    elif kind == "box":
        plot += geom_boxplot()
    else:
        raise ValueError(f"unknown chart kind {kind!r}")

    if facet is not None:
        from plotnine import facet_wrap  # noqa: PLC0415

        plot += facet_wrap(f"~{facet}")

    labels: dict[str, str] = {}
    if "title" in spec:
        labels["title"] = spec["title"]
    if "subtitle" in spec:
        labels["subtitle"] = spec["subtitle"]
    if "xlab" in spec:
        labels["x"] = spec["xlab"]
    if "ylab" in spec:
        labels["y"] = spec["ylab"]
    if labels:
        plot += labs(**labels)
    return plot


def _render_matplotlib(value: ChartValue, spec: ChartSpec) -> Any:
    import matplotlib.pyplot as plt  # noqa: PLC0415 - optional dependency

    kind = spec["kind"]
    x = spec["x"]
    y = spec.get("y")

    xs = _series(value, x)
    ys = _series(value, y) if y is not None else None

    fig, ax = plt.subplots()
    if kind == "scatter":
        ax.scatter(xs, ys)
    elif kind == "line":
        ax.plot(xs, ys)
    elif kind == "bar":
        ax.bar(xs, ys)
    elif kind == "histogram":
        ax.hist(xs)
    elif kind == "box":
        ax.boxplot(ys)
    else:
        raise ValueError(f"unknown chart kind {kind!r}")

    if "title" in spec:
        ax.set_title(spec["title"])
    ax.set_xlabel(spec.get("xlab", _label(value, x)))
    if y is not None:
        ax.set_ylabel(spec.get("ylab", _label(value, y)))
    return fig


def _render_plotly(value: ChartValue, spec: ChartSpec) -> Any:
    import plotly.express as px  # noqa: PLC0415 - optional dependency

    kind = spec["kind"]
    x = spec["x"]
    y = spec.get("y")
    color = spec.get("color")

    if kind == "scatter":
        fig = px.scatter(value, x=x, y=y, color=color)
    elif kind == "line":
        fig = px.line(value, x=x, y=y, color=color)
    elif kind == "bar":
        fig = px.bar(value, x=x, y=y, color=color)
    elif kind == "histogram":
        fig = px.histogram(value, x=x, color=color)
    elif kind == "box":
        fig = px.box(value, x=x, y=y, color=color)
    else:
        raise ValueError(f"unknown chart kind {kind!r}")

    if "title" in spec:
        fig.update_layout(title=spec["title"])
    return fig
