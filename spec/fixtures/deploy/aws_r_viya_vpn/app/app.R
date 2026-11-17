library(SAShiny)

sas_app("report.sashiny.yml", sas_pool(sas_connect_env, max_size = 2L))
