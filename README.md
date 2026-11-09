# SAShiny

Use an **unchanged SAS program** as the **server** of a Shiny app, with Shiny (R or Python) handling the UI.
A sidecar YAML contract declares the program's inputs and outputs, and SAShiny does the rest.

> Status: pre-alpha. Phase 1 (contract specification) is complete. See [PLAN.md](PLAN.md).

```
analysis.sas            # your SAS program — never modified
analysis.sashiny.yml    # the contract: inputs → macro variables, outputs → tables/plots/log/downloads
```

| Folder | Contents |
|---|---|
| [`R/`](R) | R package (target: CRAN) |
| [`Python/`](Python) | Python library (target: PyPI) |
| [`spec/`](spec) | The contract: [CONTRACT.md](spec/CONTRACT.md), [JSON Schema](spec/sashiny.schema.json), conformance fixtures |
| [`examples/`](examples) | Demo programs: general (`sashelp.cars`), pharma (TEAE summary), AML (threshold tuning) |

## Development

```sh
# contract fixtures
uv run --no-project --with jsonschema --with pyyaml python spec/tools/check_spec.py
# R package
R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz
# Python library
cd Python && uv sync && uv run ruff check . && uv run mypy && uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © 2026 Mehar Pratap Singh. Development funded by ProCogia.

---
SAS is a registered trademark of SAS Institute Inc. Shiny is a registered trademark of Posit Software, PBC.
This project is not affiliated with or endorsed by either company.
