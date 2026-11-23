"""Run the survival analysis contract on SAS without Shiny, and save the results.

The same path the Shiny app takes (sashiny.run): the inputs are validated
against survival_analysis.sashiny.yml, injected safely, the unchanged SAS
program runs, and every output is collected. Tables are written as CSV, SAS
graphs as PNG/SVG, and the SAS log as text.

The connection comes from the environment, as in a deployed app (spec 6.8):

    SASHINY_PROFILE=oda SASHINY_ODA_REGION=us1 SASHINY_LICENSE_ACK=true \
      python examples/survival/sas_survival_runner.py --out results/

Inputs default to the contract defaults (sample data). Change any of them:

    python examples/survival/sas_survival_runner.py --set study=NPH \
      --set assess_ph=yes --set covariates='["AGE","ECOG"]' --set cox_model=custom

Use your own files instead of the samples:

    python examples/survival/sas_survival_runner.py --adsl my_adsl.csv --adtte my_adtte.csv --set study=ALL

Needs the sashiny package with saspy (pip install "sashiny[saspy,upload]") and,
for ODA or SAS 9.4 IOM, Java. Exit status: 0 on success or warning, 1 on error.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from pathlib import Path
from typing import Any

import sashiny

CONTRACT = Path(__file__).resolve().parent / "survival_analysis.sashiny.yml"
EXT = {"image/png": "png", "image/svg+xml": "svg", "image/jpeg": "jpg", "image/gif": "gif"}


def _value(text: str) -> Any:
    """A JSON value (number, list, ...) or else the plain string."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_sets(items: list[str], inputs: dict[str, Any]) -> dict[str, Any]:
    """``key=value`` pairs into contract values (JSON form, spec 2.1).

    Choice, text and date values stay text (``conf_level=90`` is the choice
    ``"90"``); other values are read as JSON when they parse (numbers, lists).
    """
    values: dict[str, Any] = {}
    for item in items:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep:
            raise SystemExit(f"--set needs key=value, got {item!r}")
        kind = inputs.get(key, {}).get("type")
        values[key] = raw if kind in ("choice", "text", "date") else _value(raw)
    return values


def save(result: sashiny.Result, out: Path) -> list[str]:
    """Write every collected output under ``out``; return one line per file or problem."""
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for oid, value in result.outputs.items():
        if isinstance(value, dict) and set(value) == {"error"}:
            lines.append(f"{oid}: NOT COLLECTED - {value['error']}")
            continue
        if isinstance(value, dict) and "sas" in value and "sashiny" in value:  # paired output
            value = value["sas"]
        if isinstance(value, dict) and "rows" in value:
            path = out / f"{oid}.csv"
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow([c["label"] or c["name"] for c in value["columns"]])
                writer.writerows(value["rows"])
            lines.append(f"{oid}: {len(value['rows'])} rows -> {path.name}")
        elif isinstance(value, list) and value and isinstance(value[0], dict) and "mime" in value[0]:
            for k, graph in enumerate(value, 1):
                path = out / f"{oid}_{k}.{EXT.get(graph['mime'], 'bin')}"
                path.write_bytes(base64.b64decode(graph["data"]))
            lines.append(f"{oid}: {len(value)} graph(s)")
        elif isinstance(value, dict) and "filename" in value:
            (out / "downloads").mkdir(exist_ok=True)
            path = out / "downloads" / value["filename"]
            path.write_bytes(base64.b64decode(value["data"]))
            lines.append(f"{oid}: downloads/{path.name}")
        elif oid == "log":
            continue
        else:
            lines.append(f"{oid}: {sashiny.result.output_summary(value)}")
    (out / "sas.log").write_text(result.log, encoding="utf-8")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="an input value")
    parser.add_argument("--adsl", type=Path, help="your ADSL file (default: the sample)")
    parser.add_argument("--adtte", type=Path, help="your ADTTE file (default: the sample)")
    parser.add_argument("--out", type=Path, default=Path("survival_results"), help="output folder")
    args = parser.parse_args(argv)

    contract = sashiny.load(CONTRACT)
    # Start from the contract defaults, as the untouched UI does
    values = {
        iid: spec["default"]
        for iid, spec in contract.data["inputs"].items()
        if spec["type"] != "dataset" and "default" in spec
    }
    values.update(parse_sets(args.set, contract.data["inputs"]))
    uploads = {"adsl": args.adsl or True, "adtte": args.adtte or True}
    engine = sashiny.connect_from_env()
    try:
        result = sashiny.run(contract, engine, values, uploads=uploads)
    finally:
        engine.close()

    print(f"status: {result.status} (run {result.run_id}, SAS {result.metadata.get('sas_version', '?')})")
    summary = result.outputs.get("run_summary")
    if isinstance(summary, dict) and "rows" in summary:
        for item, value in summary["rows"]:
            print(f"  {item}: {value}")
    for line in save(result, args.out):
        print(f"  {line}")
    print(f"results in {args.out.resolve()}")
    if result.status not in ("success", "warning"):
        print(f"failed: {sashiny.result.failure_reason(result)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
