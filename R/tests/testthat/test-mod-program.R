# Tests for the Shiny modules (issue #8).

test_that("sas_program_ui returns a tagList", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  ui <- sas_program_ui("mod", contract)
  expect_s3_class(ui, "shiny.tag.list")
})

test_that("sas_program_server runs a contract", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(run = 1)
      expect_identical(result()$status, "success")
    }
  )
})