library(SAShiny)
library(jsonlite)
`%||%` <- function(x, y) if (is.null(x)) y else x
internal <- function(name) getFromNamespace(paste0(".sashiny_", name), "SAShiny")
object <- function(x) if (length(x) == 0L) structure(list(), names = character()) else x
issues <- function(x) lapply(x, unclass)
frame_value <- function(df) {
  rows <- lapply(seq_len(nrow(df)), function(i) unname(lapply(df, function(col) {
    x <- col[i]
    if (is.na(x)) NULL else if (inherits(x, c("Date", "POSIXt"))) as.character(x) else unname(x)
  })))
  list(columns = as.list(names(df)), dtypes = unname(lapply(df, function(c) class(c)[1])), rows = rows)
}
fix_result <- function(x) {
  x <- unclass(x)
  x$outputs <- object(x$outputs)
  if (!is.null(x$metadata$macros)) x$metadata$macros <- object(x$metadata$macros)
  x
}
upload_args <- function(p) lapply(p$uploads %||% list(), function(v) {
  if (is.character(v)) file.path(p$folder, v) else v
})

pool_case <- function(p, contract) {
  counts <- new.env()
  counts$created <- counts$closed <- counts$runs <- 0L
  scenario <- p$scenario %||% "reuse"
  factory <- function() {
    counts$created <- counts$created + 1L
    if (scenario == "factory_error") stop("synthetic factory failure")
    structure(list(counts = counts, scenario = scenario), class = "audit_pool_engine")
  }
  run <- function(engine, contract, values, today = Sys.Date(), uploads = NULL, run_id = NULL) {
    counts$runs <- counts$runs + 1L
    if (scenario == "raised_engine") stop("synthetic transport failure")
    result <- sas_engine_run(sas_engine_mock(), contract, values, today, uploads, run_id)
    if (scenario == "error") result$status <- "error"
    if (scenario == "validation") {
      result$status <- "error"
      result$metadata$issues <- list(list(code = "V001", input = "x"))
    }
    result
  }
  close <- function(engine) {
    counts$closed <- counts$closed + 1L
    if (scenario == "close_error") stop("synthetic close failure")
  }
  choose <- function(engine, contract) {
    if (scenario == "choices_error") stop("synthetic choices failure")
    list(x = list(list(value = "a", label = "A")))
  }
  registerS3method("sas_engine_run", "audit_pool_engine", run, envir = asNamespace("SAShiny"))
  registerS3method("sas_engine_close", "audit_pool_engine", close, envir = asNamespace("SAShiny"))
  registerS3method("sas_engine_choices", "audit_pool_engine", choose, envir = asNamespace("SAShiny"))
  cfg <- modifyList(list(max_size = 2L, acquire_timeout = 0.15), p$config %||% list())
  pool <- do.call(sas_pool, c(list(engine = factory), cfg))
  on.exit(sas_pool_close(pool), add = TRUE)
  out <- errs <- list()
  held <- NULL
  if (scenario == "busy_choices") {
    held <- internal("acquire")(pool)
    tryCatch(sas_engine_choices(pool, contract), error = function(e) errs[[1]] <<- conditionMessage(e))
    internal("release")(pool, held)
  } else if (scenario == "choices_error") {
    tryCatch(sas_engine_choices(pool, contract), error = function(e) errs[[1]] <<- conditionMessage(e))
  } else if (scenario == "close_reopen") {
    sas_pool_run(pool, contract, list())
    sas_pool_close(pool)
    out <- list(fix_result(sas_pool_run(pool, contract, list())))
  } else {
    for (i in seq_len(p$runs %||% 2L)) {
      out[[i]] <- fix_result(sas_pool_run(pool, contract, list()))
      if (scenario == "idle") Sys.sleep(0.03)
    }
  }
  before <- length(pool$sessions)
  sas_pool_close(pool)
  list(counts = as.list(counts), results = out, errors = errs,
       sessions_before_close = before, sessions_after_close = length(pool$sessions))
}

fake_case <- function(p, contract) {
  e <- new.env(parent = asNamespace("SAShiny"))
  sys.source("/tmp/SAShiny/R/tests/testthat/helper-fakesas.R", envir = e)
  data <- lapply(p$datasets %||% list(), function(v) {
    cols <- lapply(seq_along(v$columns), function(j) {
      unlist(lapply(v$rows, function(row) row[[j]] %||% NA), use.names = FALSE)
    })
    names(cols) <- unlist(v$columns)
    as.data.frame(cols, check.names = FALSE, stringsAsFactors = FALSE)
  })
  opts <- list(datasets = data)
  for (n in c("syscc", "program_log", "lst")) if (!is.null(p[[n]])) opts[[n]] <- p[[n]]
  opts$files <- lapply(p$remote_files %||% list(), openssl::base64_decode)
  sessions <- list()
  factory <- function() {
    if (identical(p$scenario, "slow_factory")) Sys.sleep(1.5)
    fake <- do.call(e$fake_sas, opts)
    original <- fake$submit
    fake$submit <- function(code, results = "HTML") {
      if (identical(p$scenario, "slow_submit") && grepl("wrapper", code)) Sys.sleep(1.5)
      if (identical(p$scenario, "raise_submit") && grepl("wrapper", code)) {
        stop("synthetic submission failure")
      }
      original(code, results)
    }
    sessions[[length(sessions) + 1L]] <<- fake
    fake
  }
  engine <- sas_engine_saspy(list(), session_factory = factory,
                             record_to = if (isTRUE(p$record)) file.path(p$folder,"rec") else NULL)
  on.exit(sas_engine_close(engine), add = TRUE)
  out <- list()
  for (i in seq_len(p$runs %||% 1L)) {
    out[[i]] <- fix_result(sas_engine_run(engine, contract, p$values %||% list(),
                          today = as.Date("2026-11-11"), uploads = upload_args(p),
                          run_id = p$run_id %||% "audit"))
  }
  before <- lapply(sessions, function(f) f$ended)
  sas_engine_close(engine)
  uploaded <- list()
  for (f in sessions) for (name in names(f$uploaded)) uploaded[[name]] <- frame_value(f$uploaded[[name]]$df)
  list(results = out, sessions = length(sessions), closed_before = before,
       closed_after = lapply(sessions, function(f) f$ended),
       submitted = as.list(unlist(lapply(sessions, function(f) f$submitted))),
       uploaded = object(uploaded))
}

dispatch <- function(p) {
  op <- p$operation
  if (op == "inventory") {
    pkgs <- c("SAShiny","shiny","jsonlite","jsonvalidate","yaml","openssl","ggplot2","plotly",
              "haven","openxlsx","reticulate","bslib","rlang","testthat","rmarkdown","knitr")
    return(list(r = R.version.string, exports = as.list(getNamespaceExports("SAShiny")),
                versions = setNames(lapply(pkgs, function(n) as.character(packageVersion(n))), pkgs),
                backends = as.list(sas_chart_backends())))
  }
  if (op == "module_id") return(lapply(p$names, internal("default_module_id")))
  if (op == "profiles") {
    path <- file.path(p$folder, "profiles.yml")
    if (!is.null(p$yaml)) writeLines(p$yaml, path)
    return(sas_load_profiles(path))
  }
  if (op == "connect") {
    engine <- do.call(sas_connect, p$kwargs)
    on.exit(sas_engine_close(engine), add = TRUE)
    return(engine$cfg)
  }
  if (op == "preflight") {
    internal("preflight")(p$config)
    return(list(passed = TRUE))
  }
  if (op == "status") {
    value <- internal("run_status")(p$log, p$run_id %||% "audit")
    value$counts <- as.list(internal("classify_log")(p$log))
    return(value)
  }
  if (op == "sanitize") return(as.list(internal("sanitize_names")(unlist(p$names))))
  if (op == "make_upload") {
    data <- lapply(seq_along(p$columns),function(j) {
      unlist(lapply(p$rows,function(row) row[[j]] %||% NA))
    })
    names(data) <- unlist(p$columns)
    df <- as.data.frame(data,stringsAsFactors=FALSE,check.names=FALSE)
    path <- file.path(p$folder,"generated.sas7bdat")
    haven::write_sas(df,path)
    return(list(base64=openssl::base64_encode(readBin(path,"raw",n=file.info(path)$size))))
  }
  if (op == "collect") {
    args <- p$args %||% list()
    kw <- p$kwargs %||% list()
    name <- p[["function"]]
    allowed <- c("split_log","scope_log","log_level","extract_plots","table_meta_code",
                 "formatted_table_code","choices_code","build_table","select_columns",
                 "join_remote","csv_bytes","xlsx_bytes","xpt_bytes","download_value",
                 "recording_key_text","recording_key","split_member")
    stopifnot(name %in% allowed)
    if (name %in% c("recording_key", "recording_key_text")) {
      pairs <- args[[2]]
      args[[2]] <- setNames(lapply(pairs, `[[`, 2L), vapply(pairs, `[[`, "", 1L))
      pairs <- args[[3]]
      args[[3]] <- setNames(vapply(pairs, `[[`, "", 2L), vapply(pairs, `[[`, "", 1L))
      if (name == "recording_key") name <- "recording_key_hash"
    }
    if (name == "formatted_table_code") args[[3]] <- unlist(args[[3]])
    value <- do.call(internal(name), c(args,kw))
    if (is.raw(value)) return(list(base64 = openssl::base64_encode(value)))
    if (name == "split_log") value <- as.list(value)
    if (name == "split_member") value <- unname(value)
    return(value)
  }
  if (op == "upload") {
    v <- internal("read_upload")(internal("upload_file")(file.path(p$folder,p$name),p$name),p$spec)
    return(c(frame_value(v$df),list(datetimes = object(v$datetimes))))
  }
  if (op == "chart") {
    if (isTRUE(p$callback)) {
      return(list(callback = sas_render_chart(p$value,p$spec,render=function(value,spec) "audit callback")))
    }
    backend <- p$backend %||% "ggplot2"
    obj <- sas_render_chart(p$value,p$spec,backend)
    if (backend == "plotly") {
      plot <- jsonlite::fromJSON(as.character(plotly::plotly_json(obj,jsonedit=FALSE)),
                                  simplifyVector=FALSE)
      return(list(backend = backend, plot = plot))
    }
    png <- file.path(p$folder,"chart.png")
    grDevices::png(png,width=1200,height=900)
    if (inherits(obj,"recordedplot")) grDevices::replayPlot(obj) else print(obj)
    grDevices::dev.off()
    return(list(backend = backend,png=openssl::base64_encode(readBin(png,"raw",n=file.info(png)$size))))
  }
  contract <- sas_contract(p$contract_path)
  today <- as.Date(p$today %||% "2026-11-11")
  if (op == "validate") return(list(issues=issues(sas_validate(contract,today)),data=contract$data))
  if (op == "values") {
    v <- sas_render_values(contract$data,p$values %||% list(),today,
                          only=unlist(p$only),choices_override=p$choices,uploads=p$uploads)
    return(list(macros=object(v$macros),macro_order=as.list(names(v$macros)),issues=issues(v$issues)))
  }
  if (op == "macro_names") return(as.list(internal("all_macro_names")(contract$data)))
  if (op == "wrapper") {
    file <- file.path(contract$base_dir,contract$data$program)
    program <- readBin(file,"raw",n=file.info(file)$size)
    v <- sas_render_values(contract$data,p$values %||% list(),today,uploads=p$uploads)
    return(list(issues=issues(v$issues),
                main=sas_wrapper_code(contract$data,v$macros,program,p$run_id %||% "fixture"),
                reset=sas_reset_code(contract$data),program_b64=openssl::base64_encode(program)))
  }
  if (op == "lint") {
    file <- file.path(contract$base_dir,contract$data$program)
    text <- rawToChar(readBin(file,"raw",n=file.info(file)$size))
    return(issues(sashiny_lint(contract$data,text)))
  }
  if (op %in% c("mock","runner")) {
    engine <- sas_engine_mock(file.path(p$folder,"rec"),choices=p$choices)
    uploads <- upload_args(p)
    if (!is.null(p$recording)) {
      v <- sas_render_values(contract$data,p$values %||% list(),today,
                             uploads=lapply(uploads,function(v) !isFALSE(v) && !is.null(v)))
      sas_engine_record(engine,contract,v$macros,p$recording,
                         files=Filter(is.character,uploads))
    }
    value <- if (op == "runner") {
      sas_run(if (isTRUE(p$by_path)) p$contract_path else contract,p$values %||% list(),
              engine,today,uploads,p$run_id %||% "audit")
    } else sas_engine_run(engine,contract,p$values %||% list(),today,uploads,p$run_id %||% "audit")
    return(fix_result(value))
  }
  if (op == "recording") {
    engine <- sas_engine_mock(file.path(p$folder,"rec"))
    key <- internal("recording_key")(contract,p$macros %||% list())
    path <- sas_engine_record(engine,contract,p$macros %||% list(),p$recording)
    r <- sashiny_result("audit","success",outputs=p$recording$outputs)
    second <- internal("save_recording")(engine$recordings_dir,"second",r)
    return(list(key=key,raw=paste(readLines(path),collapse="\n"),
                loaded=internal("load_recording")(engine$recordings_dir,key),
                result_raw=paste(readLines(second),collapse="\n")))
  }
  if (op == "raw_replay") {
    rec <- file.path(p$folder,"rec")
    dir.create(rec)
    values <- p$values %||% list()
    macros <- sas_render_values(contract$data,values,today)$macros
    key <- internal("recording_key")(contract,macros)
    writeLines(p$raw,file.path(rec,paste0(key,".json")),useBytes=TRUE)
    return(fix_result(sas_engine_run(sas_engine_mock(rec),contract,values,today)))
  }
  if (op == "fake") return(fake_case(p,contract))
  if (op == "pool") return(pool_case(p,contract))
  if (op == "ui") {
    value <- sas_program_ui("mod",contract,today=today,
             ui_override=if(isTRUE(p$override)) function(id,contract) shiny::div("audit override") else NULL)
    return(list(html=as.character(value)))
  }
  if (op == "shiny_values") {
    return(internal("shiny_values")(contract,function(iid) p$raw[[iid]]))
  }
  if (op == "app") {
    other <- contract
    if (!is.null(p$other_id)) other$data$id <- p$other_id
    a <- sas_app(if (isTRUE(p$duplicate)) list(contract,other) else list(contract),sas_engine_mock())
    return(list(built=TRUE,type=class(a)[1]))
  }
  stop("unsupported audit operation: ",op)
}

request <- fromJSON(commandArgs(trailingOnly=TRUE)[[1]],simplifyVector=FALSE)
warnings <- character()
result <- tryCatch(
  withCallingHandlers(list(ok=TRUE,value=dispatch(request)),warning=function(w) {
    warnings <<- c(warnings,conditionMessage(w))
  }),
  error=function(e) list(ok=FALSE,exception=class(e)[1],message=conditionMessage(e))
)
result$warnings <- as.list(warnings)
cat("AUDIT_RESULT=",toJSON(result,auto_unbox=TRUE,null="null",na="null",digits=I(17)), "\n",sep="")
