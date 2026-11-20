# Parent filter driving a contract

[`app.R`](app.R) and [`app.py`](app.py) show a filter panel in a parent module that drives the
[`cars_explorer`](../general/cars_explorer.sashiny.yml) contract through the module's `values`
argument (CONTRACT.md §6.10). The parent's origin selection replaces the module's own origin
control, which is hidden with `hide_inputs = TRUE`. The other inputs stay in the module UI. Because
`ui.auto_run` is set, each change of the filter starts a run after a 500 ms debounce. Values are
validated exactly like UI values (V001–V014).

Both apps connect to SAS OnDemand for Academics. Set `SASHINY_LICENSE_ACK=true` to confirm you are
licensed to use it (CONTRACT.md §6.6). The module behaviour is covered by the mock-engine tests in
`R/tests/testthat/test-mod-program.R` and `Python/tests/test_module_client.py`.
