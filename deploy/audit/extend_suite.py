"""Fill remaining API, format, rendering and lifecycle gaps with explicit remote cases."""
import base64
import copy
import io
import json
import sys
from pathlib import Path

import generate_suite as g
from generate_suite import add, both, normal, table

for libref,path in (("work","/synthetic/work/"),("win","C:\\synthetic\\work\\")):
    sep="\\" if libref=="win" else "/"
    both("remote_join_"+libref,"remote-paths","collect",
         {"function":"join_remote","args":[path,"out.csv"]},
         f"assert got=={path.rstrip('/'+chr(92))+sep+'out.csv'!r},got",["join_remote"])

meta=[{"name":"Age","type":"numeric","label":"Age label","format":""},
      {"name":"NAME","type":"character","label":"","format":""}]
both("column_selection_order","table-collection","collect",
     {"function":"select_columns","args":[meta,["name","age"]]},
     "assert [c['name'] for c in got]==['NAME','Age'],got",["select_columns"])
for language in ("python","r"):
    add("column_selection_error_"+language,"table-collection",
        f"expect_exception({language!r},'collect',{{'function':'select_columns','args':[{meta!r},['absent']]}})",
        ["select_columns"])
both("table_missing_unicode_spaces","table-collection","collect",
     {"function":"build_table","args":[meta,[[None," a \t"],[12,"b\u00a0"]]],
      "kwargs":{"total_rows":3,"max_rows":2,"formatted":False}},
     "assert got['rows']==[[None,' a'],[12,'b\\u00a0']],got\nassert got['truncated'],got",
     ["build_table","SAS missing","ASCII blanks"])
both("table_formatted_spaces","table-collection","collect",
     {"function":"build_table","args":[meta,[["  12 "," a \t"]]],
      "kwargs":{"total_rows":None,"max_rows":2,"formatted":True}},
     "assert got['rows']==[['12','a']],got\nassert got['total_rows'] is None,got",
     ["build_table","formatted","unknown nobs"])
both("table_metadata_code","generated-query","collect",{"function":"table_meta_code","args":["WORK","OUT"]},
     "assert 'dictionary.columns' in got and 'nlobs' in got and got.endswith('\\n'),got",
     ["table_meta_code"])
both("formatted_query_code","generated-query","collect",
     {"function":"formatted_table_code","args":["WORK","OUT",["AGE","NAME"],3]},
     "assert 'obs=3 keep=AGE NAME' in got and '_sx_c2 = strip(vvalue(NAME));' in got,got",
     ["formatted_table_code"])
both("dynamic_choices_query","generated-query","collect",
     {"function":"choices_code","args":[{"dataset":"WORK.CHOICES","value_column":"CODE","label_column":"LABEL","max_choices":7}]},
     "assert 'outobs=7' in got and 'where not missing(CODE)' in got and 'order by CODE' in got,got",
     ["choices_code"])
both("dynamic_choices_validation","dynamic-choices","values",
     {"data":normal({"pick":{"type":"choice","label":"Pick","choices_from":{"dataset":"work.c","value_column":"v"}}}),
      "values":{"pick":"b"},"choices":{"pick":["a"]}},
     "assert codes(got)==[('V004','pick')],got",["choices_override","V004"])
data=normal({"pick":{"type":"choice","label":"Pick","choices_from":{"dataset":"work.choices","value_column":"value"}}})
add("dynamic_choices_after_session_failure","dynamic-choices",
    f"got=value('python','choices_cache',{{'data':{data!r}}})\n"
    "assert got['second']['pick'][0]['value']=='new',got",["SaspyEngine.choices","discard"])
add("pool_close_with_inflight_run","pool-concurrency",
    "got=value('python','pool',{'scenario':'close_inflight','delay':0.1,"
    "'config':{'min_size':1,'max_size':1,'acquire_timeout':1}})\n"
    "assert got['sessions_before_close']==0,got",["Pool.close","Pool._release","warm minimum"])

# Direct upload round trips exercise real optional libraries on the server.
formats=("csv","xlsx","xpt")
upload_table={"columns":[{"name":"AGE","type":"numeric","label":"","format":""},
                          {"name":"NAME","type":"character","label":"","format":""}],
              "rows":[[12,"Ann"],[None,"Ben"]],"total_rows":2,"truncated":False,"formatted":False}
for fmt in formats:
    for producer,consumer in (("python","r"),("r","python")):
        args=[upload_table] if fmt=="csv" else [upload_table,"DATA"]
        spec={"type":"dataset","target":"work.data","columns":[
            {"name":"AGE","type":"numeric"},{"name":"NAME","type":"character"}]}
        source=(f"encoded=value({producer!r},'collect',{{'function':{fmt+'_bytes'!r},'args':{args!r}}})['base64']\n"
                f"got=value({consumer!r},'upload',{{'name':{'data.'+fmt!r},'spec':{spec!r},"
                f"'files':[{{'name':{'data.'+fmt!r},'base64':encoded}}]}})\n"
                "assert got['rows']==[[12,'Ann'],[None,'Ben']],got")
        add(f"{fmt}_interop_{producer}_to_{consumer}","format-interoperability",source,
            [fmt,"read_upload","csv_bytes","xlsx_bytes","xpt_bytes"])

for producer,consumer in (("python","r"),("r","python")):
    rec={"status":"success","log":"NOTE: Unicode \u03bb","outputs":{"t":upload_table}}
    add(f"recording_{producer}_to_{consumer}","recording-interoperability",
        f"written=value({producer!r},'recording',{{'recording':{rec!r}}})\n"
        f"got=value({consumer!r},'raw_replay',{{'raw':written['raw']}})\n"
        f"assert got['outputs']=={rec['outputs']!r},got\nassert got['metadata']['recording']=='replayed',got",
        ["save_recording","load_recording","MockEngine.run","sas_engine_record"])

outputs={fmt:{"type":"download","format":fmt,"from":"work.out"} for fmt in ("sas7bdat",)}
outputs.update({fmt:{"type":"download","format":fmt} for fmt in ("rtf","pdf")})
remote={
    "/sas/work/out.sas7bdat":base64.b64encode(b"synthetic native SAS file transport").decode(),
    "/sas/work/sashiny_rtf.rtf":base64.b64encode(b"{\\rtf1 Synthetic report}").decode(),
    "/sas/work/sashiny_pdf.pdf":base64.b64encode(b"%PDF-1.4 synthetic transport only").decode(),
}
both("remote_download_protocols","engine-orchestration","fake",
     {"data":normal(outputs=outputs),"remote_files":remote},
     "r=got['results'][0]\nassert r['status']=='success',r\n"
     "assert not r['metadata']['collect_errors'],r\n"
     "assert all('data' in r['outputs'][f] for f in ('sas7bdat','rtf','pdf')),r",
     ["_fetch_file","_download","rtf","pdf","sas7bdat transport"])

for kind in ("numeric","text","choice","multichoice","date","daterange","dataset"):
    spec={"type":kind,"label":kind}
    if kind in ("choice","multichoice"): spec["choices"]=["a","b"]
    if kind=="dataset": spec.update(target="work.data",accept=["csv"],optional=True)
    body={"data":normal({"x":spec})}
    both("ui_control_"+kind,"ui-controls","ui",body,
         "assert 'mod-x' in got['html'] and 'mod-run' in got['html'],got",["program_ui",kind])

for kind,widget in [("choice","radio"),("multichoice","checkbox"),("multichoice","select")]:
    spec={"type":kind,"label":"X","choices":["a","b"],"widget":widget}
    both("ui_widget_"+kind+"_"+widget,"ui-controls","ui",{"data":normal({"x":spec})},
         "assert 'mod-x' in got['html'],got",["program_ui",widget])

spec={"type":"multichoice","label":"X","choices":["a"],"min_selected":0}
both("missing_required_multichoice_min_zero","value-boundaries","values",{"data":normal({"x":spec}),"values":{}},
     "assert codes(got)==[('V001','x')],got",["V001","absence vs empty array"])
for raw in ([],["a"]):
    both("required_multichoice_min_zero_"+str(raw),"value-boundaries","values",
         {"data":normal({"x":spec}),"values":{"x":raw}},
         "assert not got['issues'],got",["min_selected"])
data=normal({"dataset":{"type":"dataset","label":"Upload","target":"work.data","sample":"sample.csv"},
             "dataset__sample":{"type":"text","label":"Named like generated input","optional":True}})
both("sample_control_id_collision","ui-identifiers","ui",{"data":data},
     "assert got['html'].count('id=\"mod-dataset__sample\"')==1,got",["program_ui","sample input"])

for language in ("python","r"):
    add("app_explicit_id_collision_"+language,"app",
        f"expect_exception({language!r},'app',{{'data':{normal(id='same')!r},'duplicate':True}},'duplicate')",
        ["app","duplicate explicit ids"])
    add("no_spec_chart_module_"+language,"chart-errors",
        f"expect_exception({language!r},'chart',{{'value':{table!r},'spec':None}},'no spec')",
        ["chart rendering errors"])

for track,path in [("general","general/cars_explorer.sashiny.yml"),
                   ("pharma","pharma/ae_summary.sashiny.yml"),
                   ("aml","aml/cash_aggregation_tuning.sashiny.yml"),
                   ("forecasting","forecasting/arima_forecast.sashiny.yml")]:
    both("demo_contract_"+track,"demo-integration","validate",{"example":path},
         "assert not got['issues'],got",["demo "+track,"validate"])
    both("demo_ui_"+track,"demo-integration","ui",{"example":path},
         "assert 'mod-run' in got['html'] and 'mod-status' in got['html'],got",["demo "+track,"program_ui"])
    both("demo_lint_"+track,"demo-integration","lint",{"example":path},
         "assert not got,got",["demo "+track,"lint"])

for scenario,rows,valid in [
    ("native_dates_and_blank",[[12,{"date":"2026-01-01"}],[13,None]],True),
    ("leading_blank_then_native",[[12,None],[13,{"date":"2026-01-01"}]],True),
    ("literal_NA",[[12,"NA"],[13,{"date":"2026-01-01"}]],False),
    ("iso_and_native",[[12,"2026-01-01"],[13,{"date":"2026-01-02"}]],True),
]:
    for lang in ("python","r"):
        spec={"type":"dataset","target":"work.data","columns":[
            {"name":"age","type":"numeric"},{"name":"day","type":"date"}]}
        source=f"binary=value('python','make_upload',{{'columns':['age','day'],'rows':{rows!r}}})['base64']\n"
        source+=f"request={{'name':'data.xlsx','spec':{spec!r},'files':[{{'name':'data.xlsx','base64':binary}}]}}\n"
        if valid: source+=f"got=value({lang!r},'upload',request)\nassert len(got['rows'])==2,got"
        else: source+=f"expect_exception({lang!r},'upload',request)"
        add(f"xlsx_cells_{lang}_{scenario}","xlsx-native-cells",source,["read_upload","xlsx","date"])
for lang in ("python","r"):
    spec={"type":"dataset","target":"work.data","columns":[
          {"name":"AGE","type":"numeric"},{"name":"NAME","type":"character"}]}
    add("native_sas7bdat_upload_"+lang,"native-sas7bdat",
        "binary=value('r','make_upload',{'columns':['AGE','NAME'],'rows':[[12,'Ann'],[13,'Ben']]})['base64']\n"
        f"got=value({lang!r},'upload',{{'name':'data.sas7bdat','spec':{spec!r},"
        "'files':[{'name':'data.sas7bdat','base64':binary}]})\n"
        "assert got['rows']==[[12,'Ann'],[13,'Ben']],got",["read_upload","sas7bdat","haven","pyreadstat"])
for pattern in ("[+?]", "[(?=]"):
    data=normal({"x":{"type":"text","label":"X","pattern":pattern}})
    both("portable_regex_literal_class_"+pattern,"regex-literals","validate",{"data":data},
         "assert not got['issues'],got",["S014","portable regex character classes"])
for field,value in (("max_length",1.000001),):
    data=normal({"x":{"type":"text","label":"X",field:value}})
    both("schema_fractional_"+field,"schema-precision","validate",{"data":data},
         "assert any(i['code']=='E000' for i in got['issues']),got",["sas_validate","JSON Schema","precision"])
both("unicode_module_id_parity","app","module_id",{"names":["\u0130stanbul.sas"]},
     "assert got==['i_stanbul'],got",["default_module_id","Unicode"])
add("timeout_generation_reuse","engine-lifecycle",
    f"got=value('python','generation_cancel',{{'data':{normal(run={'timeout_seconds':1})!r}}})\n"
    "assert got['old']['status']=='error' and got['new']['status']=='success',got\n"
    "assert got['sessions_created']==2 and all(got['closed_before_cleanup']),got",
    ["SaspyEngine.run","timeout generation","close"])
for lang,backend in [("python","matplotlib"),("r","base")]:
    for feature in ("color","fill","facet"):
        spec={"kind":"bar" if feature=="fill" else "scatter","x":"X","y":"Y"}
        b={"value":table,"spec":spec,"backend":backend}
        enhanced=copy.deepcopy(b); enhanced["spec"][feature]="Group"
        add(f"raster_mapping_{lang}_{feature}","chart-mapping-semantics",
            f"plain=validate_png(value({lang!r},'chart',{b!r})['png'])\n"
            f"mapped=validate_png(value({lang!r},'chart',{enhanced!r})['png'])\n"
            "assert plain.tobytes()!=mapped.tobytes(),'declared mapping changes no rendered pixels'",
            ["render_chart",backend,feature])
for lang in ("python","r"):
    add("app_helper_real_server_"+lang,"app-live-server",
        f"from app_wire import exercise\nexercise({lang!r})",["app.server","sas_app server","file_sha256"])
(g.HERE/"manifest.json").write_text(json.dumps(g.manifest,indent=2),encoding="utf-8")
print("Extended manifest:",len(g.manifest),"distinct scripts")
