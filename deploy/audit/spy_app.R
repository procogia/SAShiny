library(shiny)
library(SAShiny)
root <- "/tmp/audit"
emit <- function(event,token) {
  cat(jsonlite::toJSON(list(event=event,token=token,time=as.numeric(Sys.time())),auto_unbox=TRUE),
      "\n",file=file.path(root,"r-events.jsonl"),append=TRUE,sep="")
}
spy <- function(choice_mode="ok") structure(list(mode=choice_mode),class="audit_spy")
choices <- function(engine,contract) {
  if (engine$mode=="error") stop("synthetic choices unavailable")
  if (engine$mode=="slow") Sys.sleep(1)
  list(selected=list(list(value="a",label="Alpha"),list(value="b",label="Beta")))
}
run <- function(engine,contract,values,today=Sys.Date(),uploads=NULL,run_id=NULL) {
  emit("started",values$token)
  Sys.sleep(min(values$delay,2))
  emit("completed",values$token)
  if (values$failure=="raise") stop("synthetic engine exception")
  r <- sas_engine_run(sas_engine_mock(choices=choices(engine,contract)),contract,values,today,uploads,run_id)
  if (r$status=="error" || values$failure=="result") {
    r$status <- "error"
    r$metadata$engine_error <- "synthetic result error"
    return(r)
  }
  r$outputs <- list(
    table=list(columns=list(list(name="value",type="numeric",label="",format="")),
               rows=list(list(7)),total_rows=1,truncated=FALSE,formatted=FALSE),
    report=list(list(level="note",text=values$token)),
    csv=list(filename="audit.csv",mime="text/csv",data=openssl::base64_encode(charToRaw("value\n7\n")))
  )
  r
}
registerS3method("sas_engine_run","audit_spy",run,envir=asNamespace("SAShiny"))
registerS3method("sas_engine_choices","audit_spy",choices,envir=asNamespace("SAShiny"))
contracts <- jsonlite::fromJSON(file.path(root,"spy_contracts.json"),simplifyVector=FALSE)
contracts <- lapply(contracts,function(d) structure(list(data=d,base_dir=root),class="sashiny_contract"))
tabs <- lapply(names(contracts),function(k) tabPanel(k,sas_program_ui(k,contracts[[k]])))
ui <- do.call(navbarPage,c(list("R audit"),tabs))
server <- function(input,output,session) {
  for (k in names(contracts)) {
    engine <- spy(if (k=="broken") "error" else if (k=="slowchoices") "slow" else "ok")
    sas_program_server(k,contracts[[k]],engine)
  }
  session$onSessionEnded(function() emit("session_ended",session$token))
}
shinyApp(ui,server)
