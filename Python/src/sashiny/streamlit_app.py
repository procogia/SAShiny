"""Streamlit front end for SAShiny contracts (spec ``CONTRACT.md`` §6.9).

:func:`streamlit_app` renders contracts as a Streamlit app. Only the widgets
differ from the Shiny modules: contract loading, value validation (V001-V014),
the wrapper, engines, pool, timeouts and collection are reused unchanged.
Streamlit is an optional extra (``sashiny[streamlit]``); this module imports it
only when the app runs. There is no R equivalent (Streamlit is Python-only).
"""

from __future__ import annotations

import base64
import html
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, cast

from . import result_cache
from .collect import is_paired, paired_chart_spec
from .contract import Contract, default_module_id, load, resolve_date
from .engines import Engine
from .engines.base import check_engine
from .errors import ValuesError
from .result import Result
from .upload import UploadError, UploadFile

__all__ = ["WidgetSpec", "streamlit_app", "widget_spec"]

SAMPLE_LABEL = "Use the sample file"
_POLL_SECONDS = 1.0
# Streamlit in Snowflake exposes a PASSWORD secret named `sashiny_sas` as these
# variables (spec §6.8.5); the engines read SASHINY_SAS_USER / _PASSWORD.
_SECRET_ENV = {
    "SASHINY_SAS_USER": "sashiny_sas_USERNAME",
    "SASHINY_SAS_PASSWORD": "sashiny_sas_PASSWORD",
}


@dataclass(frozen=True)
class WidgetSpec:
    """The Streamlit widget for one contract input (spec §6.9 table)."""

    widget: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    options: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)


def _choices(spec: dict[str, Any], loaded: list[dict[str, str]] | None) -> dict[str, str]:
    items = loaded if loaded is not None else spec.get("choices", [])
    out: dict[str, str] = {}
    for c in items:
        if isinstance(c, str):
            out[c] = c
        else:
            out[c["value"]] = c.get("label", c["value"])
    return out


def _date(value: str | None, today: date) -> date | None:
    return None if value is None else resolve_date(value, today)


def _numeric(spec: dict[str, Any], common: dict[str, Any]) -> WidgetSpec:
    integer = bool(spec.get("integer"))
    num: Callable[[Any], int | float] = int if integer else float
    kw: dict[str, Any] = {**common, "value": spec.get("default")}
    for src, dst in (("min", "min_value"), ("max", "max_value")):
        if src in spec:
            kw[dst] = num(spec[src])
    if "step" in spec or integer:
        kw["step"] = num(spec.get("step", 1))
    if integer:
        kw["format"] = "%d"
    if kw["value"] is not None:
        kw["value"] = num(kw["value"])
    return WidgetSpec("number_input", kw)


def _choice(
    spec: dict[str, Any], common: dict[str, Any], loaded: list[dict[str, str]] | None
) -> WidgetSpec:
    labels = _choices(spec, loaded)
    options = list(labels)
    if spec["type"] == "choice":
        default = spec.get("default")
        kw = {**common, "index": options.index(default) if default in options else None}
        widget = "radio" if spec.get("widget") == "radio" else "selectbox"
        return WidgetSpec(widget, kw, options, labels)
    kw = {**common, "default": [v for v in spec.get("default", []) if v in labels]}
    if spec.get("widget") == "checkbox":
        return WidgetSpec("checkbox_group", kw, options, labels)
    if "max_selected" in spec:
        kw["max_selections"] = spec["max_selected"]
    return WidgetSpec("multiselect", kw, options, labels)


def _dates(spec: dict[str, Any], common: dict[str, Any], today: date) -> WidgetSpec:
    if spec["type"] == "date":
        value: Any = _date(spec.get("default"), today)
        widget = "date_input"
    else:
        start, end = spec.get("default", [None, None])
        value = (_date(start, today), _date(end, today)) if start and end else ()
        widget = "date_range_input"
    kw = {
        **common,
        "value": value,
        "min_value": _date(spec.get("min"), today),
        "max_value": _date(spec.get("max"), today),
    }
    return WidgetSpec(widget, kw)


def widget_spec(
    spec: dict[str, Any], today: date, loaded: list[dict[str, str]] | None = None
) -> WidgetSpec:
    """Return the Streamlit widget and arguments for one input (spec §6.9).

    Args:
        spec: The input's contract spec.
        today: The date that resolves ``"today"``.
        loaded: Choices read by ``choices_from`` (§6.4), if any.

    Returns:
        The :class:`WidgetSpec`: the ``st`` function name, its keyword
        arguments (without ``label`` and ``key``), and for choice inputs the
        option values and labels.

    Raises:
        ValueError: For an unknown input type.

    """
    kind = spec["type"]
    common: dict[str, Any] = {"help": spec["help"]} if spec.get("help") else {}
    if kind == "numeric":
        return _numeric(spec, common)
    if kind == "text":
        kw = {**common, "value": spec.get("default", ""), "max_chars": spec.get("max_length", 256)}
        if "placeholder" in spec:
            kw["placeholder"] = spec["placeholder"]
        return WidgetSpec("text_input", kw)
    if kind in ("choice", "multichoice"):
        return _choice(spec, common, loaded)
    if kind in ("date", "daterange"):
        return _dates(spec, common, today)
    if kind == "dataset":
        kw = {**common, "type": list(spec.get("accept", ["csv", "xlsx", "xpt", "sas7bdat"]))}
        if "sample" in spec:
            kw["sample"] = True
        return WidgetSpec("file_uploader", kw)
    raise ValuesError(f"unknown input type {kind}")


def to_values(contract: Contract, raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert widget values to the contract's JSON form (spec §2.1).

    Args:
        contract: The loaded contract.
        raw: Widget values keyed by input id. A dataset input's value is a
            Streamlit ``UploadedFile`` (or any object with ``name`` and
            ``getvalue()``), or ``True`` for its sample file.

    Returns:
        ``(values, uploads)`` for :meth:`Engine.run`.

    Raises:
        UploadError: If an upload exceeds ``max_size_mb`` (V014, §7).

    """
    values: dict[str, Any] = {}
    uploads: dict[str, Any] = {}
    for iid, spec in (contract.data.get("inputs") or {}).items():
        kind = spec["type"]
        value = raw.get(iid)
        if kind == "dataset":
            if value is True:
                uploads[iid] = True
            elif value is not None:
                uploads[iid] = _save_upload(value, spec)
            continue
        values[iid] = _json_value(kind, value)
    return values, uploads


def _json_value(kind: str, value: Any) -> Any:  # noqa: PLR0911 - one return per input type
    """Return one widget value in the JSON form of spec §2.1."""
    if kind == "multichoice":
        return list(value or [])
    if kind == "date":
        return value.isoformat() if isinstance(value, date) else None
    if kind == "daterange":
        pair = isinstance(value, (list, tuple)) and len(value) == 2  # noqa: PLR2004
        if pair and all(isinstance(d, date) for d in value):
            return [value[0].isoformat(), value[1].isoformat()]
        return None
    if kind == "choice":
        return value or None
    if kind == "numeric":
        return value
    return "" if value is None else value


def _save_upload(file: Any, spec: dict[str, Any]) -> UploadFile:
    """Write an uploaded file to a temporary path, refusing it over ``max_size_mb`` (§7)."""
    import tempfile  # noqa: PLC0415 - only for uploads

    data = file.getvalue()
    limit = spec.get("max_size_mb", 50)
    size_mb = len(data) / (1024 * 1024)
    if size_mb > limit:
        raise UploadError(f"{file.name} is {size_mb:.1f} MB (limit {limit} MB)")
    folder = Path(tempfile.mkdtemp(prefix="sashiny-upload-"))
    path = folder / Path(file.name).name
    path.write_bytes(data)
    return UploadFile(path=path, name=file.name)


class _Run:
    """A SAS run in a background thread, kept in ``st.session_state`` (§6.9)."""

    def __init__(self, target: Callable[[], Result]) -> None:
        self.result: Result | None = None
        self.error: BaseException | None = None

        def work() -> None:
            try:
                self.result = target()
            except BaseException as exc:  # reported in the app
                self.error = exc

        self.thread = threading.Thread(target=work, daemon=True, name="sashiny-run")
        self.thread.start()

    @property
    def done(self) -> bool:
        return not self.thread.is_alive()


def _upload_error(exc: UploadError) -> Result:
    import uuid  # noqa: PLC0415

    result = Result.new(str(uuid.uuid4()), "error")
    result.metadata["issues"] = [{"code": "V014", "message": str(exc)}]
    return result


def _copy_snowflake_secret() -> None:
    for name, source in _SECRET_ENV.items():
        if not os.environ.get(name) and os.environ.get(source):
            os.environ[name] = os.environ[source]


def _module_id(contract: Contract) -> str:
    return str(contract.data.get("id") or default_module_id(contract.data["program"]))


def _ordered_inputs(contract: Contract) -> list[tuple[str, dict[str, Any]]]:
    inputs: dict[str, Any] = contract.data.get("inputs") or {}
    order = [i for i in (contract.data.get("ui") or {}).get("order", []) if i in inputs]
    return [(i, inputs[i]) for i in order + [i for i in inputs if i not in order]]


def streamlit_app(
    contracts: Sequence[Contract | str | Path],
    engine: Engine | Callable[[], Engine],
    *,
    title: str | None = None,
) -> None:
    """Render SAShiny contracts as a Streamlit app (spec §6.9).

    Call it from a Streamlit script (``streamlit run streamlit_app.py``).

    Args:
        contracts: :class:`Contract` objects or paths to ``*.sashiny.yml`` files.
        engine: A :func:`sashiny.connect` engine or :class:`sashiny.Pool`, or a
            zero-argument function returning one (for example
            :func:`sashiny.connect_from_env`). A function is called once per
            server process and the engine is shared by all sessions.
        title: The page title. Defaults to the contract title when there is one
            contract, else ``"SAShiny"``.

    Raises:
        ValueError: If two contracts resolve to the same module id.
        TypeError: If the engine is not a live SAS engine or pool.

    """
    import streamlit as st  # noqa: PLC0415 - optional dependency

    _copy_snowflake_secret()
    loaded = [c if isinstance(c, Contract) else load(c) for c in contracts]
    ids = [_module_id(c) for c in loaded]
    if len(set(ids)) != len(ids):
        raise ValuesError("two contracts resolve to the same module id")
    eng = _engine(st, engine)
    page_title = title or (loaded[0].data.get("title") if len(loaded) == 1 else None) or "SAShiny"
    st.title(page_title)
    index = 0
    if len(loaded) > 1:
        names = [c.data.get("title", ids[i]) for i, c in enumerate(loaded)]
        picked = st.sidebar.selectbox("Program", names, key="sashiny-program")
        index = names.index(picked)
    _program(st, loaded[index], ids[index], eng)


def _engine(st: Any, engine: Engine | Callable[[], Engine]) -> Engine:
    """Return the engine; a factory is called once per server process (cached)."""
    if isinstance(engine, Engine) or hasattr(engine, "run"):
        return check_engine(cast("Engine", engine))
    factory = engine

    def _shared() -> Engine:
        return check_engine(factory())

    cached: Callable[[], Engine] = st.cache_resource(show_spinner=False)(_shared)
    return cached()


def _program(st: Any, contract: Contract, mid: str, engine: Engine) -> None:
    state = st.session_state
    settings = contract.data.get("ui") or {}
    if contract.data.get("description"):
        st.caption(contract.data["description"])
    loaded = _load_choices(st, contract, mid, engine)
    raw: dict[str, Any] = {}
    panel = st.sidebar if settings.get("layout", "sidebar") == "sidebar" else st.container()
    with panel:
        for iid, spec in _ordered_inputs(contract):
            raw[iid] = _widget(st, f"sashiny-{mid}-{iid}", spec, loaded.get(iid))
        clicked = st.button(
            settings.get("run_label", "Run"), key=f"sashiny-{mid}-run", type="primary"
        )
    run_key, result_key, auto_key = (
        f"sashiny-{mid}-task",
        f"sashiny-{mid}-result",
        f"sashiny-{mid}-auto",
    )
    start = clicked or (settings.get("auto_run") and not state.get(auto_key))
    if start and state.get(run_key) is None:
        state[auto_key] = True
        try:
            values, uploads = to_values(contract, raw)
        except UploadError as exc:
            state[result_key] = _upload_error(exc)
        else:
            state[run_key] = _Run(
                lambda: result_cache.cached_run(
                    engine,
                    contract,
                    values,
                    lambda: engine.run(contract, values, uploads=uploads),
                    uploads=uploads,
                )
            )
    task: _Run | None = state.get(run_key)
    if task is not None:
        if not task.done:
            with st.status("Running...", expanded=False):
                st.write("SAS is running the program.")
            time.sleep(_POLL_SECONDS)
            st.rerun()
        state[run_key] = None
        if task.error is not None:
            st.error(f"engine error: {task.error}")
            return
        state[result_key] = task.result
    result: Result | None = state.get(result_key)
    if result is not None:
        _outputs(st, contract, result)


def _load_choices(st: Any, contract: Contract, mid: str, engine: Engine) -> dict[str, Any]:
    inputs = contract.data.get("inputs") or {}
    if not any("choices_from" in s for s in inputs.values()):
        return {}
    key = f"sashiny-{mid}-choices"
    if key not in st.session_state:
        try:
            st.session_state[key] = engine.choices(contract)
        except Exception as exc:  # shown in the app (§6.9)
            st.session_state[key] = {}
            st.session_state[f"{key}-error"] = f"could not read choices: {exc}"
    if st.session_state.get(f"{key}-error"):
        st.error(st.session_state[f"{key}-error"])
    return dict(st.session_state[key])


def _widget(  # noqa: PLR0911 - one return per widget kind
    st: Any, key: str, spec: dict[str, Any], loaded: list[dict[str, str]] | None
) -> Any:
    ws = widget_spec(spec, date.today(), loaded)
    label = spec.get("label", key)
    kw = dict(ws.kwargs)
    if ws.widget in ("selectbox", "radio"):
        return getattr(st, ws.widget)(
            label, ws.options, format_func=lambda v: ws.labels.get(v, v), key=key, **kw
        )
    if ws.widget == "multiselect":
        return st.multiselect(
            label, ws.options, format_func=lambda v: ws.labels.get(v, v), key=key, **kw
        )
    if ws.widget == "checkbox_group":
        st.markdown(f"**{label}**", help=kw.get("help"))
        default = set(kw.get("default", []))
        return [
            v for v in ws.options if st.checkbox(ws.labels[v], value=v in default, key=f"{key}-{v}")
        ]
    if ws.widget == "date_range_input":
        return st.date_input(label, key=key, **kw)
    if ws.widget == "file_uploader":
        sample = kw.pop("sample", False)
        file = st.file_uploader(label, key=key, **kw)
        if file is None and sample and st.checkbox(SAMPLE_LABEL, value=True, key=f"{key}-sample"):
            return True
        return file
    return getattr(st, ws.widget)(label, key=key, **kw)


def _outputs(st: Any, contract: Contract, result: Result) -> None:
    meta = result.metadata
    st.caption(f"status: {result.status} | run_id: {result.run_id}")
    for issue in meta.get("issues", []):
        where = issue.get("input") or ""
        st.error(f"invalid input {issue['code']} {where} {issue.get('message', '')}".rstrip())
    if meta.get("engine_error"):
        st.error(f"engine error: {meta['engine_error']}")
    for err in meta.get("collect_errors", []):
        st.warning(f"collect error: {err}")
    for oid, spec in (contract.data.get("outputs") or {}).items():
        if oid not in result.outputs:
            continue
        st.subheader(spec.get("label", oid))
        if spec.get("help"):
            st.caption(spec["help"])
        _output(st, oid, spec, result.outputs[oid])
    with st.expander("SAS log"):
        st.code(result.log or "(no log)", language=None)


def _output(st: Any, oid: str, spec: dict[str, Any], value: Any) -> None:
    if isinstance(value, dict) and "error" in value and "data" not in value:
        st.error(f"Could not collect this output: {value['error']}")
        return
    kind = spec["type"]
    if is_paired(spec):
        views = ["SAShiny", "SAS"]
        tabs = st.tabs(views)
        with tabs[0]:
            _chart(st, value.get("sashiny"), paired_chart_spec(spec))
        with tabs[1]:
            _plots(st, value.get("sas") or [])
        return
    if kind == "table":
        _table(st, value)
    elif kind == "plot":
        _plots(st, value)
    elif kind == "chart":
        _chart(st, value, spec)
    elif kind == "html":
        _html(st, value)
    elif kind == "log":
        st.code("\n".join(line["text"] for line in value), language=None)
    elif kind == "download":
        st.download_button(
            f"Download {spec.get('label', oid)}",
            base64.b64decode(value["data"]),
            file_name=value["filename"],
            mime=value["mime"],
            key=f"sashiny-dl-{oid}",
        )


def _table(st: Any, value: dict[str, Any]) -> None:
    headers = [c["label"] or c["name"] for c in value["columns"]]
    rows = [dict(zip(headers, row, strict=True)) for row in value["rows"]]
    st.dataframe(rows, hide_index=True)
    if value.get("truncated"):
        st.caption(f"Showing {len(value['rows'])} of {value['total_rows']} rows.")


def _plots(st: Any, value: list[dict[str, str]]) -> None:
    if not value:
        st.caption("No graphs were produced.")
        return
    for p in value:
        st.image(base64.b64decode(p["data"]))


def _chart(st: Any, value: Any, spec: dict[str, Any]) -> None:
    if not value or not value.get("rows"):
        st.caption("No data for this chart.")
        return
    try:
        from .charts import render_chart  # noqa: PLC0415 - optional chart backends

        chart_spec = spec.get("spec")
        plot = render_chart(
            value, chart_spec, backend=(chart_spec or {}).get("backend", "plotnine")
        )
    except Exception as exc:  # shown in the app
        st.caption(f"Could not render this chart: {exc}")
        return
    if type(plot).__module__.startswith("plotly."):
        st.plotly_chart(plot)
    elif hasattr(plot, "savefig"):
        st.pyplot(plot)
    else:
        from .modules import _plot_to_png  # noqa: PLC0415 - shared PNG serialiser

        st.image(base64.b64decode(_plot_to_png(plot)))


def sandboxed_html(value: str) -> str:
    """Wrap an ODS HTML document in an ``<iframe sandbox="">`` (no scripts, §6.9)."""
    doc = html.escape(value, quote=True)
    return (
        '<iframe sandbox="" title="SAS output" '
        'style="width: 100%; height: 600px; border: 0;" '
        f'srcdoc="{doc}"></iframe>'
    )


def _html(st: Any, value: str) -> None:
    if not value:
        st.caption("No HTML output.")
        return
    # st.iframe runs scripts in HTML strings, so the SAS document goes in an
    # inner sandboxed frame; only this fixed wrapper is trusted.
    wrapper = sandboxed_html(value)
    iframe = getattr(st, "iframe", None)
    if iframe is not None:
        iframe(wrapper, height=620)
    else:  # pragma: no cover - Streamlit without st.iframe
        import streamlit.components.v1 as components  # noqa: PLC0415

        components.html(wrapper, height=620)
