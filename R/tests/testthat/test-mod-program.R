# Tests for the Shiny modules (issue #8).

test_that("sas_program_ui returns a tagList", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  ui <- sas_program_ui("mod", contract)
  expect_s3_class(ui, "shiny.tag.list")
})

test_that("sas_program_server runs a contract and returns reactives", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(run = 1)
      expect_identical(result()$status, "success")
      expect_identical(result()$log, "")
    }
  )
})

test_that("sas_program_server collects inputs from a numeric contract", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(min_msrp = 20000, ratio = 0.5, big = 1)
      session$setInputs(run = 1)
      expect_identical(result()$status, "success")
    }
  )
})

test_that("sas_program_server reports invalid values", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(min_msrp = "not-a-number", ratio = 0.5, big = 1)
      session$setInputs(run = 1)
      expect_identical(result()$status, "error")
    }
  )
})