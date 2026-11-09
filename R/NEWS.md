# SAShiny (development version)

* Added the contract loader and validator (`sas_contract()`, `sas_validate()`)
  implementing spec sections 1-3 (E000, S001-S016).
* Added value validation and rendering (`sas_render_values()`) implementing
  spec sections 4-5 (V001-V014).
* Added the generated SAS wrapper (`sas_reset_code()`, `sas_wrapper_code()`)
  implementing spec section 6.
* Added advisory lint (`sashiny_lint()`) as a stub for spec section 10.
