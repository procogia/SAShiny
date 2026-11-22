"""Shiny modules for SAShiny (issue #9).

``program_ui`` / ``program_server`` generate a UI from a contract, convert the
Shiny input values to the contract's JSON form (spec §2.1), run the program on
an engine and render one card per contract output (spec §8.1 values). Either
half can be replaced with a custom function.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import io
import logging
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from htmltools import HTMLDependency
from shiny import Inputs, Outputs, Session, module, reactive, req, ui
from shiny import render as shiny_render
from shiny.module import resolve_id
from shiny.ui import TagChild

from . import choices_cache, result_cache
from .collect import is_paired, paired_chart_spec
from .contract import Contract
from .engines import Engine
from .engines.base import check_engine
from .errors import ValuesError
from .result import Result
from .upload import FrameUpload, UploadError, UploadFile

logger = logging.getLogger(__name__)

# Size of client-side chart images (spec §8.5): 8 x 6 inches at 150 dpi.
_CHART_INCHES = (8.0, 6.0)
_CHART_DPI = 150

__all__ = ["program_server", "program_ui", "shiny_values"]

SAMPLE_SUFFIX = "__sample"
# Output id of the module-wide view toggle (spec §8.6). Output ids start with a
# letter, so `out_` + `_view` never collides with an output card.
_VIEW_TOGGLE_ID = "out__view"
_VIEW_GROUP_ID = "views"
_HIDE_INPUTS_ID = "hide__inputs"
_HIDE_INPUTS_ID = "hide__inputs"
_VIEWS = ("sas", "sashiny")
_VIEW_LABELS = {"sas": "SAS graph", "sashiny": "SAShiny chart"}
_GROUP_LABELS = {"sas": "SAS graphs", "sashiny": "SAShiny charts"}
_WWW = Path(__file__).resolve().parent / "www"
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
    raise ValuesError(f"unknown input type {kind}")


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
                upload = UploadFile(path=Path(info["datapath"]), name=info["name"])
                # Enforce max_size_mb when the file is received (spec §7), not
                # only later in read_upload, so an oversized upload is refused
                # before any SAS work (issue #54). Use the client-declared size
                # from uploadInit, which is known before the file is written.
                _check_upload_size(upload, spec, declared_size=info.get("size"))
                uploads[iid] = upload
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


def merge_values(
    contract: Contract, values: dict[str, Any], external: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge external values over UI values (spec §6.10).

    Supplied ids replace the UI value; a supplied ``None`` makes the input
    absent. Dataset ids are left to :func:`merge_uploads`. :class:`datetime.date` values (and tuples
    of them for a ``daterange``) become ISO strings.

    Args:
        contract: The loaded contract.
        values: The UI values from :func:`shiny_values`.
        external: The dict returned by ``values()``, or ``None``.

    Returns:
        A new dict of merged values.

    """
    if external is None:
        return dict(values)
    if not isinstance(external, dict):
        raise ValuesError("values() must return a dict of input values")
    inputs: dict[str, Any] = contract.data.get("inputs") or {}
    merged = dict(values)
    for iid, raw in external.items():
        kind = (inputs.get(iid) or {}).get("type")
        if kind == "dataset":
            continue
        if raw is None:
            merged.pop(iid, None)
        elif isinstance(raw, date):
            merged[iid] = raw.isoformat()
        elif isinstance(raw, (list, tuple)):
            merged[iid] = [v.isoformat() if isinstance(v, date) else v for v in raw]
        else:
            merged[iid] = raw
    return merged


def merge_uploads(
    contract: Contract, uploads: dict[str, Any], external: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge external dataset values over the UI uploads (spec §6.10).

    A value supplied for a dataset id replaces its upload: it is wrapped in a
    :class:`~sashiny.upload.FrameUpload` and written as canonical CSV when the
    run resolves its uploads (spec §7.1), where anything that is not a
    DataFrame, or cannot be written, is reported as V014. ``None`` removes the
    upload.

    Args:
        contract: The loaded contract.
        uploads: The UI uploads from :func:`shiny_values`.
        external: The dict returned by ``values()``, or ``None``.

    Returns:
        A new dict of merged uploads.

    """
    merged = dict(uploads)
    if not isinstance(external, dict):
        return merged
    inputs: dict[str, Any] = contract.data.get("inputs") or {}
    for iid, raw in external.items():
        if (inputs.get(iid) or {}).get("type") != "dataset":
            continue
        if raw is None:
            merged.pop(iid, None)
        else:
            merged[iid] = FrameUpload(frame=raw, input_id=iid)
    return merged


def _hide_inputs_tag(ids: list[str], ns: Callable[[str], str]) -> TagChild:
    """Return a ``<style>`` tag hiding the controls of ``ids`` (spec §6.10)."""
    if not ids:
        return None
    rules = "\n".join(f"#{ns(f'in__{iid}')} {{ display: none; }}" for iid in ids)
    return ui.tags.style(rules)


def _check_upload_size(
    upload: UploadFile, spec: dict[str, Any], declared_size: int | None = None
) -> None:
    """Reject an upload over ``max_size_mb`` when it is received (spec §7).

    ``declared_size`` is the byte size the client reported in its ``uploadInit``
    message (Shiny's ``FileInfo["size"]``); it is known before the file is
    written, so it is preferred over re-stat'ing the file. A missing file is
    left to ``read_upload``'s ``_check_file`` (which reports ``file not found``
    as V014).
    """
    if declared_size is None:
        if not upload.path.is_file():
            return
        declared_size = upload.path.stat().st_size
    limit = spec.get("max_size_mb", 50)
    size_mb = declared_size / (1024 * 1024)
    if size_mb > limit:
        raise UploadError(f"{upload.name} is {size_mb:.1f} MB (limit {limit} MB)")


def _status_text(result: Result) -> str:
    lines = [f"status: {result.status}", f"run_id: {result.run_id}"]
    meta = result.metadata
    if meta.get("sas_version"):
        lines.append(f"SAS: {meta['sas_version']}")
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


def _toggle_dependency() -> HTMLDependency:
    """Return the client-side view toggle script and styles (spec §8.6)."""
    from . import __version__  # noqa: PLC0415 - avoid import cycle

    return HTMLDependency(
        "sashiny-toggle",
        __version__,
        source={"subdir": str(_WWW)},
        script={"src": "sashiny-toggle.js"},
        stylesheet={"href": "sashiny-toggle.css"},
    )


def _toggle_buttons(labels: dict[str, str], view: str | None, **attrs: str) -> TagChild:
    """Return a pair of `aria-pressed` buttons that switch views in the browser."""
    buttons = [
        ui.tags.button(
            labels[v],
            type="button",
            class_="active" if v == view else None,
            aria_pressed="true" if v == view else "false",
            data_sashiny_set=v,
        )
        for v in ("sashiny", "sas")
    ]
    return ui.div(*buttons, class_="sashiny-toggle", role="group", **attrs)


def paired_tag(  # noqa: PLR0913 - value, spec and the §8.6 view settings
    value: dict[str, Any],
    spec: dict[str, Any],
    *,
    output_id: str,
    group: str,
    view: str = "sashiny",
    toggle: bool = True,
    render: Callable[[dict[str, Any], dict[str, Any] | None], Any] | None = None,
) -> TagChild:
    """Render a paired output: the SAS graph and the SAShiny chart (spec §8.6).

    Both views are rendered once; the browser switches between them. With
    ``toggle=False`` only the default ``view`` is rendered.

    Args:
        value: The §8.1 paired value ``{"sas", "sashiny"}``.
        spec: The output's contract spec.
        output_id: The output id (keys the remembered view).
        group: The module's toggle group id.
        view: The default view, ``"sashiny"`` or ``"sas"``.
        toggle: Whether to show the per-card toggle.
        render: An optional chart render callback (spec §8.5).

    Returns:
        The card body.

    """
    chart_spec = paired_chart_spec(spec)

    def _pane(part: str) -> TagChild:
        part_value = value.get(part) if isinstance(value, dict) else None
        if part_value is None:
            return ui.tags.small("No output for this run.")
        error = _error_tag(part_value)
        if error is not None:
            return error
        if part == "sas":
            return plot_tag(part_value)
        return chart_tag(part_value, chart_spec, render)

    if not toggle:
        return _pane(view)
    return ui.div(
        _toggle_dependency(),
        _toggle_buttons(_VIEW_LABELS, view, data_sashiny_card_toggle="", aria_label="Chart view"),
        *[
            ui.div(_pane(v), data_sashiny_pane=v, hidden=None if v == view else "")
            for v in ("sashiny", "sas")
        ],
        class_="sashiny-paired",
        data_sashiny_paired="",
        data_sashiny_group=group,
        data_sashiny_output=output_id,
        data_sashiny_default=view,
        data_sashiny_view=view,
    )


def view_toggle_tag(group: str, view: str | None) -> TagChild:
    """Render the module-wide SAS / SAShiny view toggle (spec §8.6).

    Args:
        group: The module's toggle group id.
        view: The default view of every paired card, or ``None`` when they differ.

    Returns:
        The toggle.

    """
    attrs: dict[str, str] = {"data_sashiny_group": group}
    if view is not None:
        attrs["data_sashiny_default"] = view
    return ui.div(
        _toggle_dependency(),
        ui.tags.span("Show:", class_="small"),
        _toggle_buttons(_GROUP_LABELS, view, aria_label="Chart view for all outputs"),
        class_="sashiny-group-toggle",
        data_sashiny_group_toggle="",
        **attrs,
    )


def _chart_views(contract: Contract, chart_view: str | dict[str, str]) -> dict[str, str]:
    """Return the default view of each paired output, validating `chart_view` (spec §8.6)."""
    paired = [oid for oid, s in contract.data["outputs"].items() if is_paired(s)]
    if isinstance(chart_view, str):
        if chart_view not in _VIEWS:
            raise ValuesError(f"chart_view must be 'sashiny' or 'sas', not {chart_view!r}")
        return dict.fromkeys(paired, chart_view)
    if not isinstance(chart_view, dict):
        raise TypeError("chart_view must be 'sashiny', 'sas' or a dict of output id to view")
    unknown = [oid for oid in chart_view if oid not in paired]
    if unknown:
        raise ValuesError(f"chart_view names outputs that are not paired: {', '.join(unknown)}")
    bad = [oid for oid, v in chart_view.items() if v not in _VIEWS]
    if bad:
        raise ValuesError(f"chart_view must map outputs to 'sashiny' or 'sas': {', '.join(bad)}")
    return {oid: chart_view.get(oid, "sashiny") for oid in paired}


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
        # The download button is rendered conditionally (only once a result with
        # this output exists), so a disabled placeholder is shown before the first
        # run and after a failed run (issue #51).
        body: TagChild = ui.output_ui(f"dl_btn_{oid}")
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
        # The wrapper id lets the server hide controls driven by `values` (spec §6.10).
        controls.append(
            ui.div(_input_ui(iid, spec, today), _help(spec), id=resolve_id(f"in__{iid}"))
        )
    controls.append(ui.output_ui(_HIDE_INPUTS_ID))
    settings = contract.data.get("ui") or {}
    # A task button shows a busy state and is disabled until the run finishes.
    controls.append(
        ui.input_task_button("run", settings.get("run_label", "Run"), label_busy="Running...")
    )
    outputs = [_output_card(oid, spec) for oid, spec in contract.data["outputs"].items()]
    if any(is_paired(spec) for spec in contract.data["outputs"].values()):
        # Module-wide SAS / SAShiny toggle (spec §8.6); empty when the server turns it off.
        outputs.insert(0, ui.output_ui(_VIEW_TOGGLE_ID))
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
def program_server(  # noqa: PLR0913, PLR0915, PLR0917 - Shiny module: one reactive graph
    input: Inputs,
    output: Outputs,
    session: Session,
    contract: Contract,
    engine: Engine,
    server_override: Callable[..., Any] | None = None,
    chart_render: (dict[str, Callable[[dict[str, Any], dict[str, Any] | None], Any]] | None) = None,
    *,
    chart_view: str | dict[str, str] = "sashiny",
    chart_toggle: bool = True,
    values: Callable[[], dict[str, Any] | None] | None = None,
    hide_inputs: bool = False,
    debounce_ms: float = 500,
) -> dict[str, Any]:
    """Serve a SAS program module (run the contract and render outputs).

    Args:
        input: Shiny inputs.
        output: Shiny outputs.
        session: Shiny session.
        contract: The loaded contract.
        engine: A :func:`sashiny.connect` engine or a :class:`sashiny.Pool`.
        server_override: An optional callable `(input, output, session,
            contract, engine)` that replaces the auto-generated server.
        chart_render: An optional mapping of chart render callbacks keyed by
            output id. Each is `(value, spec) -> object` returning a plot
            object (spec §8.5). Takes precedence over a declarative `spec`.
        chart_view: The default view of paired outputs (spec §8.6):
            `"sashiny"` (default) for the SAShiny chart, `"sas"` for the
            original SAS graph, or a dict of paired output id to view.
        chart_toggle: Whether to show the SAS / SAShiny toggles (default
            `True`). With `False` each paired card shows only its default view.
        values: An optional reactive returning a dict of input values in the
            §2.1 JSON form (spec §6.10). Supplied ids replace the UI value and
            are validated exactly like UI values; other ids come from the UI.
            For a dataset input, supply a pandas DataFrame: it replaces the
            upload and is written as CSV (spec §7.1). With `ui.auto_run: true`,
            a change starts a run after `debounce_ms`.
        hide_inputs: Whether to hide the controls of the ids supplied by
            `values()` (default `False`).
        debounce_ms: Debounce interval in milliseconds for auto-runs driven by
            `values()` (default 500).

    Returns:
        `{"result", "status", "log"}` reactive calcs for custom extensions.

    """
    check_engine(engine)
    if values is not None and not callable(values):
        raise ValuesError("values must be a reactive (or callable) returning a dict")
    if debounce_ms < 0:
        raise ValuesError("debounce_ms must be non-negative")
    views = _chart_views(contract, chart_view)
    if server_override is not None:
        return server_override(input, output, session, contract, engine)  # type: ignore[no-any-return]
    inputs: dict[str, Any] = contract.data.get("inputs") or {}
    settings = contract.data.get("ui") or {}
    choice_error = reactive.value("")

    def _apply_choices(found: dict[str, list[dict[str, str]]]) -> None:
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

    @reactive.extended_task
    async def choices_task() -> dict[str, list[dict[str, str]]]:
        # Load choices off the event loop, once per app and contract (spec 6.4).
        return await asyncio.to_thread(choices_cache.load, engine, contract)

    @reactive.effect
    def _load_choices() -> None:
        """Fill `choices_from` inputs from the app cache, or load them (spec §6.4)."""
        if not choices_cache.has_choices_from(contract):
            return
        with reactive.isolate():
            hit = choices_cache.cached(engine, contract)
            if hit is not None:
                _apply_choices(hit)
                return
            placeholder = {"": "Loading choices\u2026"}
            for iid, spec in inputs.items():
                if "choices_from" not in spec:
                    continue
                if spec["type"] == "choice" and spec.get("widget") == "radio":
                    ui.update_radio_buttons(iid, choices=placeholder)
                elif spec["type"] == "choice":
                    ui.update_select(iid, choices=placeholder)
                elif spec.get("widget") == "checkbox":
                    ui.update_checkbox_group(iid, choices=placeholder)
                else:
                    ui.update_selectize(iid, choices=placeholder)
            choices_task()

    @reactive.effect
    def _choices_done() -> None:
        status = choices_task.status()
        if status == "success":
            choice_error.set("")
            _apply_choices(choices_task.result())
        elif status == "error":
            choice_error.set(f"could not read choices: {choices_task.error()}")

    def _read(iid: str) -> Any:
        try:
            return input[iid]()
        except Exception:  # unknown or not-yet-initialised input
            return None

    # Keep the Run task button busy and disabled until the run finishes.
    @ui.bind_task_button(button_id="run")
    @reactive.extended_task
    async def run_task(snapshot: tuple[dict[str, Any], dict[str, Any]] | Result) -> Result:
        # Run the engine off the event loop so a slow SAS run never blocks other
        # sessions (spec §5.1 / PLAN.md). Inputs are snapshotted in _trigger.
        run_contract = contract
        if choices_cache.has_choices_from(contract):
            hit = choices_cache.cached(engine, contract)
            if hit is not None:
                run_contract = dataclasses.replace(contract, cached_choices=hit)
        return await _run_snapshot(engine, run_contract, snapshot)

    def _start_run() -> None:
        external = values() if values is not None else None
        run_task(_snapshot_inputs(contract, _read, external))

    @reactive.effect
    @reactive.event(input.run, ignore_none=not settings.get("auto_run", False))
    def _trigger() -> None:
        # Coalesce: ignore a Run click while a run is already in flight, so a
        # burst of clicks does not queue one engine run per click (issue #49).
        if run_task.status() == "running":
            return
        _start_run()

    if values is not None:
        _external_runs(values, settings, run_task, _start_run, debounce_ms / 1000)

        @output(id=_HIDE_INPUTS_ID)
        @shiny_render.ui
        def _hide_inputs() -> TagChild:
            if not hide_inputs:
                return None
            supplied = [iid for iid in (values() or {}) if iid in inputs]
            return _hide_inputs_tag(supplied, session.ns)

    # Cancel any in-flight or queued run when the session ends, so a slow SAS
    # run does not keep executing after the browser disconnects (issue #50).
    session.on_ended(run_task.cancel)

    @reactive.calc
    def running() -> bool:
        """Return whether a run is in flight (used to show progress, not a stuck card)."""
        return run_task.status() == "running"

    @reactive.calc
    def result() -> Result | None:
        """Return the completed :class:`Result`, or ``None`` while running/errored."""
        if run_task.status() == "success":
            return run_task.result()
        return None

    @output(id="status")
    @shiny_render.code
    def _status() -> str:
        status = run_task.status()
        if status == "running":
            return "running..."
        if status == "error":
            return f"engine error: {run_task.error()}"
        res = result()
        if res is None:
            # Before the first run, surface a choices_from load failure so the
            # user is not left with empty dropdowns and no explanation (#68).
            return choice_error() or "idle"
        text = _status_text(res)
        return f"{text}\n{choice_error()}" if choice_error() else text

    @output(id="log")
    @shiny_render.code
    def _log() -> str:
        res = result()
        if res is None:
            return "(no log)"
        return res.log or "(no log)"

    _register_outputs(
        output,
        contract,
        result,
        running,
        chart_render or {},
        views,
        group=session.ns(_VIEW_GROUP_ID),
        chart_toggle=chart_toggle,
    )

    return {
        "result": result,
        "status": reactive.calc(lambda: (result() or _empty_result()).status),
        "log": reactive.calc(lambda: (result() or _empty_result()).log),
    }


def _register_outputs(  # noqa: PLR0913, PLR0917 - the module's reactive pieces and §8.6 settings
    output: Outputs,
    contract: Contract,
    result: Callable[[], Result | None],
    running: Callable[[], bool],
    chart_render: dict[str, Callable[[dict[str, Any], dict[str, Any] | None], Any]],
    views: dict[str, str],
    *,
    group: str,
    chart_toggle: bool,
) -> None:
    """Register one card (or download) per output and the module-wide view toggle."""
    for oid, spec in contract.data["outputs"].items():
        if spec["type"] == "download":
            _register_download(output, oid, spec, result)
            continue
        pairing = (
            _Pairing(group=group, view=views[oid], toggle=chart_toggle) if oid in views else None
        )
        _register_card(output, oid, spec, result, running, chart_render.get(oid), pairing)

    if not views:
        return
    defaults = set(views.values())
    group_view = next(iter(defaults)) if len(defaults) == 1 else None

    @output(id=_VIEW_TOGGLE_ID)
    @shiny_render.ui
    def _view_toggle() -> TagChild:
        return view_toggle_tag(group, group_view) if chart_toggle else None


def _external_runs(
    values: Callable[[], dict[str, Any] | None],
    settings: dict[str, Any],
    run_task: Any,
    start_run: Callable[[], None],
    debounce: float,
) -> None:
    """Start debounced runs when ``values()`` changes and ``ui.auto_run`` is on (spec §6.10)."""
    if not settings.get("auto_run", False):
        return
    changed_at: reactive.Value[float | None] = reactive.value(None)
    state = {"first": True, "pending": False}

    @reactive.effect
    def _watch() -> None:
        values()
        if state["first"]:
            # The auto_run run at session start already uses the first value.
            state["first"] = False
            return
        with reactive.isolate():
            changed_at.set(time.monotonic())

    @reactive.effect
    def _settle() -> None:
        at = changed_at()
        if at is None:
            return
        remaining = at + debounce - time.monotonic()
        if remaining > 0:
            reactive.invalidate_later(remaining)
            return
        with reactive.isolate():
            changed_at.set(None)
            if run_task.status() == "running":
                state["pending"] = True
            else:
                start_run()

    @reactive.effect
    def _after_run() -> None:
        status = run_task.status()
        if status in {"success", "error"} and state["pending"]:
            state["pending"] = False
            with reactive.isolate():
                start_run()


def _snapshot_inputs(
    contract: Contract, read: Callable[[str], Any], external: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any]] | Result:
    """Return merged :func:`shiny_values`, or a V014 error :class:`Result` for a refused upload."""
    try:
        values, uploads = shiny_values(contract, read)
    except UploadError as exc:
        return _upload_error_result(exc)
    return merge_values(contract, values, external), merge_uploads(contract, uploads, external)


async def _run_snapshot(
    engine: Engine, contract: Contract, snapshot: tuple[dict[str, Any], dict[str, Any]] | Result
) -> Result:
    """Run a snapshot of the inputs on ``engine`` in a worker thread.

    A run refused before reaching the engine (an upload over ``max_size_mb``,
    spec §7) is already a V014 error :class:`Result` and is returned as is, so
    it is shown in the status card like R (issue #101).
    """
    if isinstance(snapshot, Result):
        return snapshot
    values, uploads = snapshot
    return await asyncio.to_thread(
        result_cache.cached_run,
        engine,
        contract,
        values,
        lambda: engine.run(contract, values, uploads=uploads),
        uploads=uploads,
    )


def _upload_error_result(exc: UploadError) -> Result:
    """Return the V014 error :class:`Result` for an upload refused on receipt (spec §7)."""
    result = Result.new(str(uuid.uuid4()), "error")
    result.metadata["issues"] = [{"code": "V014", "message": str(exc)}]
    return result


def _empty_result() -> Result:
    """Return a placeholder result for a run that is in progress or errored."""
    return Result.new("", "idle")


@dataclass(frozen=True)
class _Pairing:
    """View settings of one paired output card (spec §8.6)."""

    group: str
    view: str
    toggle: bool


def _register_card(  # noqa: PLR0913, PLR0917 - Shiny render callback + running flag
    output: Outputs,
    oid: str,
    spec: dict[str, Any],
    result: Callable[[], Result | None],
    running: Callable[[], bool],
    chart_render: Callable[[dict[str, Any], dict[str, Any] | None], Any] | None = None,
    pairing: _Pairing | None = None,
) -> None:
    kind = spec["type"]

    @output(id=f"out_{oid}")
    @shiny_render.ui
    def _card() -> TagChild:
        if running():
            return ui.tags.small("Running...")
        res = result()
        if res is None:
            # Not running and no result: before the first run, or after a failed
            # run. Do not leave a stuck "Running..." spinner (issue #52).
            return ui.tags.small("No output for this run.")
        if oid not in res.outputs:
            return ui.tags.small("No output for this run.")
        value = res.outputs[oid]
        if pairing is not None:
            return _error_tag(value) or paired_tag(
                value,
                spec,
                output_id=oid,
                group=pairing.group,
                view=pairing.view,
                toggle=pairing.toggle,
                render=chart_render,
            )
        if kind == "chart":
            return _error_tag(value) or chart_tag(value, spec, chart_render)
        return _error_tag(value) or _RENDERERS[kind](value)


def _register_download(
    output: Outputs, oid: str, spec: dict[str, Any], result: Callable[[], Result | None]
) -> None:
    def _value() -> dict[str, str]:
        # `req()` raises a SilentException when there is no result or no download
        # value yet, which Shiny turns into an HTTP 404 (matching R's `shiny::req`,
        # issue #51) instead of an HTTP 500 + traceback.
        res = result()
        req(res is not None)
        assert res is not None  # noqa: S101 - req() raises on falsy; narrow for mypy
        value = res.outputs.get(oid)
        req(isinstance(value, dict) and "data" in value)
        assert isinstance(value, dict)  # noqa: S101 - req() raises on falsy; narrow for mypy
        return value

    def _filename() -> str:
        return _value()["filename"]

    def _media_type() -> str:
        return _value()["mime"]

    def _download() -> Iterator[bytes]:
        value = _value()
        yield base64.b64decode(value["data"])

    # Shiny 1.9 renamed render.download to render.download_button.
    renderer = getattr(shiny_render, "download_button", None)
    if renderer is None:  # pragma: no cover - Shiny < 1.9
        renderer = shiny_render.download
    output(id=f"dl_{oid}")(renderer(filename=_filename, media_type=_media_type)(_download))

    # Render the download button only once a result with this output exists, so a
    # disabled placeholder is shown before the first run and after a failed run
    # (issue #51). The real button keeps the download handler's id `dl_{oid}`.
    label = spec.get("label", oid)

    @output(id=f"dl_btn_{oid}")
    @shiny_render.ui
    def _button() -> TagChild:
        res = result()
        value = res.outputs.get(oid) if res is not None else None
        if isinstance(value, dict) and "data" in value:
            return ui.download_button(f"dl_{oid}", f"Download {label}")
        # A plain button with no id: an input with id `dl_btn_{oid}` would share
        # the id of this output.
        return ui.tags.button(
            f"Download {label}", type="button", class_="btn btn-default", disabled=True
        )
