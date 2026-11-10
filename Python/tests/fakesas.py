"""A fake saspy session for engine tests.

It understands exactly the submissions SAShiny makes (spec §6 and §8.2): the
reset, the wrapper, the table metadata and formatted steps, the path query,
the version query, the ``choices_from`` query and ``_sx_*`` clean-up. Data sets
are pandas data frames keyed by ``(LIB, MEM)``.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import pandas as pd

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
LST = (
    "<html><body><h1>Report</h1>"
    f'<img src="data:image/png;base64,{PNG}" alt="graph 1">'
    '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
    "</body></html>"
)

_WHERE = re.compile(r'libname = "(\w+)" and memname = "(\w+)"')
_SET = re.compile(r"set (\w+)\.(\w+)\(obs=(\d+) keep=([\w ]+)\);")
_RUN = re.compile(r"SASHINY-BEGIN run=(\S+);")
_PATH = re.compile(r"pathname\((\w+)\)")


class FakeSAS:
    """Records submissions and answers them like a SAS session would."""

    def __init__(  # noqa: PLR0913 - test double with many knobs
        self,
        datasets: dict[tuple[str, str], pd.DataFrame] | None = None,
        *,
        meta: dict[tuple[str, str], list[dict[str, str]]] | None = None,
        files: dict[str, bytes] | None = None,
        program_log: str = "NOTE: The data set WORK.OUT has 2 observations.",
        syscc: int = 0,
        lst: str = LST,
    ) -> None:
        self.datasets = dict(datasets or {})
        self.meta = meta or {}
        self.files = files or {}
        self.program_log = program_log
        self.syscc = syscc
        self.lst = lst
        self.submitted: list[str] = []
        self.uploaded: dict[tuple[str, str], tuple[pd.DataFrame, dict[str, str]]] = {}
        self.ended = False

    # -------------------------------------------------------------- saspy API

    def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
        self.submitted.append(code)
        m = _RUN.search(code)
        if m:
            log = (
                f"1    %put NOTE: SASHINY-BEGIN run={m.group(1)};\n"
                f"NOTE: SASHINY-BEGIN run={m.group(1)}\n"
                "NOTE: SASHINY-BEGIN-PROGRAM\n"
                f"{self.program_log}\n"
                "NOTE: SASHINY-END-PROGRAM\n"
                f"NOTE: SASHINY-END run={m.group(1)} syscc={self.syscc}\n"
            )
            return {"LOG": log, "LST": self.lst}
        if "_sx_cols" in code:
            self._meta_step(code)
        elif "data work._sx_fmt;" in code:
            self._fmt_step(code)
        elif "_sx_choices as" in code:
            self._choices_step(code)
        elif "SXVER=" in code:
            return {"LOG": "SXVER=9.04.01M8P011923\n", "LST": ""}
        elif "SASHINY-PATH=" in code:
            lib = _PATH.search(code)
            assert lib is not None
            return {"LOG": f"1 %put ...\nSASHINY-PATH=/sas/{lib.group(1).lower()}\n", "LST": ""}
        elif "delete _sx_" in code:
            for key in [k for k in self.datasets if k[0] == "WORK" and k[1].startswith("_SX_")]:
                del self.datasets[key]
        return {"LOG": "", "LST": ""}

    def sd2df(self, table: str, libref: str = "WORK", dsopts: dict[str, Any] | None = None) -> Any:
        df = self.datasets.get((libref.upper(), table.upper()))
        if df is None:
            return None
        if dsopts:
            keep = dsopts.get("keep")
            if keep:
                lookup = {c.upper(): c for c in df.columns}
                df = df[[lookup[k.upper()] for k in keep.split()]]
            df = df.head(int(dsopts.get("obs", len(df))))
        return df.copy()

    def df2sd(self, df: pd.DataFrame, table: str, libref: str, datetimes: dict[str, str]) -> None:
        self.uploaded[(libref.upper(), table.upper())] = (df, datetimes)
        self.datasets[(libref.upper(), table.upper())] = df

    def download(self, localfile: str, remotefile: str, overwrite: bool = True) -> dict[str, Any]:
        if remotefile not in self.files:
            return {"Success": False, "LOG": f"ERROR: {remotefile} not found"}
        Path(localfile).write_bytes(self.files[remotefile])
        return {"Success": True, "LOG": ""}

    def endsas(self) -> None:
        self.ended = True

    # -------------------------------------------------------------- helpers

    def _meta_step(self, code: str) -> None:
        m = _WHERE.search(code)
        assert m is not None
        key = (m.group(1), m.group(2))
        df = self.datasets.get(key)
        if df is None:
            self.datasets[("WORK", "_SX_COLS")] = pd.DataFrame(
                columns=["varnum", "name", "type", "format", "label"]
            )
            self.datasets[("WORK", "_SX_NOBS")] = pd.DataFrame(columns=["nlobs"])
            return
        extra = {d["name"].upper(): d for d in self.meta.get(key, [])}
        rows = []
        for i, col in enumerate(df.columns, start=1):
            info = extra.get(str(col).upper(), {})
            kind = "num" if pd.api.types.is_numeric_dtype(df[col]) else "char"
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                kind = "num"
            rows.append(
                {
                    "varnum": i,
                    "name": str(col).upper() if info.get("upper") else str(col),
                    "type": kind,
                    "format": info.get("format", ""),
                    "label": info.get("label", ""),
                }
            )
        self.datasets[("WORK", "_SX_COLS")] = pd.DataFrame(rows)
        self.datasets[("WORK", "_SX_NOBS")] = pd.DataFrame({"nlobs": [float(len(df))]})

    def _fmt_step(self, code: str) -> None:
        m = _SET.search(code)
        assert m is not None
        df = self.datasets[(m.group(1), m.group(2))].head(int(m.group(3)))
        lookup = {c.upper(): c for c in df.columns}
        out = pd.DataFrame(
            {
                f"_sx_c{i}": [f"fmt:{v}" for v in df[lookup[col.upper()]]]
                for i, col in enumerate(m.group(4).split(), start=1)
            }
        )
        self.datasets[("WORK", "_SX_FMT")] = out

    def _choices_step(self, code: str) -> None:
        m = re.search(r"select distinct ([\w, ]+)\n\s*from (\w+)\.(\w+)", code)
        assert m is not None
        cols = [c.strip() for c in m.group(1).split(",")]
        df = self.datasets[(m.group(2).upper(), m.group(3).upper())]
        lookup = {c.upper(): c for c in df.columns}
        picked = df[[lookup[c.upper()] for c in cols]].drop_duplicates()
        picked = picked.sort_values(lookup[cols[0].upper()])
        self.datasets[("WORK", "_SX_CHOICES")] = picked.reset_index(drop=True)
