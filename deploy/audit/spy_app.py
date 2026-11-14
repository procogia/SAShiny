"""A real Shiny module around an observable, synthetic engine (never live SAS)."""
import base64
import json
import time
from pathlib import Path

from shiny import App, reactive, render, ui
import sashiny
from sashiny import modules

ROOT = Path("/tmp/audit")
ROOT.joinpath("program.sas").write_text("data work.out; run;\n")


def emit(event, token):
    with (ROOT / "python-events.jsonl").open("a") as f:
        f.write(json.dumps({"event": event, "token": token, "time": time.time()}) + "\n")


class Spy(sashiny.Engine):
    def __init__(self, choice_mode="ok"):
        self.choice_mode = choice_mode
    def choices(self, contract):
        if self.choice_mode == "error":
            raise RuntimeError("synthetic choices unavailable")
        if self.choice_mode == "slow":
            time.sleep(1)
        return {"selected": [{"value": "a", "label": "Alpha"}, {"value": "b", "label": "Beta"}]}
    def run(self, contract, values, **kwargs):
        token = values.get("token", "unset")
        emit("started", token)
        time.sleep(min(float(values.get("delay") or 0), 2))
        emit("completed", token)
        if values.get("failure") == "raise":
            raise RuntimeError("synthetic engine exception")
        r = sashiny.MockEngine(choices=self.choices(contract)).run(contract, values, **kwargs)
        if r.status == "error" or values.get("failure") == "result":
            r.status = "error"
            r.metadata["engine_error"] = "synthetic result error"
            return r
        r.outputs = {
            "table": {"columns": [{"name":"value","type":"numeric","label":"","format":""}],
                      "rows":[[7]],"total_rows":1,"truncated":False,"formatted":False},
            "report": [{"level":"note","text":token}],
            "csv": {"filename":"audit.csv","mime":"text/csv",
                    "data":base64.b64encode(b"value\n7\n").decode()},
        }
        return r


def contract(auto=False, choices=False):
    d = {
        "sashiny":1,"program":"program.sas","title":"Observable module",
        "inputs":{
            "token":{"type":"text","label":"Token","default":"audit"},
            "delay":{"type":"numeric","label":"Delay","min":0,"max":2,"default":0},
            "failure":{"type":"choice","label":"Failure","choices":["none","raise","result"],
                       "default":"none"},
            "data":{"type":"dataset","label":"Upload","target":"work.upload","optional":True,
                    "accept":["csv"],"max_size_mb":0.1,
                    "columns":[{"name":"age","type":"numeric"}]},
        },
        "outputs":{"table":{"type":"table","from":"work.out"},"report":{"type":"log"},
                   "csv":{"type":"download","from":"work.out","format":"csv"}},
        "ui":{"auto_run":auto},
    }
    if choices:
        d["inputs"]["selected"] = {"type":"choice","label":"Choice","optional":True,
                                   "choices_from":{"dataset":"work.choices","value_column":"value"}}
    return sashiny.Contract(d,ROOT)


contracts = {key:contract(auto=key=="auto",choices=key in ("broken","choices","slowchoices"))
             for key in ("normal","auto","broken","choices","slowchoices")}
app_ui = ui.page_navbar(*[
    ui.nav_panel(key,modules.program_ui(key,c),ui.output_text(f"returned_{key}"))
    for key,c in contracts.items()
])


def server(input, output, session):
    for key,c in contracts.items():
        engine = Spy("error" if key=="broken" else "slow" if key=="slowchoices" else "ok")
        returned = modules.program_server(key,c,engine)
        def register(k, r):
            @output(id=f"returned_{k}")
            @render.text
            def status():
                return r["status"]()
        register(key,returned)
    session.on_ended(lambda: emit("session_ended",session.id))


app = App(app_ui,server)
