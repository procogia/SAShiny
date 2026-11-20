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
  switch(profile,
    oda = sas_connect("oda",
      region = .live_env("SASHINY_ODA_REGION", "us1"), java = java, license_ack = TRUE
    ),
    viya = sas_connect("viya",
      url = .live_env("SASHINY_VIYA_URL"), context = .live_env("SASHINY_VIYA_CONTEXT"),
      license_ack = TRUE
    ),
    sas94 = sas_connect("sas94",
      host = .live_env("SASHINY_SAS94_HOST"),
      port = as.integer(.live_env("SASHINY_SAS94_PORT", "8591")),
      saspath = .live_env("SASHINY_SAS94_SASPATH"), java = java, license_ack = TRUE
    ),
    stop("set SASHINY_PROFILE to oda, viya or sas94", call. = FALSE)
  )
}
