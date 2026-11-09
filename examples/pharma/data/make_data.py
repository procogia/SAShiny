"""Generate the synthetic ADSL and ADAE sample files used by the pharma example.

The data are entirely synthetic (no real subjects). They follow CDISC ADaM
variable naming so the example reads like a real safety analysis.
Deterministic: running this script always produces identical files.

    python examples/pharma/data/make_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ["Placebo", "Xanomeline Low Dose", "Xanomeline High Dose"]
AE_TERMS = [
    ("GENERAL DISORDERS AND ADMINISTRATION SITE CONDITIONS", "APPLICATION SITE PRURITUS", (0.06, 0.22, 0.27)),
    ("GENERAL DISORDERS AND ADMINISTRATION SITE CONDITIONS", "APPLICATION SITE ERYTHEMA", (0.04, 0.16, 0.18)),
    ("GENERAL DISORDERS AND ADMINISTRATION SITE CONDITIONS", "FATIGUE", (0.05, 0.06, 0.07)),
    ("SKIN AND SUBCUTANEOUS TISSUE DISORDERS", "PRURITUS", (0.08, 0.20, 0.24)),
    ("SKIN AND SUBCUTANEOUS TISSUE DISORDERS", "ERYTHEMA", (0.09, 0.15, 0.17)),
    ("SKIN AND SUBCUTANEOUS TISSUE DISORDERS", "RASH", (0.06, 0.11, 0.10)),
    ("NERVOUS SYSTEM DISORDERS", "DIZZINESS", (0.03, 0.10, 0.13)),
    ("NERVOUS SYSTEM DISORDERS", "HEADACHE", (0.04, 0.04, 0.06)),
    ("GASTROINTESTINAL DISORDERS", "DIARRHOEA", (0.10, 0.05, 0.05)),
    ("GASTROINTESTINAL DISORDERS", "NAUSEA", (0.04, 0.03, 0.07)),
    ("CARDIAC DISORDERS", "SINUS BRADYCARDIA", (0.02, 0.09, 0.11)),
    ("INFECTIONS AND INFESTATIONS", "NASOPHARYNGITIS", (0.03, 0.05, 0.07)),
]


def main() -> None:
    rng = random.Random(20261111)
    adsl, adae = [], []
    for i in range(1, 181):
        arm = ARMS[(i - 1) % 3]
        usubjid = f"SX01-{i:04d}"
        trtsdt = date(2025, 1, 6) + timedelta(days=rng.randint(0, 120))
        saffl = "N" if rng.random() < 0.03 else "Y"
        adsl.append(
            {
                "STUDYID": "SX01",
                "USUBJID": usubjid,
                "TRT01A": arm,
                "SAFFL": saffl,
                "AGE": rng.randint(51, 88),
                "SEX": rng.choice(["F", "M"]),
                "RACE": rng.choices(["WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN"], [0.84, 0.10, 0.06])[0],
                "TRTSDT": trtsdt.isoformat(),
            }
        )
        arm_idx = ARMS.index(arm)
        for soc, pt, probs in AE_TERMS:
            if rng.random() < probs[arm_idx]:
                astdt = trtsdt + timedelta(days=rng.randint(-5, 168))
                adae.append(
                    {
                        "STUDYID": "SX01",
                        "USUBJID": usubjid,
                        "AEBODSYS": soc,
                        "AEDECOD": pt,
                        "ASTDT": astdt.isoformat(),
                        "TRTEMFL": "Y" if astdt >= trtsdt else "N",
                        "AESEV": rng.choices(["MILD", "MODERATE", "SEVERE"], [0.65, 0.30, 0.05])[0],
                    }
                )
    _write(HERE / "adsl.csv", adsl)
    _write(HERE / "adae.csv", adae)
    print(f"adsl.csv: {len(adsl)} rows, adae.csv: {len(adae)} rows")


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
