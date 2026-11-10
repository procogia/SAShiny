# A fake saspy session for engine tests.
#
# It understands exactly the submissions SAShiny makes (spec sections 6 and
# 8.2): the reset, the wrapper, the table metadata and formatted steps, the path
# and version queries, the choices query and the `_sx_*` clean-up. Data sets are
# data frames keyed "LIB.MEM". Mirrors Python/tests/fakesas.py.

.fake_png <- .sashiny_b64enc(c(as.raw(0x89), charToRaw("PNG fake")))
.fake_lst <- paste0(
  "<html><body><h1>Report</h1>",
  "<img src=\"data:image/png;base64,", .fake_png, "\" alt=\"graph 1\">",
  "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"1\" height=\"1\"/></svg>",
  "</body></html>"
)

fake_sas <- function(datasets = list(), meta = list(), files = list(),
                     program_log = "NOTE: The data set WORK.OUT has 2 observations.",
                     syscc = 0L, lst = .fake_lst) {
  self <- new.env()
  self$datasets <- datasets
  self$submitted <- character(0)
  self$uploaded <- list()
  self$ended <- FALSE
  self$syscc <- syscc
  self$program_log <- program_log
  key <- function(lib, mem) paste0(toupper(lib), ".", toupper(mem))
  first <- function(pattern, text) {
    m <- regmatches(text, regexec(pattern, text, perl = TRUE))[[1]]
    if (length(m)) m[-1] else NULL
  }

  meta_step <- function(code) {
    parts <- first('libname = "(\\w+)" and memname = "(\\w+)"', code)
    df <- self$datasets[[key(parts[1], parts[2])]]
    if (is.null(df)) {
      self$datasets[["WORK._SX_COLS"]] <- data.frame(
        varnum = numeric(0), name = character(0), type = character(0),
        format = character(0), label = character(0)
      )
      return(invisible())
    }
    extra <- meta[[key(parts[1], parts[2])]] %||% list()
    rows <- lapply(seq_along(df), function(i) {
      col <- names(df)[[i]]
      info <- extra[[toupper(col)]] %||% list()
      kind <- if (is.numeric(df[[i]]) || inherits(df[[i]], c("Date", "POSIXt"))) "num" else "char"
      data.frame(
        varnum = i, name = col, type = kind,
        format = info$format %||% "", label = info$label %||% "",
        stringsAsFactors = FALSE
      )
    })
    self$datasets[["WORK._SX_COLS"]] <- do.call(rbind, rows)
    self$datasets[["WORK._SX_NOBS"]] <- data.frame(nlobs = as.numeric(nrow(df)))
  }

  fmt_step <- function(code) {
    parts <- first("set (\\w+)\\.(\\w+)\\(obs=(\\d+) keep=([\\w ]+)\\);", code)
    df <- utils::head(self$datasets[[key(parts[1], parts[2])]], as.integer(parts[3]))
    cols <- strsplit(parts[4], " ")[[1]]
    out <- lapply(cols, function(c) paste0("fmt:", df[[match(toupper(c), toupper(names(df)))]]))
    names(out) <- paste0("_sx_c", seq_along(cols))
    self$datasets[["WORK._SX_FMT"]] <- as.data.frame(out,
      check.names = FALSE, stringsAsFactors = FALSE
    )
  }

  choices_step <- function(code) {
    parts <- first("select distinct ([\\w, ]+)\\n\\s*from (\\w+)\\.(\\w+)", code)
    cols <- trimws(strsplit(parts[1], ",")[[1]])
    df <- self$datasets[[key(parts[2], parts[3])]]
    picked <- unique(df[, match(toupper(cols), toupper(names(df))), drop = FALSE])
    picked <- picked[order(picked[[1]]), , drop = FALSE]
    rownames(picked) <- NULL
    self$datasets[["WORK._SX_CHOICES"]] <- picked
  }

  self$submit <- function(code, results = "HTML") {
    self$submitted <- c(self$submitted, code)
    run <- first("SASHINY-BEGIN run=(\\S+);", code)
    if (!is.null(run)) {
      log <- paste0(
        "1    %put NOTE: SASHINY-BEGIN run=", run, ";\n",
        "NOTE: SASHINY-BEGIN run=", run, "\n",
        "NOTE: SASHINY-BEGIN-PROGRAM\n",
        self$program_log, "\n",
        "NOTE: SASHINY-END-PROGRAM\n",
        "NOTE: SASHINY-END run=", run, " syscc=", self$syscc, "\n"
      )
      return(list(LOG = log, LST = lst))
    }
    if (grepl("_sx_cols", code, fixed = TRUE)) {
      meta_step(code)
    } else if (grepl("data work._sx_fmt;", code, fixed = TRUE)) {
      fmt_step(code)
    } else if (grepl("_sx_choices as", code, fixed = TRUE)) {
      choices_step(code)
    } else if (grepl("SXVER=", code, fixed = TRUE)) {
      return(list(LOG = "1    %put SXVER=&sysvlong;\nSXVER=9.04.01M8P011923\n", LST = ""))
    } else if (grepl("SASHINY-PATH=", code, fixed = TRUE)) {
      lib <- first("pathname\\((\\w+)\\)", code)
      return(list(LOG = paste0("1 %put ...\nSASHINY-PATH=/sas/", tolower(lib), "\n"), LST = ""))
    } else if (grepl("delete _sx_", code, fixed = TRUE)) {
      drop <- startsWith(names(self$datasets), "WORK._SX_")
      self$datasets <- self$datasets[!drop]
    }
    list(LOG = "", LST = "")
  }

  self$sd2df <- function(table, libref = "WORK", dsopts = NULL) {
    df <- self$datasets[[key(libref, table)]]
    if (is.null(df)) {
      return(NULL)
    }
    if (!is.null(dsopts$keep)) {
      keep <- strsplit(dsopts$keep, " ")[[1]]
      df <- df[, match(toupper(keep), toupper(names(df))), drop = FALSE]
    }
    if (!is.null(dsopts$obs)) df <- utils::head(df, dsopts$obs)
    df
  }

  self$df2sd <- function(df, table, libref, datetimes) {
    self$uploaded[[key(libref, table)]] <- list(df = df, datetimes = datetimes)
    self$datasets[[key(libref, table)]] <- df
  }

  self$download <- function(localfile, remotefile, overwrite = TRUE) {
    if (is.null(files[[remotefile]])) {
      return(list(Success = FALSE, LOG = paste("ERROR:", remotefile, "not found")))
    }
    writeBin(files[[remotefile]], localfile)
    list(Success = TRUE, LOG = "")
  }

  self$endsas <- function() self$ended <- TRUE
  self
}

# The contract used by the live-engine tests (same as the Python tests).
.fake_contract_yaml <- c(
  "sashiny: 1",
  "program: prog.sas",
  "title: Fake run",
  "inputs:",
  "  min_age:",
  "    type: numeric",
  "    label: Minimum age",
  "    default: 18",
  "  make:",
  "    type: choice",
  "    label: Make",
  "    choices_from: {dataset: sashelp.cars, value_column: make}",
  "    optional: true",
  "  adsl:",
  "    type: dataset",
  "    label: ADSL",
  "    target: work.adsl",
  "    sample: adsl.csv",
  "    optional: true",
  "    columns:",
  "      - {name: age, type: numeric}",
  "outputs:",
  "  stats:",
  "    type: table",
  "    from: work.stats",
  "    columns: [AGE, name]",
  "    max_rows: 2",
  "  stats_fmt:",
  "    type: table",
  "    from: work.stats",
  "    formatted: true",
  "  missing:",
  "    type: table",
  "    from: work.nope",
  "  graphs:",
  "    type: plot",
  "  second:",
  "    type: plot",
  "    select: 2",
  "  report:",
  "    type: html",
  "  log:",
  "    type: log",
  "  csv:",
  "    type: download",
  "    format: csv",
  "    from: work.stats",
  "    filename: stats",
  "  data:",
  "    type: download",
  "    format: sas7bdat",
  "    from: work.stats",
  "  rtf:",
  "    type: download",
  "    format: rtf"
)

fake_contract <- function(dir = tempfile("sashiny-fake-")) {
  dir.create(dir, showWarnings = FALSE)
  writeLines("data work.stats; set work.adsl; run;", file.path(dir, "prog.sas"))
  writeLines(c("age,name", "40,Ann", "50,Bo"), file.path(dir, "adsl.csv"))
  writeLines(.fake_contract_yaml, file.path(dir, "app.sashiny.yml"))
  sas_contract(file.path(dir, "app.sashiny.yml"))
}

fake_session <- function() {
  stats <- data.frame(
    name = c("Ann", "Bo", "Cy"),
    age = c(40, NA, 61),
    trtsdt = as.POSIXct(c("2024-01-02", NA, "1960-01-01"), tz = "UTC"),
    stringsAsFactors = FALSE
  )
  cars <- data.frame(Make = c("BMW", "Audi", "BMW", "Saab"), stringsAsFactors = FALSE)
  fake_sas(
    list(WORK.STATS = stats, SASHELP.CARS = cars),
    meta = list(WORK.STATS = list(AGE = list(label = "Age (y)", format = "BEST12."))),
    files = list(
      "/sas/work/stats.sas7bdat" = charToRaw("SAS7BDAT"),
      "/sas/work/sashiny_rtf.rtf" = charToRaw("{\\rtf1}")
    )
  )
}
