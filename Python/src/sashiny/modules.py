"""Shiny modules for SAShiny (issue #9).

``program_ui`` / ``program_server`` generate a UI from a contract, convert the
Shiny input values to the contract's JSON form (spec §2.1), run the program on
an engine and render one card per contract output (spec §8.1 values). Either
half can be replaced with a custom function.
"""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from htmltools import HTMLDependency
from shiny import Inputs, Outputs, Session, module, reactive, req, ui
from shiny import render as shiny_render
from shiny.ui import TagChild

from .contract import Contract
from .engines import Engine
from .result import Result
from .upload import UploadFile

logger = logging.getLogger(__name__)

# Size of client-side chart images (spec §8.5): 8 x 6 inches at 150 dpi.
_CHART_INCHES = (8.0, 6.0)
_CHART_DPI = 150

__all__ = ["program_server", "program_ui", "shiny_values"]

SAMPLE_SUFFIX = "__sample"
_LOG_COLOURS = {"error": "#b42318", "warning": "#b54708", "note": "#175cd3", "text": "inherit"}


# --------------------------------------------------------------------------- helpers


def _choices(spec: dict[str, Any]) -> dict[str, str]:
    """Return static choices as ``{value: label}`` (empty for ``choices_from``)."""
    out: dict[str, str] = {}
    for c in spec.get("choices", []):
        if isinstance(c, str):
            out[c] = c
        else:
            out[c["value"]] = c.get("label", c["value"])
    return out


def _date(value: str | None, today: date) -> date | None:
    if value is None:
        return None
    return today if value == "today" else date.fromisoformat(value)


def _ordered_inputs(contract: Contract) -> list[tuple[str, dict[str, Any]]]:
    """Return inputs in ``ui.order`` first, then the rest in contract order."""
    inputs: dict[str, Any] = contract.data.get("inputs") or {}
    order = [i for i in (contract.data.get("ui") or {}).get("order", []) if i in inputs]
    rest = [i for i in inputs if i not in order]
    return [(i, inputs[i]) for i in order + rest]


def _help(spec: dict[str, Any]) -> TagChild | None:
    text = spec.get("help")
    return ui.tags.small(text, class_="form-text text-muted d-block mb-2") if text else None


def _input_ui(iid: str, spec: dict[str, Any], today: date) -> TagChild:  # noqa: PLR0911
    """Render the Shiny control for one contract input, with contract defaults."""
    kind = spec["type"]
    label = spec.get("label", iid)
    if kind == "numeric":
        return ui.input_numeric(
            iid,
            label,
            spec.get("default"),  # type: ignore[arg-type]  # None = empty box
            min=spec.get("min"),
            max=spec.get("max"),
            step=spec.get("step", 1 if spec.get("integer") else None),
        )
    if kind == "text":
        return ui.input_text(
            iid, label, spec.get("default", ""), placeholder=spec.get("placeholder")
        )
    if kind == "choice":
        choices = _choices(spec)
        selected = spec.get("default")
        if spec.get("widget") == "radio":
            return ui.input_radio_buttons(iid, label, choices=choices, selected=selected)
        return ui.input_select(iid, label, choices=choices, selected=selected)
    if kind == "multichoice":
        choices = _choices(spec)
        selected = spec.get("default", [])
        if spec.get("widget") == "checkbox":
            return ui.input_checkbox_group(iid, label, choices=choices, selected=selected)
        return ui.input_selectize(iid, label, choices=choices, selected=selected, multiple=True)
    if kind == "date":
        return ui.input_date(
            iid,
            label,
            value=_date(spec.get("default"), today),
            min=_date(spec.get("min"), today),
            max=_date(spec.get("max"), today),
        )
    if kind == "daterange":
        start, end = spec.get("default", [None, None])
        return ui.input_date_range(
            iid,
            label,
            start=_date(start, today),
            end=_date(end, today),
            min=_date(spec.get("min"), today),
            max=_date(spec.get("max"), today),
        )
    if kind == "dataset":
        accept = [f".{a}" for a in spec.get("accept", ["csv", "xlsx", "xpt", "sas7bdat"])]
        parts: list[TagChild] = [ui.input_file(iid, label, accept=accept)]
        if "sample" in spec:
            parts.append(ui.input_checkbox(f"{iid}{SAMPLE_SUFFIX}", "Use the sample file", True))
        return ui.div(*parts)
    raise ValueError(f"unknown input type {kind}")


def shiny_values(
    contract: Contract, read: Callable[[str], Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert Shiny input values to the contract's JSON form (spec §2.1).

    Args:
        contract: The loaded contract.
        read: Returns the current Shiny value of an input id (``None`` if unset).

    Returns:
        ``(values, uploads)``: ``values`` for non-dataset inputs; ``uploads``
        maps dataset inputs to an :class:`UploadFile` or ``True`` (sample).

    """
    values: dict[str, Any] = {}
    uploads: dict[str, Any] = {}
    for iid, spec in (contract.data.get("inputs") or {}).items():
        kind = spec["type"]
        raw = read(iid)
        if kind == "dataset":
            if raw:
                info = raw[0]
                uploads[iid] = UploadFile(path=Path(info["datapath"]), name=info["name"])
            elif "sample" in spec and read(f"{iid}{SAMPLE_SUFFIX}"):
                uploads[iid] = True
            continue
        if kind == "multichoice":
            values[iid] = list(raw or [])
        elif kind == "date":
            values[iid] = raw.isoformat() if isinstance(raw, date) else raw or None
        elif kind == "daterange":
            if raw and all(isinstance(d, date) for d in raw):
                values[iid] = [raw[0].isoformat(), raw[1].isoformat()]
            else:
                values[iid] = None
        elif kind == "choice":
            values[iid] = raw or None
        else:
            values[iid] = raw
    return values, uploads


def _status_text(result: Result) -> str:
    lines = [f"status: {result.status}", f"run_id: {result.run_id}"]
    meta = result.metadata
    if meta.get("sas_version"):
        lines.append(f"SAS: {meta['sas_version']}")
    if meta.get("recording") == "missing":
        lines.append("offline: no recording matches these inputs")
    elif meta.get("recording") == "replayed":
        lines.append(f"offline: replayed recording from {meta.get('recorded_at', '')}")
    for issue in meta.get("issues", []):
        where = issue.get("input") or ""
        lines.append(f"invalid input {issue['code']} {where} {issue.get('message', '')}".rstrip())
    if meta.get("notice"):
        lines.append(str(meta["notice"]))
    if meta.get("engine_error"):
        lines.append(f"engine error: {meta['engine_error']}")
    lines.extend(f"collect error: {e}" for e in meta.get("collect_errors", []))
    return "\n".join(lines)


def _error_tag(value: Any) -> TagChild | None:
    if isinstance(value, dict) and "error" in value:
        return ui.div(f"Could not collect this output: {value['error']}", class_="text-danger")
    return None


def table_tag(value: dict[str, Any]) -> TagChild:
    """Render a §8.1 table value as an HTML table."""
    head = ui.tags.tr(
        *[ui.tags.th(c["label"] or c["name"], title=c["name"]) for c in value["columns"]]
    )
    numeric = [c["type"] == "numeric" and not value["formatted"] for c in value["columns"]]
    body = [
        ui.tags.tr(
            *[
                ui.tags.td("" if v is None else str(v), class_="text-end" if n else None)
                for v, n in zip(row, numeric, strict=True)
            ]
        )
        for row in value["rows"]
    ]
    parts: list[TagChild] = [
        ui.div(
            ui.tags.table(
                ui.tags.thead(head),
                ui.tags.tbody(*body),
                class_="table table-sm table-striped",
            ),
            style="max-height: 480px; overflow: auto;",
        )
    ]
    if value["truncated"]:
        parts.append(ui.tags.small(f"Showing {len(value['rows'])} of {value['total_rows']} rows."))
    return ui.TagList(*parts)


def plot_tag(value: list[dict[str, str]]) -> TagChild:
    """Render a §8.1 plot value as images."""
    if not value:
        return ui.tags.small("No graphs were produced.")
    return ui.TagList(
        *[
            ui.img(src=f"data:{p['mime']};base64,{p['data']}", style="max-width: 100%;")
            for p in value
        ]
    )


def chart_tag(
    value: dict[str, Any],
    spec: dict[str, Any] | None,
    render: Callable[[dict[str, Any], dict[str, Any] | None], Any] | None = None,
) -> TagChild:
    """Render a §8.1 chart value with the client-side graphics engine.

    Follows the ``shiny.render.plot`` pattern: a render callback (or a
    declarative spec) produces a plot object. plotly figures are shown as
    interactive plotly charts; plotnine and matplotlib plots are serialised to
    a base64 PNG.
    """
    if not value or not value.get("rows"):
        return ui.tags.small("No data for this chart.")
    try:
        from .charts import render_chart  # noqa: PLC0415 - avoid import cycle

        chart_spec = (spec or {}).get("spec")
        backend = (chart_spec or {}).get("backend", "plotnine")
        plot = render_chart(value, chart_spec, backend=backend, render=render)
        if _is_plotly(plot):
            return _plotly_tag(plot)
        png = _plot_to_png(plot)
        return ui.img(src=f"data:image/png;base64,{png}", style="max-width: 100%;")
    except Exception as exc:
        logger.warning("could not render chart: %s", exc)
        return ui.tags.small(f"Could not render this chart: {exc}")


def _is_plotly(plot: Any) -> bool:
    """Whether a plot object is a plotly figure."""
    return type(plot).__module__.startswith("plotly.") and hasattr(plot, "to_plotly_json")


def _plotly_tag(fig: Any) -> TagChild:
    """Return an interactive plotly chart, using the plotly.js bundled with plotly.

    No static-image export (kaleido and a Chrome install) and no CDN are
    needed; Shiny serves plotly.js once as an HTML dependency.
    """
    import plotly  # noqa: PLC0415 - optional dependency
    from plotly.offline import get_plotlyjs_version  # noqa: PLC0415

    bundle = Path(plotly.__file__).parent / "package_data"
    dep = HTMLDependency(
        "plotly-js",
        get_plotlyjs_version(),
        source={"subdir": str(bundle)},
        script={"src": "plotly.min.js"},
    )
    html = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
    return ui.TagList(dep, ui.HTML(html))


def _plot_to_png(plot: Any) -> str:
    """Serialize a plotnine or matplotlib plot object to a base64 PNG.

    Charts are drawn at 8 x 6 inches and 150 dpi (1200 x 900 pixels), the same
    as the R module, so they stay sharp when a card scales them to its width.
    """
    buf = io.BytesIO()
    if hasattr(plot, "savefig"):
        plot.set_size_inches(_CHART_INCHES)
        plot.savefig(buf, format="png", dpi=_CHART_DPI)
    elif hasattr(plot, "save"):
        width, height = _CHART_INCHES
        plot.save(buf, format="png", width=width, height=height, dpi=_CHART_DPI, verbose=False)
    else:
        raise TypeError(f"cannot render a {type(plot).__name__} as a chart")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def html_tag(value: str) -> TagChild:
    """Render the ODS HTML document in a sandboxed frame (no scripts)."""
    if not value:
        return ui.tags.small("No HTML output.")
    return ui.tags.iframe(
        srcdoc=value,
        sandbox="",
        style="width: 100%; height: 600px; border: 0;",
        title="SAS output",
    )


def log_tag(value: list[dict[str, str]]) -> TagChild:
    """Render a §8.1 log value with lines coloured by level."""
    lines = [
        ui.tags.span(
            line["text"] + "\n",
            style=f"color: {_LOG_COLOURS.get(line['level'], 'inherit')};",
        )
        for line in value
    ]
    return ui.tags.pre(*lines, style="max-height: 480px; overflow: auto;")


_RENDERERS: dict[str, Callable[[Any], TagChild]] = {
    "table": table_tag,
    "plot": plot_tag,
    "html": html_tag,
    "log": log_tag,
}


def _output_card(oid: str, spec: dict[str, Any]) -> TagChild:
    label = spec.get("label", oid)
    if spec["type"] == "download":
        body: TagChild = ui.download_button(f"dl_{oid}", f"Download {label}")
    else:
        body = ui.output_ui(f"out_{oid}")
    return ui.card(ui.card_header(label), _help(spec), body, fill=False)


# --------------------------------------------------------------------------- module


@module.ui
def program_ui(
    contract: Contract,
    ui_override: Callable[[Contract], TagChild] | None = None,
    *,
    today: date | None = None,
) -> TagChild:
    """Generate the UI for a SAS program module.

    Args:
        contract: The loaded contract.
        ui_override: An optional callable ``(contract) -> TagChild`` that
            replaces the auto-generated UI.
        today: The date used to resolve ``"today"`` defaults (default: today).

    """
    if ui_override is not None:
        return ui_override(contract)
    today = today or date.today()
    controls: list[TagChild] = []
    for iid, spec in _ordered_inputs(contract):
        controls.extend([_input_ui(iid, spec, today), _help(spec)])
    settings = contract.data.get("ui") or {}
    controls.append(ui.input_action_button("run", settings.get("run_label", "Run")))
    outputs = [_output_card(oid, spec) for oid, spec in contract.data["outputs"].items()]
    status = ui.card(
        ui.card_header("Run"),
        ui.output_code("status"),
        ui.accordion(
            ui.accordion_panel("Full SAS log", ui.output_code("log")),
            open=False,
        ),
        fill=False,
    )
    if settings.get("layout") == "top":
        return ui.TagList(ui.card(*controls, fill=False), status, *outputs)
    return ui.TagList(ui.layout_sidebar(ui.sidebar(*controls), status, *outputs, fillable=False))


@module.server
def program_server(  # noqa: PLR0913, PLR0917 - Shiny module signature + override
    input: Inputs,
    output: Outputs,
    session: Session,
    contract: Contract,
    engine: Engine,
    server_override: Callable[..., Any] | None = None,
    chart_render: (dict[str, Callable[[dict[str, Any], dict[str, Any] | None], Any]] | None) = None,
) -> dict[str, Any]:
    """Serve a SAS program module (run the contract and render outputs).

    Args:
        input: Shiny inputs.
        output: Shiny outputs.
        session: Shiny session.
        contract: The loaded contract.
        engine: The engine to run on (mock, saspy or a :class:`sashiny.Pool`).
        server_override: An optional callable ``(input, output, session,
            contract, engine)`` that replaces the auto-generated server.
        chart_render: An optional mapping of chart render callbacks keyed by
            output id. Each is ``(value, spec) -> object`` returning a plot
            object (spec §8.5). Takes precedence over a declarative ``spec``.

    Returns:
        ``{"result", "status", "log"}`` reactive calcs for custom extensions.

    """
    if server_override is not None:
        return server_override(input, output, session, contract, engine)  # type: ignore[no-any-return]
    inputs: dict[str, Any] = contract.data.get("inputs") or {}
    settings = contract.data.get("ui") or {}
    choice_error = reactive.value("")

    @reactive.effect
    def _load_choices() -> None:
        """Fill ``choices_from`` inputs once at session start (spec §6.4)."""
        if not any("choices_from" in s for s in inputs.values()):
            return
        try:
            found = engine.choices(contract)
        except Exception as exc:  # shown in the status card
            choice_error.set(f"could not read choices: {exc}")
            return
        for iid, items in found.items():
            spec = inputs[iid]
            options = {c["value"]: c.get("label", c["value"]) for c in items}
            if spec["type"] == "choice" and spec.get("widget") == "radio":
                ui.update_radio_buttons(iid, choices=options, selected=spec.get("default"))
            elif spec["type"] == "choice":
                ui.update_select(iid, choices=options, selected=spec.get("default"))
            elif spec.get("widget") == "checkbox":
                ui.update_checkbox_group(iid, choices=options, selected=spec.get("default", []))
            else:
                ui.update_selectize(iid, choices=options, selected=spec.get("default", []))

    def _read(iid: str) -> Any:
        try:
            return input[iid]()
        except Exception:  # unknown or not-yet-initialised input
            return None

    @reactive.calc
    @reactive.event(input.run, ignore_none=not settings.get("auto_run", False))
    def result() -> Result:
        values, uploads = shiny_values(contract, _read)
        return engine.run(contract, values, uploads=uploads)

    @output(id="status")
    @shiny_render.code
    def _status() -> str:
        text = _status_text(result())
        return f"{text}\n{choice_error()}" if choice_error() else text

    @output(id="log")
    @shiny_render.code
    def _log() -> str:
        return result().log or "(no log)"

    for oid, spec in contract.data["outputs"].items():
        if spec["type"] == "download":
            _register_download(output, oid, result)
        else:
            _register_card(output, oid, spec, result, (chart_render or {}).get(oid))

    return {
        "result": result,
        "status": reactive.calc(lambda: result().status),
        "log": reactive.calc(lambda: result().log),
    }


def _register_card(
    output: Outputs,
    oid: str,
    spec: dict[str, Any],
    result: Callable[[], Result],
    chart_render: Callable[[dict[str, Any], dict[str, Any] | None], Any] | None = None,
) -> None:
    kind = spec["type"]

    @output(id=f"out_{oid}")
    @shiny_render.ui
    def _card() -> TagChild:
        res = result()
        if oid not in res.outputs:
            return ui.tags.small("No output for this run.")
        value = res.outputs[oid]
        if kind == "chart":
            return _error_tag(value) or chart_tag(value, spec, chart_render)
        return _error_tag(value) or _RENDERERS[kind](value)


def _register_download(output: Outputs, oid: str, result: Callable[[], Result]) -> None:
    def _value() -> dict[str, str]:
        value = result().outputs.get(oid)
        req(isinstance(value, dict) and "data" in value)
        assert isinstance(value, dict)  # noqa: S101 - narrowed by req()
        return value

    def _filename() -> str:
        return _value()["filename"]

    def _media_type() -> str:
        return _value()["mime"]

    def _download() -> Iterator[bytes]:
        yield base64.b64decode(_value()["data"])

    # Shiny 1.9 renamed render.download to render.download_button.
    renderer = getattr(shiny_render, "download_button", None)
    if renderer is None:  # pragma: no cover - Shiny < 1.9
        renderer = shiny_render.download
    output(id=f"dl_{oid}")(renderer(filename=_filename, media_type=_media_type)(_download))
