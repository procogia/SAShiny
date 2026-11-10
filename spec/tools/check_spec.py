"""Check the SAShiny spec: schema, fixtures and example contracts.

Usage (from the repository root):

    uv run --with jsonschema --with pyyaml python spec/tools/check_spec.py

Exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sashiny_ref as ref  # noqa: E402

SPEC = ref.SPEC_DIR
REPO = SPEC.parent
FIX = SPEC / "fixtures"


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
        else:
            self.failures.append(f"FAIL {label}" + (f"\n     {detail}" if detail else ""))


def check_schema(r: Report) -> None:
    try:
        Draft202012Validator.check_schema(ref.SCHEMA)
        r.check(True, "schema is valid JSON Schema 2020-12")
    except Exception as exc:  # pragma: no cover - reported, not raised
        r.check(False, "schema is valid JSON Schema 2020-12", str(exc))


def check_valid(r: Report, today: date) -> None:
    for yml in sorted((FIX / "contracts" / "valid").glob("*/contract.sashiny.yml")):
        issues = ref.validate(ref.load(yml), today)
        r.check(not issues, f"valid/{yml.parent.name}", "; ".join(f"{i.code} {i.path} {i.message}" for i in issues))


def check_invalid(r: Report, today: date) -> None:
    for yml in sorted((FIX / "contracts" / "invalid").glob("*/contract.sashiny.yml")):
        expected = json.loads((yml.parent / "expected.json").read_text(encoding="utf-8"))
        want = {(e["code"], e["path"]) for e in expected["errors"]}
        got_issues = ref.validate(ref.load(yml), today)
        got = {i.key() for i in got_issues}
        if all(c == "E000" for c, _ in want):
            # Schema errors: the expected path must be reported; exact messages vary by validator.
            paths_found = all(any(gp.startswith(p) or p.startswith(gp) for _, gp in got) for _, p in want)
            ok = bool(got) and all(c == "E000" for c, _ in got) and paths_found
        else:
            ok = got == want
        r.check(ok, f"invalid/{yml.parent.name}", f"want {sorted(want)} got {sorted(got)}")


def check_values(r: Report) -> None:
    for vf in sorted((FIX / "values").glob("*.json")):
        spec = json.loads(vf.read_text(encoding="utf-8"))
        contract = ref.load(FIX / spec["contract"] / "contract.sashiny.yml")
        today = date.fromisoformat(spec["today"])
        for case in spec["cases"]:
            macros, issues = ref.render_values(
                contract.data,
                case["values"],
                today,
                choices_override=case.get("choices_from"),
                uploads=case.get("uploads"),
            )
            exp = case["expected"]
            label = f"values/{vf.stem}/{case['name']}"
            if exp["status"] == "ok":
                ok = not issues and list(macros.items()) == list(exp["macros"].items())
                r.check(ok, label, f"issues={[i.key() for i in issues]} macros={macros} want={exp['macros']}")
            else:
                want = {(e["code"], e["input"]) for e in exp["errors"]}
                got = {(i.code, i.path) for i in issues}
                r.check(got == want, label, f"want {sorted(want)} got {sorted(got)}")


def check_wrappers(r: Report) -> None:
    for d in sorted((FIX / "wrapper").iterdir()):
        contract = ref.load(d / "contract.sashiny.yml")
        case = json.loads((d / "case.json").read_text(encoding="utf-8"))
        today = date.fromisoformat(case["today"])
        issues = ref.validate(contract, today)
        r.check(not issues, f"wrapper/{d.name} contract valid", str([i.key() for i in issues]))
        macros, vissues = ref.render_values(contract.data, case["values"], today, uploads=case.get("uploads"))
        r.check(not vissues, f"wrapper/{d.name} values valid", str([i.key() for i in vissues]))
        reset_enabled = (contract.data.get("run") or {}).get("reset_work", True)
        reset_file = d / "expected_reset.sas"
        r.check(reset_file.exists() == reset_enabled, f"wrapper/{d.name} reset file presence")
        if reset_enabled and reset_file.exists():
            r.check(
                ref.reset_code(contract.data) == reset_file.read_text(encoding="utf-8"),
                f"wrapper/{d.name} reset bytes",
                repr(ref.reset_code(contract.data)),
            )
        program = (d / contract.data["program"]).read_bytes()
        got = ref.wrapper_code(contract.data, macros, program)
        want = (d / "expected_main.sas").read_text(encoding="utf-8")
        r.check(got == want, f"wrapper/{d.name} main bytes", _diff(want, got))


def check_collect(r: Report) -> None:
    d = FIX / "collect"
    for case in json.loads((d / "log_scope.json").read_text(encoding="utf-8"))["cases"]:
        got = ref.scope_log(case["log"], case["scope"])
        r.check(got == case["expected"], f"collect/log_scope/{case['name']}", f"got {got}")
    plots = json.loads((d / "plots.json").read_text(encoding="utf-8"))
    for case in plots["cases"]:
        label = f"collect/plots/{case['name']}"
        if case.get("expected_error"):
            try:
                ref.extract_plots(plots["html"], case["select"])
                r.check(False, label, "expected an error")
            except ValueError:
                r.check(True, label)
        else:
            got = ref.extract_plots(plots["html"], case["select"])
            r.check(got == case["expected"], label, f"got {got}")
    k = json.loads((d / "recording_key.json").read_text(encoding="utf-8"))
    macros = [tuple(m) for m in k["macros"]]
    uploads = [tuple(u) for u in k["uploads"]]
    r.check(ref.recording_key_text(k["contract_sha256"], macros, uploads) == k["key_text"], "collect/recording_key text")
    r.check(ref.recording_key(k["contract_sha256"], macros, uploads) == k["key"], "collect/recording_key sha256")


def check_expected_sas_format(r: Report) -> None:
    for f in sorted(FIX.glob("wrapper/*/expected_*.sas")):
        raw = f.read_bytes()
        lines = raw.decode("utf-8").split("\n")
        ok = b"\r" not in raw and raw.endswith(b"\n") and all(line == line.rstrip() for line in lines)
        r.check(ok, f"format {f.relative_to(FIX)}", "must be LF, end with newline, no trailing spaces")


def check_examples(r: Report, today: date) -> None:
    for yml in sorted((REPO / "examples").rglob("*.sashiny.yml")):
        issues = ref.validate(ref.load(yml), today)
        r.check(not issues, f"example {yml.relative_to(REPO)}", "; ".join(f"{i.code} {i.path} {i.message}" for i in issues))


def _diff(want: str, got: str) -> str:
    import difflib

    return "\n     ".join(difflib.unified_diff(want.splitlines(), got.splitlines(), "expected", "generated", lineterm=""))


def main() -> int:
    today = date(2026, 11, 11)
    r = Report()
    check_schema(r)
    check_valid(r, today)
    check_invalid(r, today)
    check_values(r)
    check_wrappers(r)
    check_collect(r)
    check_expected_sas_format(r)
    check_examples(r, date.today())
    for f in r.failures:
        print(f)
    print(f"\n{r.passed} passed, {len(r.failures)} failed")
    return 1 if r.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
