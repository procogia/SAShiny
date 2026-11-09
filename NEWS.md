# SAShiny 0.1.0

* Added the contract loader and validator (`sas_contract()`, `sas_validate()`)
  implementing spec sections 1-3 (E000, S001-S016).
* Added value validation and rendering (`sas_render_values()`) implementing
  spec sections 4-5 (V001-V014).
* Added the generated SAS wrapper (`sas_reset_code()`, `sas_wrapper_code()`)
  implementing spec section 6.
* Added advisory lint (`sashiny_lint()`) as a stub for spec section 10.
* Added the mock engine (`sas_engine_mock()`) and result object
  (`sashiny_result()`).
* Added the saspy engine (`sas_engine_saspy()`, `sas_connect()`) with
  selectable connection profiles (ODA, Viya, SAS 9.4).
* Added the bounded session pool (`sas_pool()`).
* Added the runner (`sas_run()`) and app helper (`sas_app()`).
* Added the Shiny modules (`sas_program_ui()`, `sas_program_server()`) with
  auto-generated UI and custom override.
