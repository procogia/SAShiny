r"""SAShiny Lisbon demo app (Python).

Four tabs (General / Pharma / AML / Forecasting) run the example contracts. The sidebar picks
the SAS connection:

- **Offline** replays recordings from ``examples/recordings`` (spec §8.3).
- **ODA**, **ProCogia Viya** and **ProCogia SAS 9.4** run live through saspy.
  Every live run is also saved as a recording, so running the demo inputs once
  live fills the offline fallback. If a live session cannot start, the run falls
  back to the matching recording and says so in the Run card.

Connection details come from environment variables; credentials come only from
``~/.authinfo`` (see ``docs/live-sas-run-sheet.md``):

    SASHINY_ODA_REGION   us1 | us2 | eu1 | ap1 | ap2   (default us1)
    SASHINY_VIYA_URL     https://viya.example.com
    SASHINY_VIYA_CONTEXT SAS Studio compute context     (optional)
    SASHINY_SAS94_HOST   sas94.example.com

Run from the repository root:

    cd Python && uv run --extra shiny --extra saspy --extra upload \\
        shiny run examples/demo/app.py --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from shiny import App, Inputs, Outputs, Session, reactive, ui

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
RECORDINGS = EXAMPLES / "recordings"

TRACKS = {
    "general": ("General", EXAMPLES / "general" / "cars_explorer.sashiny.yml"),
    "pharma": ("Pharma", EXAMPLES / "pharma" / "ae_summary.sashiny.yml"),
    "aml": ("AML", EXAMPLES / "aml" / "cash_aggregation_tuning.sashiny.yml"),
    "forecasting": ("Forecasting", EXAMPLES / "forecasting" / "arima_forecast.sashiny.yml"),
}
PROFILES = {
    "offline": "Offline (recordings)",
    "oda": "SAS OnDemand for Academics",
    "viya": "ProCogia SAS Viya (VPN)",
    "sas94": "ProCogia SAS 9.4 (VPN)",
}


def _live_engine(profile: str) -> sashiny.Engine:
    """Build a pooled live engine for a profile from environment variables."""
    env = os.environ

    def factory() -> sashiny.Engine:
        if profile == "oda":
            return sashiny.connect(
                "oda", region=env.get("SASHINY_ODA_REGION", "us1"), record_to=RECORDINGS
            )
        if profile == "viya":
            return sashiny.connect(
                "viya",
                url=env.get("SASHINY_VIYA_URL"),
                context=env.get("SASHINY_VIYA_CONTEXT"),
                record_to=RECORDINGS,
            )
        return sashiny.connect("sas94", host=env.get("SASHINY_SAS94_HOST"), record_to=RECORDINGS)

    return sashiny.Pool(factory, max_size=2)


# One shared live pool per profile, so `max_size` bounds live SAS sessions
# across every browser session rather than per session (issue #62).
_LIVE_ENGINES: dict[str, sashiny.Engine] = {}


def _shared_live_engine(profile: str) -> sashiny.Engine:
    if profile not in _LIVE_ENGINES:
        _LIVE_ENGINES[profile] = _live_engine(profile)
    return _LIVE_ENGINES[profile]


class DemoEngine(sashiny.Engine):
    """Routes runs to the selected profile and falls back to recordings."""

    name = "demo"
    version = sashiny.__version__

    def __init__(self, profile: reactive.Value[str]) -> None:
        """Route to ``profile``; live engines are shared across sessions."""
        self.profile = profile
        self.offline = sashiny.MockEngine(RECORDINGS)

    def _current(self) -> tuple[str, sashiny.Engine]:
        with reactive.isolate():
            name = self.profile()
        if name == "offline":
            return name, self.offline
        return name, _shared_live_engine(name)

    def choices(self, contract: sashiny.Contract) -> dict[str, list[dict[str, str]]]:
        """Read ``choices_from`` choices on the selected engine."""
        _, engine = self._current()
        return engine.choices(contract)

    def run(
        self,
        contract: sashiny.Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> sashiny.Result:
        """Run live on the selected profile, or replay a recording."""
        name, engine = self._current()
        kwargs: dict[str, Any] = {"today": today, "uploads": uploads, "run_id": run_id}
        if name == "offline":
            return engine.run(contract, values, **kwargs)
        try:
            result = engine.run(contract, values, **kwargs)
        except ValueError as exc:  # missing connection settings
            reason = str(exc)
        else:
            reason = result.metadata.get("engine_error", "")
            if not reason:
                return result
        fallback = self.offline.run(contract, values, **kwargs)
        fallback.metadata["notice"] = (
            f"live {PROFILES[name]} unavailable ({reason}); showing the offline recording"
        )
        return fallback

    def close(self) -> None:
        """Close the offline engine (live pools are shared across sessions)."""
        self.offline.close()


app_ui = ui.page_navbar(
    ui.nav_panel(
        "About",
        ui.markdown(
            "SAShiny turns unchanged SAS programs into Shiny apps. Each tab is one SAS "
            "program plus a sidecar YAML contract. Choose a connection, set the inputs "
            "and press Run."
        ),
    ),
    *[
        ui.nav_panel(label, modules.program_ui(tid, sashiny.load(path)))
        for tid, (label, path) in TRACKS.items()
    ],
    title="SAShiny demo",
    sidebar=ui.sidebar(
        ui.input_select("profile", "SAS connection", PROFILES, selected="offline"),
        ui.markdown(
            "Offline replays recorded runs. Live profiles need saspy, Java (IOM) and "
            "credentials in `~/.authinfo`."
        ),
        open="closed",
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    """Serve every track through one routing engine."""
    profile: reactive.Value[str] = reactive.value("offline")

    @reactive.effect
    def _track_profile() -> None:
        profile.set(input.profile())

    engine = DemoEngine(profile)
    for tid, (_label, path) in TRACKS.items():
        modules.program_server(tid, sashiny.load(path), engine)
    session.on_ended(engine.close)


app = App(app_ui, server)
