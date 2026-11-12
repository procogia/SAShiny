# SAShiny

Use an **unchanged SAS program** as the **server** of a Shiny app, with Shiny (R or Python) handling the UI.
A sidecar YAML contract declares the program's inputs and outputs, and SAShiny does the rest.

> Status: beta (R 0.1.2, Python 0.1.3). Core, saspy engine, Shiny modules and client-side charts
> implemented. See [PLAN.md](PLAN.md).
>
> **Live SAS is not yet verified.** Every automated check uses the mock engine. The
> saspy connection profiles (ODA, Viya, SAS 9.4) have not been run against real SAS
> yet; that work is tracked in [#11](https://github.com/procogia/SAShiny/issues/11).

```
analysis.sas            # your SAS program — never modified
analysis.sashiny.yml    # the contract: inputs → macro variables, outputs → tables/plots/log/downloads
```

| Folder | Contents |
|---|---|
| [`R/`](R) | R package (target: CRAN) |
| [`Python/`](Python) | Python library (target: PyPI) |
| [`spec/`](spec) | The contract: [CONTRACT.md](spec/CONTRACT.md), [JSON Schema](spec/sashiny.schema.json), conformance fixtures |
| [`examples/`](examples) | Demo programs: general (`sashelp.cars`), pharma (TEAE summary), AML (threshold tuning), forecasting (ARIMA / SARIMA) |

## Development

```sh
# contract fixtures
uv run --no-project --python 3.12 --with jsonschema --with pyyaml python spec/tools/check_spec.py
# R package
R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz
# Python library
cd Python && uv sync && uv run ruff check . && uv run mypy && uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Maintainers

- Mehar Pratap Singh (author, maintainer)
- Shreya Sharma
- Love ProCogia
- Igor ProCogia
- Ahmer Khan

See [docs/HANDOFF.md](docs/HANDOFF.md) for the current state and the path to CRAN/PyPI.

## License

MIT © 2026 Mehar Pratap Singh. Development funded by ProCogia.

---
SAS is a registered trademark of SAS Institute Inc. Shiny is a registered trademark of Posit Software, PBC.
This project is not affiliated with or endorsed by either company.
