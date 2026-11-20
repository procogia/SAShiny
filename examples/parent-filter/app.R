# A parent filter panel drives the cars_explorer contract (CONTRACT.md 6.10).
# The module's own origin control is hidden; its other inputs stay in the UI.
# Runs on SAS OnDemand for Academics; set SASHINY_LICENSE_ACK=true to confirm
# you are licensed to use it (CONTRACT.md 6.6).
library(shiny)
library(SAShiny)

contract <- sas_contract("../general/cars_explorer.sashiny.yml")
contract$data$ui$auto_run <- TRUE
engine <- sas_connect("oda", license_ack = identical(Sys.getenv("SASHINY_LICENSE_ACK"), "true"))

filter_ui <- function(id) {
  checkboxGroupInput(NS(id, "origins"), "Origin (parent filter)",
    choices = c("Asia", "Europe", "USA"), selected = c("Asia", "Europe", "USA"), inline = TRUE
  )
}

filter_server <- function(id) {
  moduleServer(id, function(input, output, session) {
    reactive(list(origins = as.list(input$origins %||% character(0))))
  })
}

ui <- fluidPage(
  titlePanel("Cars explorer driven by a parent filter"),
  filter_ui("filter"),
  sas_program_ui("cars", contract)
)

server <- function(input, output, session) {
  values <- filter_server("filter")
  sas_program_server("cars", contract, engine, values = values, hide_inputs = TRUE)
}

shinyApp(ui, server)
