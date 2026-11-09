"""Live SAS conformance check for SAShiny.

Runs the SAShiny contract against a real SAS session through saspy and writes a
JSON report you can share. It never prints or stores credentials: saspy reads
them from your ~/.authinfo (Linux/macOS) or %USERPROFILE%\\_authinfo (Windows),
or prompts for them.

Profiles (pick one with --profile):

  oda   SAS OnDemand for Academics (SAS 9.4, IOM). Needs Java 8+.
        authinfo line:  oda user <ODA user or e-mail> password <ODA password>
  viya  SAS Viya (HTTP).  --url https://viya.example.com [--context "SAS Studio compute context"]
        authinfo line:  viya user <user> password <password>
  iom   SAS 9.4 workspace server (IOM). --host <host> [--port 8591]. Needs Java 8+.
        authinfo line:  iom user <user> password <password>
  ssh   SAS 9.4 over SSH (key-based). --host <host> --saspath /path/to/sas [--ssh-user <user>]

Examples (from the repository root):

  uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \\
      python spec/tools/live_sas_check.py --profile oda --oda-region us1

  uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \\
      python spec/tools/live_sas_check.py --profile viya --url https://viya.procogia.example

Checks:
  env        Python, saspy, pandas and Java versions
  connect    session starts; SAS version and encoding
  submit     plain submission and log classification
  graphics   ODS HTML results contain graphs
  roundtrip  data frame -> SAS -> data frame (dates, Unicode, missing values)
  wrapper    every spec/fixtures/wrapper case runs in SAS and injected macro values match exactly
  injection  hostile text values stay data (session survives, values intact)
  ods_ids    `ods rtf(id=...)` / `ods pdf(id=...)` files are written to WORK
  examples   the three example programs run with their default inputs
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sashiny_ref as ref  # noqa: E402

REPO = ref.SPEC_DIR.parent
FIX = ref.SPEC_DIR / "fixtures"
ODA_HOSTS = {
    "us1": ["odaws01-usw2.oda.sas.com", "odaws02-usw2.oda.sas.com"],
    "us2": ["odaws01-usw2-2.oda.sas.com", "odaws02-usw2-2.oda.sas.com"],
    "eu1": ["odaws01-euw1.oda.sas.com", "odaws02-euw1.oda.sas.com"],
    "ap1": ["odaws01-apse1.oda.sas.com", "odaws02-apse1.oda.sas.com"],
    "ap2": ["odaws01-apse1-2.oda.sas.com", "odaws02-apse1-2.oda.sas.com"],
}
CHECKS = ["env", "connect", "submit", "graphics", "roundtrip", "wrapper", "injection", "ods_ids", "examples"]
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


# --------------------------------------------------------------------------- report


@dataclass
class CheckResult:
    name: str
    status: str = "skipped"  # pass | fail | skipped
    seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class Report:
    profile: str
    started_utc: str
    platform: str
    results: list[CheckResult] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        out = {"pass": 0, "fail": 0, "skipped": 0}
        for r in self.results:
            out[r.status] += 1
        return out


# --------------------------------------------------------------------------- saspy config


def find_java() -> str | None:
    if os.environ.get("JAVA_HOME"):
        cand = Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if cand.exists():
            return str(cand)
    if sys.platform == "darwin" and Path("/usr/libexec/java_home").exists():
        try:
            home = subprocess.run(["/usr/libexec/java_home"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
            if home:
                return str(Path(home) / "bin" / "java")
        except (subprocess.SubprocessError, OSError):
            pass
    return shutil.which("java")


def build_cfg(args: argparse.Namespace) -> dict[str, Any]:
    if args.profile == "oda":
        return {
            "java": args.java or find_java(),
            "iomhost": ODA_HOSTS[args.oda_region],
            "iomport": 8591,
            "authkey": "oda",
            "encoding": "utf-8",
        }
    if args.profile == "viya":
        if not args.url:
            raise SystemExit("--url is required for --profile viya")
        cfg: dict[str, Any] = {"url": args.url, "authkey": "viya", "options": ["fullstimer"]}
        if args.context:
            cfg["context"] = args.context
        if args.no_verify_ssl:
            cfg["verify"] = False
        return cfg
    if args.profile == "iom":
        if not args.host:
            raise SystemExit("--host is required for --profile iom")
        return {"java": args.java or find_java(), "iomhost": args.host, "iomport": args.port, "authkey": "iom", "encoding": "utf-8"}
    if args.profile == "ssh":
        if not (args.host and args.saspath):
            raise SystemExit("--host and --saspath are required for --profile ssh")
        cfg = {
            "saspath": args.saspath,
            "ssh": shutil.which("ssh") or "/usr/bin/ssh",
            "host": args.host,
            "encoding": "utf-8",
            "options": ["-fullstimer"],
        }
        if args.ssh_user:
            cfg["luser"] = args.ssh_user
        return cfg
    raise SystemExit(f"unknown profile {args.profile}")


def write_cfgfile(cfg: dict[str, Any], folder: Path) -> Path:
    path = folder / "sascfg_sashiny_check.py"
    path.write_text(f"SAS_config_names = ['sashiny_check']\nsashiny_check = {cfg!r}\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- helpers


def classify_log(log: str) -> dict[str, int]:
    counts = {"error": 0, "warning": 0}
    for line in log.splitlines():
        if line.startswith("ERROR"):
            counts["error"] += 1
        elif line.startswith("WARNING"):
            counts["warning"] += 1
    return counts


def run_status(log: str, run_id: str = "fixture") -> tuple[str, int | None]:
    """Spec section 6.5."""
    m = re.search(rf"SASHINY-END run={re.escape(run_id)} syscc=(\d+)", log)
    if not m:
        return "error", None
    syscc = int(m.group(1))
    counts = classify_log(log)
    if syscc > 4 or counts["error"]:
        return "error", syscc
    if syscc == 4 or counts["warning"]:
        return "warning", syscc
    return "success", syscc


def read_macros(sas: Any, names: list[str]) -> dict[str, str]:
    """Read macro variable values back from SAS, removing macro-quoting delta characters."""
    if not names:
        return {}
    code = ["data work._sx_check;", "  length name $32 value $32767;"]
    for n in names:
        code.append(f"  name = '{n}'; value = symget('{n}'); output;")
    code.append("run;")
    sas.submit("\n".join(code), results="TEXT")
    df = sas.sd2df("_sx_check", libref="work")
    sas.submit("proc datasets library=work nolist nowarn; delete _sx_check; quit;", results="TEXT")
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        val = row["value"]
        val = "" if val is None or (isinstance(val, float) and val != val) else str(val)
        out[str(row["name"]).strip()] = CONTROL.sub("", val).rstrip()
    return out


def default_values(data: dict[str, Any], today: date) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    for iid, spec in (data.get("inputs") or {}).items():
        if spec["type"] == "dataset" or "default" not in spec:
            continue
        d = spec["default"]
        if spec["type"] in ("date", "daterange"):
            iso = today.isoformat()
            if isinstance(d, list):
                d = [iso if x == "today" else x for x in d]
            elif d == "today":
                d = iso
        vals[iid] = d
    return vals


def upload_sample(sas: Any, base: Path, spec: dict[str, Any]) -> None:
    import pandas as pd

    df = pd.read_csv(base / spec["sample"], dtype=str, keep_default_na=False)
    date_cols: dict[str, str] = {}
    for col in spec.get("columns", []):
        name = next(c for c in df.columns if c.upper() == col["name"].upper())
        if col["type"] == "numeric":
            df[name] = pd.to_numeric(df[name].replace("", None))
        elif col["type"] == "date":
            df[name] = pd.to_datetime(df[name].replace("", None), format="%Y-%m-%d")
            date_cols[name] = "date"
    libref, member = spec["target"].split(".")
    sas.df2sd(df, table=member, libref=libref, datetimes=date_cols)


def run_contract(sas: Any, contract: ref.Contract, values: dict[str, Any], uploads: dict[str, bool], today: date) -> dict[str, Any]:
    data = contract.data
    macros, issues = ref.render_values(data, values, today, uploads=uploads)
    if issues:
        return {"status": "invalid-values", "issues": [i.key() for i in issues]}
    if (data.get("run") or {}).get("reset_work", True):
        sas.submit(ref.reset_code(data), results="TEXT")
    for iid, spec in (data.get("inputs") or {}).items():
        if spec["type"] == "dataset" and uploads.get(iid) and "sample" in spec:
            upload_sample(sas, contract.base_dir, spec)
    program = (contract.base_dir / data["program"]).read_bytes()
    t0 = time.monotonic()
    res = sas.submit(ref.wrapper_code(data, macros, program), results="HTML")
    status, syscc = run_status(res["LOG"])
    got = read_macros(sas, list(macros))
    return {
        "status": status,
        "syscc": syscc,
        "seconds": round(time.monotonic() - t0, 2),
        "log_counts": classify_log(res["LOG"]),
        "graphs": res["LST"].count("<img") + res["LST"].count("<svg"),
        "macros_match": got == macros,
        "macro_mismatches": {k: {"expected": v, "sas": got.get(k)} for k, v in macros.items() if got.get(k) != v},
        "log_tail": res["LOG"].splitlines()[-25:] if status == "error" else [],
    }


# --------------------------------------------------------------------------- checks


def check_env(ctx: dict[str, Any], r: CheckResult) -> None:
    import pandas
    import saspy

    r.details = {"python": sys.version.split()[0], "saspy": saspy.__version__, "pandas": pandas.__version__}
    java = ctx["cfg"].get("java")
    if java:
        try:
            out = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=20)
            r.details["java"] = (out.stderr or out.stdout).splitlines()[0]
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Java not runnable at {java}: {exc}") from exc
    elif ctx["args"].profile in ("oda", "iom"):
        raise RuntimeError("Java 8+ is required for IOM connections; install it or pass --java")
    r.status = "pass"


def check_connect(ctx: dict[str, Any], r: CheckResult) -> None:
    import saspy

    sas = saspy.SASsession(cfgfile=str(ctx["cfgfile"]), cfgname="sashiny_check", results="HTML")
    ctx["sas"] = sas
    res = sas.submit("%put SXCHK VERSION=&sysvlong; %put SXCHK ENCODING=&sysencoding;", results="TEXT")
    r.details = {
        "sas_version": _grab(res["LOG"], "VERSION"),
        "encoding": _grab(res["LOG"], "ENCODING"),
        "access_method": getattr(sas, "sascfg", None) and sas.sascfg.mode,
    }
    r.status = "pass"


def check_submit(ctx: dict[str, Any], r: CheckResult) -> None:
    sas = ctx["sas"]
    ok = sas.submit("data work._sx_t; x = 1; run; proc datasets lib=work nolist; delete _sx_t; quit;", results="TEXT")
    bad = sas.submit("data work._sx_t; set work.does_not_exist_sx; run;", results="TEXT")
    r.details = {"clean_run": classify_log(ok["LOG"]), "failing_run": classify_log(bad["LOG"])}
    r.status = "pass" if r.details["clean_run"]["error"] == 0 and r.details["failing_run"]["error"] > 0 else "fail"


def check_graphics(ctx: dict[str, Any], r: CheckResult) -> None:
    res = ctx["sas"].submit("proc sgplot data=sashelp.class; scatter x=height y=weight; run;", results="HTML")
    n = res["LST"].count("<img") + res["LST"].count("<svg")
    r.details = {"graphs_in_html": n, "html_bytes": len(res["LST"])}
    r.status = "pass" if n >= 1 else "fail"


def check_roundtrip(ctx: dict[str, Any], r: CheckResult) -> None:
    import pandas as pd

    sas = ctx["sas"]
    df = pd.DataFrame(
        {
            "ID": ["S-001", "S-002", "S-003"],
            "NAME": ["Café", "日本", "O'Brien & Co"],
            "AGE": [54.0, None, 71.5],
            "VISIT": pd.to_datetime(["2026-01-15", "2026-02-28", None]),
        }
    )
    sas.df2sd(df, table="_sx_rt", libref="work", datetimes={"VISIT": "date"})
    back = sas.sd2df("_sx_rt", libref="work")
    sas.submit("proc datasets library=work nolist nowarn; delete _sx_rt; quit;", results="TEXT")
    problems = []
    if list(back["NAME"].str.rstrip()) != list(df["NAME"]):
        problems.append(f"NAME {list(back['NAME'])}")
    if not (pd.isna(back["AGE"][1]) and back["AGE"][2] == 71.5):
        problems.append(f"AGE {list(back['AGE'])}")
    visits = [None if pd.isna(v) else pd.Timestamp(v).date().isoformat() for v in back["VISIT"]]
    if visits != ["2026-01-15", "2026-02-28", None]:
        problems.append(f"VISIT {visits}")
    r.details = {"problems": problems, "dtypes": {k: str(v) for k, v in back.dtypes.items()}}
    r.status = "pass" if not problems else "fail"


def _run_wrapper_fixture(ctx: dict[str, Any], d: Path) -> dict[str, Any]:
    contract = ref.load(d / "contract.sashiny.yml")
    case = json.loads((d / "case.json").read_text(encoding="utf-8"))
    uploads = case.get("uploads", {})
    for iid in uploads:  # wrapper fixtures have no sample files; create a tiny stand-in table
        ctx["sas"].submit(f"data {contract.data['inputs'][iid]['target']}; usubjid = 'S-001'; run;", results="TEXT")
    return run_contract(ctx["sas"], contract, case["values"], uploads, date.fromisoformat(case["today"]))


def check_wrapper(ctx: dict[str, Any], r: CheckResult) -> None:
    out = {d.name: _run_wrapper_fixture(ctx, d) for d in sorted((FIX / "wrapper").iterdir())}
    r.details = out
    r.status = "pass" if all(v["status"] in ("success", "warning") and v["macros_match"] for v in out.values()) else "fail"


def check_injection(ctx: dict[str, Any], r: CheckResult) -> None:
    contract = ref.load(FIX / "contracts" / "valid" / "text" / "contract.sashiny.yml")
    cases = json.loads((FIX / "values" / "text.json").read_text(encoding="utf-8"))["cases"]
    out = {}
    for case in cases:
        if case["expected"]["status"] != "ok":
            continue
        res = run_contract(ctx["sas"], contract, case["values"], {}, date(2026, 11, 11))
        alive = ctx["sas"].submit("%put SXCHK ALIVE=1;", results="TEXT")["LOG"]
        res["session_alive"] = "SXCHK ALIVE=1" in alive
        out[case["name"]] = res
    r.details = out
    r.status = "pass" if all(v["status"] != "error" and v["macros_match"] and v["session_alive"] for v in out.values()) else "fail"


def check_ods_ids(ctx: dict[str, Any], r: CheckResult) -> None:
    sas = ctx["sas"]
    r.details["run"] = _run_wrapper_fixture(ctx, FIX / "wrapper" / "macro_entry_ods")
    names = ["sashiny_rtf_a.rtf", "sashiny_pdf_a.pdf", "sashiny_rtf_b.rtf"]
    code = ["data _null_;", "  length f $1024;"]
    for i, n in enumerate(names):
        code.append(f"  f = cats(pathname('work'), '/{n}'); e{i} = fileexist(f); call symputx('SXF{i}', e{i});")
    code.append("run;")
    code.extend(f"%put SXCHK F{i}=&SXF{i};" for i in range(len(names)))
    log = sas.submit("\n".join(code), results="TEXT")["LOG"]
    files = {n: _grab(log, f"F{i}") == "1" for i, n in enumerate(names)}
    r.details["files"] = files
    r.status = "pass" if all(files.values()) else "fail"


def check_examples(ctx: dict[str, Any], r: CheckResult) -> None:
    out = {}
    today = date.today()
    for yml in sorted((REPO / "examples").rglob("*.sashiny.yml")):
        contract = ref.load(yml)
        uploads = {iid: True for iid, s in (contract.data.get("inputs") or {}).items() if s["type"] == "dataset" and "sample" in s}
        out[str(yml.relative_to(REPO))] = run_contract(ctx["sas"], contract, default_values(contract.data, today), uploads, today)
    r.details = out
    r.status = (
        "pass" if all(v["status"] in ("success", "warning") and v["macros_match"] and v["graphs"] >= 1 for v in out.values()) else "fail"
    )


def _grab(log: str, key: str) -> str | None:
    m = re.search(rf"SXCHK {key}=(\S*)", log)
    return m.group(1) if m else None


CHECK_FUNCS: dict[str, Callable[[dict[str, Any], CheckResult], None]] = {
    "env": check_env,
    "connect": check_connect,
    "submit": check_submit,
    "graphics": check_graphics,
    "roundtrip": check_roundtrip,
    "wrapper": check_wrapper,
    "injection": check_injection,
    "ods_ids": check_ods_ids,
    "examples": check_examples,
}
NEEDS_SESSION = set(CHECKS) - {"env", "connect"}


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", required=True, choices=["oda", "viya", "iom", "ssh"])
    p.add_argument("--oda-region", default="us1", choices=sorted(ODA_HOSTS))
    p.add_argument("--url", help="Viya base URL")
    p.add_argument("--context", help="Viya compute context name")
    p.add_argument("--no-verify-ssl", action="store_true", help="Viya: do not verify TLS certificates")
    p.add_argument("--host")
    p.add_argument("--port", type=int, default=8591)
    p.add_argument("--saspath")
    p.add_argument("--ssh-user")
    p.add_argument("--java")
    p.add_argument("--only", nargs="+", choices=CHECKS, help="run only these checks (env and connect always run)")
    p.add_argument("--report", default=None, help="report path (default: sashiny-sas-check-<profile>.json)")
    args = p.parse_args(argv)

    selected = ["env", "connect"] + [c for c in CHECKS if c not in ("env", "connect") and (not args.only or c in args.only)]
    report = Report(
        profile=args.profile, started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), platform=platform.platform()
    )
    with tempfile.TemporaryDirectory() as tmp:
        cfg = build_cfg(args)
        ctx: dict[str, Any] = {"args": args, "cfg": cfg, "cfgfile": write_cfgfile(cfg, Path(tmp)), "sas": None}
        try:
            for name in selected:
                r = CheckResult(name)
                report.results.append(r)
                if name in NEEDS_SESSION and ctx["sas"] is None:
                    r.error = "no SAS session"
                    continue
                t0 = time.monotonic()
                try:
                    CHECK_FUNCS[name](ctx, r)
                except Exception as exc:  # report every failure, keep going
                    r.status = "fail"
                    r.error = f"{type(exc).__name__}: {exc}"
                    r.details.setdefault("traceback", traceback.format_exc().splitlines()[-6:])
                r.seconds = round(time.monotonic() - t0, 2)
                print(f"  {r.status.upper():7} {name:10} {r.seconds:6.1f}s  {r.error}")
        finally:
            if ctx["sas"] is not None:
                ctx["sas"].endsas()

    path = Path(args.report or f"sashiny-sas-check-{args.profile}.json")
    path.write_text(json.dumps(asdict(report), indent=2, default=str) + "\n", encoding="utf-8")
    s = report.summary()
    print(f"\n{s['pass']} passed, {s['fail']} failed, {s['skipped']} skipped. Report: {path.resolve()}")
    return 1 if s["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
