# Shared helpers for the live SAS tests (SASHINY_LIVE=1). Connection settings
# are documented in test-demo-live.R; credentials always come from ~/.authinfo.

skip_unless_live <- function() {
  skip_on_cran()
  if (!identical(Sys.getenv("SASHINY_LIVE"), "1")) skip("live SAS tests need SASHINY_LIVE=1")
  skip_if_no_demo_scenarios()
}

.live_env <- function(name, default = NULL) {
  value <- Sys.getenv(name, unset = "")
  if (nzchar(value)) value else default
}

live_connect <- function() {
  profile <- .live_env("SASHINY_PROFILE", "")
  java <- .live_env("SASHINY_JAVA")
  backend <- switch(profile,
    oda = sas_oda(.live_env("SASHINY_ODA_REGION", "us1"), java = java),
    viya = sas_viya(.live_env("SASHINY_VIYA_URL"), context = .live_env("SASHINY_VIYA_CONTEXT")),
    sas94 = if (is.null(.live_env("SASHINY_SAS94_SASPATH"))) {
      sas_94_iom(.live_env("SASHINY_SAS94_HOST"),
        port = as.integer(.live_env("SASHINY_SAS94_PORT", "8591")), java = java)
    } else {
      sas_94_ssh(.live_env("SASHINY_SAS94_HOST"), .live_env("SASHINY_SAS94_SASPATH"))
    },
    stop("set SASHINY_PROFILE to oda, viya or sas94", call. = FALSE)
  )
  sas_connect(backend, license_ack = TRUE)
}
