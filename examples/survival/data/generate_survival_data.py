"""Generate the synthetic clinical trial data used by the Survival example.

Entirely synthetic: a fictional randomized trial of RX-101 added to standard
cancer treatment, versus standard treatment alone (Control). The endpoint is
progression-free survival (PFS): months from randomization to progression or
death, whichever comes first. Patients without an event are censored at the
data cutoff (administrative censoring) or when they were lost to follow-up.

Each scenario is written as its own study (STUDYID), so one pair of files holds
every scenario and the app selects a study:

  standard  RX101-STD   moderate benefit, true hazard ratio 0.70
  null      RX101-NULL  no treatment effect, true hazard ratio 1.00
  nph       RX101-NPH   non-proportional hazards: no effect for the first
                        6 months, then a hazard ratio of 0.45 (a delayed
                        effect, so the Cox proportional hazards assumption
                        does not hold for treatment)

Event times follow a Weibull proportional hazards model (shape 1.2) with
prognostic effects of age, sex, stage and ECOG performance status:

    h(t | x) = lambda * k * t^(k-1) * exp(b_trt*trt + 0.02*(age-62) + 0.15*male
                                           + 0.45*[II] + 0.95*[III]
                                           + 0.30*[ECOG 1] + 0.70*[ECOG 2])

Accrual is uniform over the first 18 months from 2023-01-02 and the data cutoff
is 36 months after the first randomization. Loss to follow-up is exponential
(2-4% of patients). Dates are consistent: ADT = RANDDT + days on study, and
AVAL = days / 30.4375. The two files use ADaM-like names (ADSL, ADTTE, with
CNSR = 0 for an event and 1 for censoring).

Deterministic: the same seed and scenarios always produce identical files.

    python examples/survival/data/generate_survival_data.py
    python examples/survival/data/generate_survival_data.py --scenario standard --n 300 --seed 7 --out-dir /tmp/rx
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = {
    # name: (STUDYID, hazard ratio before DELAY months, hazard ratio after)
    "standard": ("RX101-STD", 0.70, 0.70),
    "null": ("RX101-NULL", 1.00, 1.00),
    "nph": ("RX101-NPH", 1.00, 0.45),
}
DELAY = 6.0  # months, nph scenario only
SHAPE = 1.2  # Weibull shape k
MEDIAN_REF = 27.0  # baseline median PFS (months) of the reference patient
LAMBDA = math.log(2) / MEDIAN_REF**SHAPE  # Weibull scale: H0(t) = LAMBDA * t^k
LTFU_RATE = 0.0025  # per month
DAYS_PER_MONTH = 30.4375
FIRST_RAND = date(2023, 1, 2)
ACCRUAL_MONTHS = 18
CUTOFF = FIRST_RAND + timedelta(days=round(36 * DAYS_PER_MONTH))
REGIONS = [("North America", 0.35), ("Europe", 0.40), ("Asia Pacific", 0.25)]
STAGES = [("I", 0.25), ("II", 0.45), ("III", 0.30)]
ECOGS = [(0, 0.45), (1, 0.40), (2, 0.15)]
BETA = {"age": 0.02, "male": 0.15, "II": 0.45, "III": 0.95, "ecog1": 0.30, "ecog2": 0.70}

ADSL_FIELDS = ["STUDYID", "USUBJID", "TRT01A", "AGE", "SEX", "STAGE", "ECOG", "REGION", "ITTFL", "RANDDT"]
ADTTE_FIELDS = [
    "STUDYID", "USUBJID", "PARAMCD", "PARAM", "AVAL", "AVALU", "CNSR", "EVNTDESC", "STARTDT", "ADT",
]  # fmt: skip


def _pick(rng: random.Random, options: list[tuple[object, float]]) -> object:
    u = rng.random()
    acc = 0.0
    for value, p in options:
        acc += p
        if u < acc:
            return value
    return options[-1][0]


def _event_time(rng: random.Random, risk: float, treated: bool, hr_early: float, hr_late: float) -> float:
    """Months to progression or death, by inverting the cumulative hazard."""
    e = -math.log(1.0 - rng.random())  # unit exponential
    c = risk * (hr_early if treated else 1.0)
    h_delay = LAMBDA * DELAY**SHAPE  # baseline cumulative hazard at DELAY
    if not treated or hr_early == hr_late or e <= h_delay * c:
        return (e / (LAMBDA * c)) ** (1 / SHAPE)
    c_late = risk * hr_late
    h0 = h_delay + (e - h_delay * c) / c_late
    return (h0 / LAMBDA) ** (1 / SHAPE)


def _study(rng: random.Random, scenario: str, n: int) -> tuple[list[dict], list[dict]]:
    studyid, hr_early, hr_late = SCENARIOS[scenario]
    adsl: list[dict] = []
    adtte: list[dict] = []
    arms: list[str] = []
    for i in range(1, n + 1):
        if not arms:  # permuted blocks of 4, 1:1
            arms = ["Control", "Control", "RX-101", "RX-101"]
            rng.shuffle(arms)
        arm = arms.pop()
        age = min(85, max(30, round(rng.gauss(62, 10))))
        sex = "F" if rng.random() < 0.48 else "M"
        stage = str(_pick(rng, STAGES))
        ecog = int(_pick(rng, ECOGS))  # type: ignore[call-overload]
        region = str(_pick(rng, REGIONS))
        itt = "N" if rng.random() < 0.02 else "Y"  # randomized in error
        randdt = FIRST_RAND + timedelta(days=rng.randrange(round(ACCRUAL_MONTHS * DAYS_PER_MONTH)))

        lp = BETA["age"] * (age - 62) + BETA["male"] * (sex == "M")
        lp += BETA.get(stage, 0.0) + BETA["ecog1"] * (ecog == 1) + BETA["ecog2"] * (ecog == 2)
        t_event = _event_time(rng, math.exp(lp), arm == "RX-101", hr_early, hr_late)
        t_ltfu = -math.log(1.0 - rng.random()) / LTFU_RATE
        admin_days = (CUTOFF - randdt).days

        event_days = max(1, math.ceil(t_event * DAYS_PER_MONTH))
        ltfu_days = max(1, math.ceil(t_ltfu * DAYS_PER_MONTH))
        days = min(event_days, ltfu_days, admin_days)
        if days == event_days:
            cnsr, desc = 0, ("Death" if rng.random() < 0.18 else "Disease progression")
        elif days == ltfu_days:
            cnsr, desc = 1, "Lost to follow-up"
        else:
            cnsr, desc = 1, "Study end (data cutoff)"

        usubjid = f"{studyid}-{i:04d}"
        adsl.append(
            {
                "STUDYID": studyid,
                "USUBJID": usubjid,
                "TRT01A": arm,
                "AGE": age,
                "SEX": sex,
                "STAGE": stage,
                "ECOG": ecog,
                "REGION": region,
                "ITTFL": itt,
                "RANDDT": randdt.isoformat(),
            }
        )
        adtte.append(
            {
                "STUDYID": studyid,
                "USUBJID": usubjid,
                "PARAMCD": "PFS",
                "PARAM": "Progression-free survival (months)",
                "AVAL": f"{days / DAYS_PER_MONTH:.2f}",
                "AVALU": "MONTHS",
                "CNSR": cnsr,
                "EVNTDESC": desc,
                "STARTDT": randdt.isoformat(),
                "ADT": (randdt + timedelta(days=days)).isoformat(),
            }
        )
    return adsl, adtte


def generate(scenarios: list[str], n: int = 600, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """ADSL and ADTTE rows for each scenario, one study per scenario."""
    adsl: list[dict] = []
    adtte: list[dict] = []
    for k, scenario in enumerate(SCENARIOS):
        if scenario not in scenarios:
            continue
        # Each study has its own stream, so a study does not change when others are added.
        a, t = _study(random.Random(seed * 1000 + k), scenario, n)
        adsl += a
        adtte += t
    return adsl, adtte


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    parser.add_argument("--n", type=int, default=600, help="patients per study (default 600)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=HERE)
    args = parser.parse_args()

    chosen = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    adsl, adtte = generate(chosen, args.n, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write(args.out_dir / "adsl.csv", ADSL_FIELDS, adsl)
    _write(args.out_dir / "adtte.csv", ADTTE_FIELDS, adtte)
    events = sum(r["CNSR"] == 0 for r in adtte)
    print(
        f"adsl.csv, adtte.csv: {len(adsl)} subjects, {events} events "
        f"({', '.join(chosen)}; {args.n} per study, seed {args.seed})"
    )


if __name__ == "__main__":
    main()
