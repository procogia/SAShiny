library(SAShiny)
contracts <- lapply(c("alpha","beta"),function(name) structure(list(
  data=list(sashiny=1L,program="program.sas",id=name,title=name,
            outputs=list(report=list(type="log"))),
  base_dir="/tmp/audit"
),class="sashiny_contract"))
sas_app(contracts,sas_engine_mock())
