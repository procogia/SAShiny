"""Generate the synthetic transaction file used by the AML example.

Entirely synthetic. A small share of customers are flagged as having a prior
suspicious activity report (SAR_FLAG = 1); they tend to make more and larger
cash deposits, which is what a cash-aggregation scenario should catch.
Deterministic: running this script always produces an identical file.

    python examples/aml/data/make_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEGMENTS = {"Retail": (0.70, 900.0), "SME": (0.22, 3500.0), "Corporate": (0.08, 9000.0)}
TYPES = ["CASH_DEPOSIT", "WIRE_IN", "WIRE_OUT", "CARD"]
START, DAYS = date(2026, 1, 1), 181


def main() -> None:
    rng = random.Random(20261111)
    rows = []
    txn = 0
    for c in range(1, 401):
        segment = rng.choices(list(SEGMENTS), [w for w, _ in SEGMENTS.values()])[0]
        base = SEGMENTS[segment][1]
        sar = 1 if rng.random() < 0.06 else 0
        n_txn = rng.randint(8, 30) + (12 if sar else 0)
        for _ in range(n_txn):
            txn += 1
            ttype = rng.choices(TYPES, [0.55 if sar else 0.35, 0.2, 0.2, 0.25 if not sar else 0.05])[0]
            amount = rng.lognormvariate(0, 0.6) * base * (2.2 if sar and ttype == "CASH_DEPOSIT" else 1.0)
            rows.append(
                {
                    "TXN_ID": f"T{txn:07d}",
                    "CUSTOMER_ID": f"C{c:05d}",
                    "SEGMENT": segment,
                    "TXN_TYPE": ttype,
                    "TXN_DATE": (START + timedelta(days=rng.randrange(DAYS))).isoformat(),
                    "AMOUNT": f"{amount:.2f}",
                    "SAR_FLAG": sar,
                }
            )
    rows.sort(key=lambda r: (r["TXN_DATE"], r["TXN_ID"]))
    with (HERE / "transactions.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"transactions.csv: {len(rows)} rows")


if __name__ == "__main__":
    main()
