"""Generate the synthetic monthly prescription data used by the Forecasting example.

Entirely synthetic: fictional products (Drug A, B, C) in three fictional regions
(West, Central, East). Each series is built as

    Y_t = L_t * (1 + S_t) + E_t + I_t,   L_t = L_{t-1} + beta + u_t

where L_t is the demand level (starting at mu, growing by beta a month, with a
small random drift u_t), S_t annual seasonality whose monthly factors change a
little from year to year, E_t autocorrelated AR(1) noise and I_t occasional
shocks (supply disruptions or demand spikes). The random drift in the level and
the seasonality is what makes differenced (S)ARIMA models a natural fit. This is
a simulation recipe, not the ARIMA model fitted later.

Scenarios:
  standard    moderate trend, mild seasonality, stable variance
  seasonal    pronounced annual cycle (winter peak), suited to SARIMA
  disruption  standard demand plus several drops and spikes
  mixed       one scenario per product (default): Drug A standard,
              Drug B seasonal, Drug C disruption

Deterministic: the same seed and scenario always produce an identical file.

    python examples/forecasting/data/generate_rx_data.py
    python examples/forecasting/data/generate_rx_data.py --scenario seasonal --seed 7 --out my.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCTS = ["Drug A", "Drug B", "Drug C"]
REGIONS = {"West": 1.00, "Central": 0.72, "East": 1.25}  # relative market size
MIXED = {"Drug A": "standard", "Drug B": "seasonal", "Drug C": "disruption"}
SCENARIOS = ["standard", "seasonal", "disruption", "mixed"]

# Per-product baseline (prescriptions per month in a size-1.00 region) and
# trend (share of the baseline gained or lost per year).
BASE = {"Drug A": 4200.0, "Drug B": 2600.0, "Drug C": 1800.0}
TREND = {"Drug A": 0.045, "Drug B": 0.020, "Drug C": -0.025}
# Seasonal amplitude (share of the level) by scenario.
SEASONAL_AMP = {"standard": 0.05, "seasonal": 0.22, "disruption": 0.05}


def _months(start_year: int, start_month: int, n: int) -> list[str]:
    out = []
    y, m = start_year, start_month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}-01")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _series(
    rng: random.Random, product: str, region: str, scenario: str, months: list[str]
) -> list[dict[str, object]]:
    """One product-region series of len(months) rows."""
    size = REGIONS[region]
    mu = BASE[product] * size * rng.uniform(0.92, 1.08)
    beta = mu * TREND[product] / 12 * rng.uniform(0.8, 1.2)
    amp = SEASONAL_AMP[scenario] * rng.uniform(0.85, 1.15)
    phase = rng.uniform(-0.4, 0.4)  # small regional shift of the seasonal peak
    phi, sigma = 0.45, 0.025 * mu  # AR(1) noise
    n = len(months)

    # Monthly seasonal factors: winter peak (January) with a smaller second
    # harmonic, then a small random change for each month every year.
    factors = [
        amp * (math.cos(2 * math.pi * k / 12 + phase) + 0.3 * math.cos(4 * math.pi * k / 12))
        for k in range(12)
    ]

    # Shocks: month index -> multiplicative effect (lasting a few months).
    shocks: dict[int, float] = {}
    n_shocks = rng.randint(3, 5) if scenario == "disruption" else (1 if rng.random() < 0.3 else 0)
    for _ in range(n_shocks):
        at = rng.randrange(12, n - 6)
        drop = rng.random() < 0.65
        size_ = -rng.uniform(0.25, 0.45) if drop else rng.uniform(0.20, 0.40)
        for k in range(rng.randint(1, 3)):
            shocks[at + k] = size_ * (0.6**k)

    rows = []
    e = 0.0
    level = mu
    for t, month in enumerate(months):
        moy = int(month[5:7])
        if t and moy == 1:
            factors = [f + rng.gauss(0.0, 0.012 + 0.15 * amp) for f in factors]
            mean = sum(factors) / 12
            factors = [f - mean for f in factors]
        s = factors[moy - 1]
        e = phi * e + rng.gauss(0.0, sigma)
        if t:
            level += beta + rng.gauss(0.0, 0.012 * mu)
        shock = shocks.get(t, 0.0)
        y = level * (1 + s) + e + level * shock
        rows.append(
            {
                "month": month,
                "product": product,
                "region": region,
                "prescriptions": max(0, round(y)),
                "shock_flag": 1 if shock else 0,
                "scenario": scenario,
            }
        )
    return rows


def generate(scenario: str = "mixed", seed: int = 42, n_months: int = 120) -> list[dict[str, object]]:
    """All 9 product-region series, sorted by product, region and month."""
    rng = random.Random(seed)
    months = _months(2016, 1, n_months)
    rows: list[dict[str, object]] = []
    for product in PRODUCTS:
        kind = MIXED[product] if scenario == "mixed" else scenario
        for region in REGIONS:
            rows.extend(_series(rng, product, region, kind, months))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=SCENARIOS, default="mixed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--months", type=int, default=120, help="months per series (default 120)")
    parser.add_argument("--out", type=Path, default=HERE / "demo_rx_monthly.csv")
    args = parser.parse_args()

    rows = generate(args.scenario, args.seed, args.months)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{args.out.name}: {len(rows)} rows ({args.scenario}, seed {args.seed})")


if __name__ == "__main__":
    main()
