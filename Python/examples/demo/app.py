r"""SAShiny demo app (Python).

Four tabs (General / Pharma / AML / Forecasting) run the example contracts on a
live SAS system chosen with ``SASHINY_PROFILE``: ``oda`` (SAS OnDemand for
Academics, the default), ``viya`` or ``sas94``. There is no offline mode:
SAShiny runs programs only on a SAS system you are licensed to use. Acknowledge
this with ``SASHINY_LICENSE_ACK=true`` before starting the app.

Connection details come from environment variables; credentials come only from
``~/.authinfo`` or ``SASHINY_SAS_USER`` / ``SASHINY_SAS_PASSWORD`` (see
``docs/live-sas-run-sheet.md``):

    SASHINY_ODA_REGION   us1 | us2 | eu1 | ap1 | ap2   (default us1)
    SASHINY_VIYA_URL     https://viya.example.com
    SASHINY_VIYA_CONTEXT SAS Studio compute context     (optional)
    SASHINY_SAS94_HOST   sas94.example.com

Run from the repository root:

    cd Python && SASHINY_LICENSE_ACK=true uv run --extra shiny --extra saspy \\
        --extra upload --extra plotnine shiny run examples/demo/app.py --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from shiny import App, Inputs, Outputs, Session, ui

import sashiny
from sashiny import modules


def _examples_dir() -> Path:
    """Locate the shared ``examples/`` directory (repo or extracted sdist)."""
    here = Path(__file__).resolve()
    for parent in (here.parents[2], here.parents[3], here.parents[4]):
        candidate = parent / "examples"
        if (candidate / "general").is_dir():
            return candidate
    return here.parents[3] / "examples"


EXAMPLES = _examples_dir()

TRACKS = {
    "general": ("General", EXAMPLES / "general" / "cars_explorer.sashiny.yml"),
    "pharma": ("Pharma", EXAMPLES / "pharma" / "ae_summary.sashiny.yml"),
    "aml": ("AML", EXAMPLES / "aml" / "cash_aggregation_tuning.sashiny.yml"),
    "forecasting": ("Forecasting", EXAMPLES / "forecasting" / "arima_forecast.sashiny.yml"),
}
PROFILES = {
    "oda": "SAS ODA (OnDemand for Academics)",
    "viya": "SAS Viya",
    "sas94": "SAS 9.4",
}
PROFILE = os.environ.get("SASHINY_PROFILE", "oda")
if PROFILE not in PROFILES:
    raise ValueError(f"SASHINY_PROFILE must be one of {sorted(PROFILES)}")


def _live_engine(profile: str) -> sashiny.Pool:
    """Build a pooled live engine for a profile from environment variables."""
    env = os.environ

    def factory() -> sashiny.Engine:
        if profile == "oda":
            return sashiny.connect(sashiny.oda(env.get("SASHINY_ODA_REGION", "us1")))
        if profile == "viya":
            return sashiny.connect(
                sashiny.viya(
                    env.get("SASHINY_VIYA_URL", ""), context=env.get("SASHINY_VIYA_CONTEXT")
                )
            )
        return sashiny.connect(sashiny.sas94_iom(env.get("SASHINY_SAS94_HOST", "")))

    return sashiny.Pool(factory, max_size=2)


# One shared live pool, so `max_size` bounds live SAS sessions across every
# browser session rather than per session (issue #62).
ENGINE = _live_engine(PROFILE)

app_ui = ui.page_navbar(
    ui.nav_panel(
        "About",
        ui.markdown(
            "SAShiny turns unchanged SAS programs into Shiny apps. Each tab is one SAS "
            "program plus a sidecar YAML contract. Set the inputs and press Run."
        ),
    ),
    *[
        ui.nav_panel(label, modules.program_ui(tid, sashiny.load(path)))
        for tid, (label, path) in TRACKS.items()
    ],
    title="SAShiny demo",
    sidebar=ui.sidebar(
        ui.markdown(
            f"Connected to **{PROFILES[PROFILE]}** (set `SASHINY_PROFILE`). You are "
            "responsible for obtaining access to a compatible SAS compiler for your chosen "
            "profile, and for its licence; SAShiny does not provide SAS. Runs need saspy, "
            "Java (IOM) and credentials in `~/.authinfo`."
        ),
        open="closed",
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    """Serve every track on the shared live pool."""
    for tid, (_label, path) in TRACKS.items():
        modules.program_server(tid, sashiny.load(path), ENGINE)


app = App(app_ui, server)
