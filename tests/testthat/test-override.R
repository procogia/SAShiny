# Tests for the custom-module override.

test_that("sas_program_ui accepts a custom override", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  custom_ui <- function(id, contract) {
    shiny::h3("custom")
  }
  ui <- sas_program_ui("mod", contract, ui_override = custom_ui)
  expect_s3_class(ui, "shiny.tag")
  expect_identical(ui$name, "h3")
})

test_that("sas_program_server accepts a custom override", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  custom_server <- function(id, contract, engine) {
    list(custom = TRUE)
  }
  result <- sas_program_server("mod", contract, engine, server_override = custom_server)
  expect_identical(result$custom, TRUE)
})