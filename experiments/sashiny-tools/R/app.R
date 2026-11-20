# shinychat demo: a chat model calls the cars_explorer contract as a tool.
# Needs 'ellmer', 'shinychat', an LLM API key (for example OPENAI_API_KEY) and a
# licensed SAS system; set SASHINY_LICENSE_ACK=true to confirm the licence.
# The mock engine is a test fixture and is only used by tests/.
library(shiny)
library(SAShiny)
source("sashiny_tools.R")

contract <- sas_contract("../../../examples/general/cars_explorer.sashiny.yml")
engine <- sas_connect(sas_oda(), license_ack = identical(Sys.getenv("SASHINY_LICENSE_ACK"), "true"))

ui <- bslib::page_fillable(shinychat::chat_ui("chat"))

server <- function(input, output, session) {
  chat <- ellmer::chat_openai(system_prompt = paste(
    "Answer questions about car prices by calling the cars_explorer tool.",
    "Never write SAS code. Quote the run_id of every run you use."
  ))
  chat$register_tool(sas_as_tool(contract, engine))
  observeEvent(input$chat_user_input, {
    shinychat::chat_append("chat", chat$stream_async(input$chat_user_input))
  })
}

shinyApp(ui, server)