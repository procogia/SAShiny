"""Generate distinct remote test scripts from frozen fixtures and explicit assertions."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]) if len(sys.argv)>1 else Path("/tmp/SAShiny")
FIX = REPO/"spec"/"fixtures"
SUITE = HERE/"scripts"
SUITE.mkdir(exist_ok=True)
manifest = []


def add(name, category, source, covers):
    index = len(manifest)+1
    filename = f"s{index:03d}_{re.sub('[^a-z0-9_]', '_', name.lower())}.py"
    code = (f'"""Audit {index}: {name}. Category: {category}."""\n'
            "from client import *\n\n"+source.rstrip()+"\n")
    (SUITE/filename).write_text(code,encoding="utf-8",newline="\n")
    manifest.append({"id":f"s{index:03d}","script":filename,"name":name,"category":category,
                     "covers":covers,"sha256":hashlib.sha256(code.encode()).hexdigest()})


def normal(inputs=None, outputs=None, **kw):
    return {"sashiny":1,"program":"program.sas","title":"Audit",
            "inputs":inputs or {}, "outputs":outputs or {"report":{"type":"log"}}, **kw}


def both(name, category, op, body, checks, covers):
    add(name,category,f"body = {body!r}\nfailures = []\nfor language in ('python', 'r'):\n"
        f"    try:\n        got = value(language, {op!r}, body)\n"+
        "\n".join("        "+s for s in checks.splitlines())+
        "\n    except AssertionError as exc:\n        failures.append((language, str(exc)))\n"
        "assert not failures, failures",covers)


# Contract and fixture suites: expected values come only from versioned fixtures.
for path in sorted((FIX/"contracts").glob("*/*/contract.sashiny.yml")):
    rel = path.parent.relative_to(FIX).as_posix()
    valid = path.parent.parent.name=="valid"
    expected = [] if valid else json.loads((path.parent/"expected.json").read_text())["errors"]
    want = sorted({(i["code"],i["path"]) for i in expected})
    if valid:
        check = "assert codes(got) == [], (language, got)"
    elif all(i[0]=="E000" for i in want):
        check = (f"wanted = {want!r}\nfound = codes(got)\n"
                 "assert found and all(c == 'E000' for c,p in found), (language, found)\n"
                 "assert all(any(gp.startswith(p) or p.startswith(gp) for c,gp in found)"
                 " for _,p in wanted), (language, wanted, found)")
    else:
        check = f"assert codes(got) == {want!r}, (language, got)"
    both("contract_"+path.parent.name,"contract-fixtures","validate",
         {"fixture":rel,"today":"2026-11-11"},check,["load","validate","schema","S001-S016"])

for path in sorted((FIX/"values").glob("*.json")):
    fixture = json.loads(path.read_text())
    for case in fixture["cases"]:
        body = {"fixture":fixture["contract"],"today":fixture["today"],"values":case["values"]}
        for old,new in [("choices_from","choices"),("uploads","uploads")]:
            if old in case: body[new]=case[old]
        exp = case["expected"]
        if exp["status"]=="ok":
            check = (f"assert got['macros'] == {exp['macros']!r}, (language, got)\n"
                     f"assert got['macro_order'] == {list(exp['macros'])!r}, (language, got)\n"
                     "assert not got['issues'], (language, got)")
        else:
            want = sorted({(e["code"],e["input"]) for e in exp["errors"]})
            check = f"assert codes(got) == {want!r}, (language, got)"
        both("values_"+path.stem+"_"+case["name"],"value-fixtures","values",body,check,
             ["render_values","V001-V014","macro ordering"])

for folder in sorted((FIX/"wrapper").iterdir()):
    case = json.loads((folder/"case.json").read_text())
    body = {"fixture":folder.relative_to(FIX).as_posix(),"values":case["values"],
            "uploads":case.get("uploads",{}),"today":case["today"],"run_id":"fixture"}
    check = f"assert got['main'] == {(folder/'expected_main.sas').read_text(encoding='utf-8')!r}, (language, got)\nassert not got['issues']"
    if (folder/"expected_reset.sas").exists():
        check += f"\nassert got['reset'] == {(folder/'expected_reset.sas').read_text()!r}"
    both("wrapper_"+folder.name,"wrapper-fixtures","wrapper",body,check,
         ["wrapper_code","reset_code","verbatim SAS","macro entry"])

# Audit cases deliberately include inputs missing from the existing tests.
for kind in ("date","daterange"):
    for bound in ("min","max"):
        data=normal({"x":{"type":kind,"label":"X",bound:"2026-01-01"}})
        both(f"{kind}_single_{bound}_bound","contract-boundaries","validate",{"data":data},
             "assert codes(got) == [], (language,got)",["S003"])
for raw in [None,"",{},{"chosen":"a"},[""],[None],[["a"]],[1,"a"]]:
    data=normal({"x":{"type":"multichoice","label":"X","choices":["a","b"],
                      "optional":True,"min_selected":0,"count_macro":"n"}})
    expected=[] if raw in (None,"") else [("V004","x")] if raw==[""] else [("V002","x")]
    both("multichoice_shape_"+str(raw),"value-boundaries","values",{"data":data,"values":{"x":raw}},
         f"assert codes(got) == {expected!r}, (language,got)",["render_values","V001","V002","V004"])
for raw in [["bad",None],["2026-01-01",None],[],[""],{},["2026-01-01"],[None,None]]:
    data=normal({"x":{"type":"daterange","label":"X","optional":True}})
    expected=[("V009","x")] if raw==["bad",None] else [("V002","x")]
    both("daterange_shape_"+str(raw),"value-boundaries","values",{"data":data,"values":{"x":raw}},
         f"assert codes(got) == {expected!r}, (language,got)",["render_values","V002","V009"])
for mode in ("iso","date9","literal","sasdate"):
    text={"iso":"0001-01-01","date9":"01JAN0001","literal":"'01JAN0001'd","sasdate":"-715509"}[mode]
    data=normal({"x":{"type":"date","label":"X","render":mode}})
    both("date_year_one_"+mode,"value-boundaries","values",{"data":data,"values":{"x":"0001-01-01"}},
         f"assert got['macros'] == {{'X':{text!r}}}, (language,got)\nassert not got['issues']",
         ["date rendering"])

for size in (32000,32001):
    data=normal({"x":{"type":"text","label":"X","max_length":32000}})
    raw="a"*size
    check="assert not got['issues']" if size==32000 else "assert codes(got) == [('V006','x')], got"
    both("text_length_"+str(size),"value-boundaries","values",{"data":data,"values":{"x":raw}},check,
         ["V006","V013"])
data=normal({"x":{"type":"text","label":"X","max_length":32000}})
both("unicode_macro_byte_limit","value-boundaries","values",{"data":data,"values":{"x":"\u00e9"*16001}},
     "assert codes(got) == [('V013','x')], got",["V013","UTF-8"])

# All advertised chart backends and kinds must actually render, not merely import.
table={"columns":[{"name":"X","type":"numeric","label":"","format":""},
                  {"name":"Y","type":"numeric","label":"","format":""},
                  {"name":"Group","type":"character","label":"","format":""}],
       "rows":[[1,3,"a"],[2,4,"a"],[3,5,"b"],[4,8,"b"]],
       "total_rows":4,"truncated":False,"formatted":False}
for language,backends in [("python",["plotnine","matplotlib","plotly"]),("r",["ggplot2","base","plotly"])]:
    for backend in backends:
        for kind in ("scatter","line","bar","histogram","box"):
            spec={"kind":kind,"x":"Group" if kind in ("bar","box") else "x",
                  "title":"Synthetic chart","xlab":"Horizontal","ylab":"Vertical"}
            if kind!="histogram": spec["y"]="y"
            body={"value":table,"spec":spec,"backend":backend}
            check="assert got['plot']['data'], got" if backend=="plotly" else "validate_png(got['png'])"
            add(f"chart_{language}_{backend}_{kind}","charts",
                f"got = value({language!r},'chart',{body!r})\n{check}",
                ["render_chart",backend,kind])
        for feature in ("color","fill","facet"):
            spec={"kind":"scatter" if feature!="fill" else "bar","x":"X","y":"Y",feature:"Group"}
            body={"value":table,"spec":spec,"backend":backend}
            if feature=="facet" and backend=="matplotlib":
                check="assert got['axes'] >= 2, got"
            elif feature=="facet" and backend=="plotly":
                check="assert 'xaxis2' in got['plot']['layout'], got['plot']['layout']"
            elif backend=="plotly":
                check="assert len(got['plot']['data']) >= 2, got['plot']['data']"
            else:
                check="validate_png(got['png'])"
            add(f"chart_{language}_{backend}_{feature}","chart-aesthetics",
                f"got = value({language!r},'chart',{body!r})\n{check}",["render_chart",backend,feature])
    for spec in (None,{"kind":"scatter","x":"X"},{"kind":"scatter","x":"missing","y":"Y"}):
        add(f"chart_error_{language}_{spec}","chart-errors",
            f"expect_exception({language!r},'chart',{{'value':{table!r},'spec':{spec!r}}})",
            ["render_chart","chart errors"])
    add("chart_callback_"+language,"chart-callbacks",
        f"got=value({language!r},'chart',{{'value':{table!r},'spec':None,'callback':True}})\n"
        "assert got['callback']=='audit callback'",["render_chart callback"])

# Upload content validation: direct converter and mock must agree on invalid data.
up_spec={"type":"dataset","label":"Data","target":"work.data","accept":["csv","xlsx","xpt","sas7bdat"],
         "columns":[{"name":"age","type":"numeric"},{"name":"day","type":"date"}]}
upload_cases=[
    ("valid","age,day\n12,2026-01-01\n",True),
    ("missing_column","name,day\nAnn,2026-01-01\n",False),
    ("bad_number","age,day\nnot-a-number,2026-01-01\n",False),
    ("bad_date","age,day\n12,not-a-date\n",False),
    ("literal_na","age,day\n12,NA\n",False),
    ("unpadded","age,day\n12,2026-1-2\n",False),
    ("empty_file","",False),
    ("header_only","age,day\n",True),
    ("blank_missing","age,day\n , \n",True),
    ("quoted_cells",'age,day\n"12","2026-01-01"\n',True),
]
for name,text,valid in upload_cases:
    body={"name":"input.csv","files":[{"name":"input.csv","text":text}],"spec":up_spec}
    for lang in ("python","r"):
        add(f"upload_{name}_{lang}","upload-conversion",
            (f"got=value({lang!r},'upload',{body!r})\nassert got['columns']==['age','day'],got"
             if valid else f"expect_exception({lang!r},'upload',{body!r})"),
            ["read_upload","V014","csv"])
    both("mock_upload_"+name,"mock-content-validation","mock",
         {"data":normal({"data":up_spec}),"files":body["files"],"uploads":{"data":"input.csv"}},
         ("assert got['status']=='success',got" if valid else
          "assert got['status']=='error' and got['metadata']['issues'][0]['code']=='V014',got"),
         ["MockEngine.run","sas_engine_run","V014"])
both("sanitize_duplicate_names","upload-conversion","sanitize",
     {"names":["1 item","x","X","x","x_2","a"*35,"a"*35]},
     f"assert got=={['_1_item','x','X_2','x_3','x_2_2','a'*32,'a'*30+'_2']!r},got",
     ["sanitize_names"])
for fmt in ("csv","xlsx","xpt"):
    args=[table] if fmt=="csv" else [table,"OUT"]
    both("download_"+fmt,"download-formats","collect",{"function":fmt+"_bytes","args":args},
         f"raw=base64.b64decode(got['base64'])\nassert len(raw)>20,got\n"
         +( "assert raw.startswith(b'PK'),raw[:20]" if fmt=="xlsx" else
             "assert b'HEADER RECORD' in raw[:200],raw[:200]" if fmt=="xpt" else
             "assert raw.startswith(b'X,Y,Group\\n'),raw"),[fmt+"_bytes",fmt])
for length in (8,9):
    both("xpt_member_length_"+str(length),"download-formats","collect",
         {"function":"xpt_bytes","args":[table,"A"*length]},
         f"raw=base64.b64decode(got['base64'])\nassert {b'LIBRARY' if length==8 else b'LIBV8'!r} in raw[:100],raw[:100]",
         ["xpt_bytes","XPT v5/v8"])

for case in json.loads((FIX/"collect"/"log_scope.json").read_text())["cases"]:
    both("log_"+case["name"],"collect-fixtures","collect",
         {"function":"scope_log","args":[case["log"],case["scope"]]},
         f"assert got=={case['expected']!r},(language,got)",["scope_log","split_log","log_level"])
plots=json.loads((FIX/"collect"/"plots.json").read_text())
for case in plots["cases"]:
    body={"function":"extract_plots","args":[plots["html"],case["select"]]}
    source=f"body={body!r}\nfor language in ('python','r'):\n"
    if case.get("expected_error"):
        source+="    expect_exception(language,'collect',body)\n"
    else:
        source+=f"    assert value(language,'collect',body)=={case['expected']!r}\n"
    add("plots_"+case["name"],"collect-fixtures",source,["extract_plots"])
k=json.loads((FIX/"collect"/"recording_key.json").read_text())
for fn,exp in [("recording_key_text",k["key_text"]),("recording_key",k["key"])]:
    both(fn,"recording-keys","collect",{"function":fn,"args":[k["contract_sha256"],k["macros"],k["uploads"]]},
         f"assert got=={exp!r},got",[fn])
for ending in ("\n","\r\n","\r"):
    log=ending.join(["NOTE: hi","ERROR: bad","NOTE: SASHINY-END run=audit syscc=0",""])
    both("status_line_end_"+repr(ending),"run-status","status",{"log":log},
         "assert got['status']=='error',got",["run_status","classify_log"])
for code,expect in [(0,"success"),(4,"warning"),(8,"error")]:
    both("status_syscc_"+str(code),"run-status","status",
         {"log":f"NOTE: SASHINY-END run=audit syscc={code}\n"},
         f"assert got['status']=={expect!r},got",["run_status"])
both("status_source_echo_not_sentinel","run-status","status",
     {"log":"1  %put NOTE: SASHINY-END run=audit syscc=0;\n"},
     "assert got['status']=='error',got",["run_status"])
for name in ("reuse","error","raised_engine","validation","idle","factory_error",
             "busy_choices","choices_error","close_reopen"):
    cfg={"max_size":1,"acquire_timeout":0.05}
    if name=="idle": cfg["idle_timeout"]=0.01
    body={"scenario":name,"config":cfg}
    if name=="factory_error":
        # Engine API should report acquisition failures in an error Result.
        check="assert got['results'][0]['status']=='error',got"
    elif name=="close_reopen":
        check="assert got['counts']['created']==1,got"
    elif name=="choices_error":
        check="assert got['sessions_before_close']==0,got"
    elif name=="busy_choices":
        check="assert got['errors'] and all('pool exhausted' in e for e in got['errors']),got"
    elif name in ("error","raised_engine"):
        check="assert got['counts']['created']==2 and got['counts']['closed']==2,got"
    elif name=="idle":
        check="assert got['counts']['created']==2,got"
    else:
        check="assert got['counts']['created']==1,got"
    both("pool_"+name,"pool-lifecycle","pool",body,check,["Pool","sas_pool",name])
for name,timeout in (("parallel",2),("timeout",0.03),("shared_engine",2)):
    body={"scenario":name,"delay":0.12,"config":{"max_size":2,"acquire_timeout":timeout}}
    check=("assert all(r['status']=='success' for r in got['results']),got"
           if name!="timeout" else "assert sum(r['status']=='error' for r in got['results'])==2,got")
    add("pool_"+name,"pool-concurrency",f"got=value('python','pool',{body!r})\n{check}\n"
        "assert not got['errors'],got\nassert got['counts']['peak']<=2,got",["Pool.run",name])

# Real saspy orchestration with a documented fake transport: no invented SAS calculation.
outputs={"stats":{"type":"table","from":"work.stats","columns":["AGE","name"],"max_rows":2},
         "chart":{"type":"chart","from":"work.stats","spec":{"kind":"scatter","x":"age","y":"age"}},
         "missing":{"type":"table","from":"work.nope"},"report":{"type":"html"},
         "graphs":{"type":"plot"},"log":{"type":"log"},
         "csv":{"type":"download","format":"csv","from":"work.stats"},
         "xlsx":{"type":"download","format":"xlsx","from":"work.stats"},
         "xpt":{"type":"download","format":"xpt","from":"work.stats"}}
dataset={"WORK.STATS":{"columns":["age","name"],"rows":[[12,"Ann"],[13,"Ben"],[14,"Chen"]]}}
body={"data":normal(outputs=outputs),"datasets":dataset,"record":True}
both("fake_sas_full_pipeline","engine-orchestration","fake",body,
     "r=got['results'][0]\nassert r['status']=='success',got\n"
     "assert r['outputs']['stats']['rows']==[[12,'Ann'],[13,'Ben']],r\n"
     "assert r['outputs']['stats']['truncated'] is True,r\n"
     "assert 'error' in r['outputs']['missing'],r\n"
     "assert len(r['metadata']['collect_errors'])==1,r\n"
     "assert all(got['closed_after']),got",["SaspyEngine.run","collect all","df2sd","sd2df","record"])
for name in ("slow_factory","slow_submit","raise_submit"):
    body={"data":normal(run={"timeout_seconds":1}),"scenario":name}
    both("fake_sas_"+name,"engine-lifecycle","fake",body,
         "assert got['results'][0]['status']=='error',got\nassert all(got['closed_before']),got",
         ["SaspyEngine.run","timeout","discard","sas_engine_saspy_run"])
for fn in ("mock","runner"):
    both(fn+"_missing_recording","engine-runner",fn,{"by_path":fn=="runner"},
         "assert got['status']=='success',got\nassert got['metadata']['recording']=='missing',got",
         ["MockEngine","run","sas_run"])
rec={"status":"warning","log":"WARNING: synthetic","outputs":{"table":table}}
both("mock_recording_replay","recording","mock",{"recording":rec},
     f"assert got['status']=='warning',got\nassert got['outputs']=={rec['outputs']!r},got",
     ["MockEngine.save_recording","MockEngine.run","sas_engine_record"])
big_table=copy.deepcopy(table); big_table["rows"]=[[9007199254740994,1.2345678901234567,"precise"]]
both("recording_precision","recording","recording",{"recording":{"outputs":{"table":big_table}}},
     f"assert got['loaded']['outputs']['table']['rows']=={big_table['rows']!r},got\n"
     f"assert json.loads(got['result_raw'])['outputs']['table']['rows']=={big_table['rows']!r},got",
     ["save_recording","load_recording","sas_engine_record"])

for name in ("run","status","log","out_report","dl_csv"):
    data=normal({name:{"type":"text","label":"Collision","optional":True}})
    both("ui_internal_id_collision_"+name,"ui-identifiers","ui",{"data":data},
         "from html.parser import HTMLParser\n"
         "class IDs(HTMLParser):\n"
         "    def __init__(self):\n"
         "        super().__init__(); self.ids=[]\n"
         "    def handle_starttag(self,tag,attrs):\n"
         "        self.ids.extend(v for k,v in attrs if k=='id')\n"
         "parser=IDs(); parser.feed(got['html'])\n"
         "assert len(parser.ids)==len(set(parser.ids)),parser.ids",
         ["program_ui","input/output namespaces"])
for layout in ("top","sidebar"):
    both("ui_layout_"+layout,"ui-options","ui",{"data":normal(ui={"layout":layout})},
         "assert 'mod-run' in got['html'] and 'mod-out_report' in got['html'],got",["program_ui",layout])
both("ui_override","ui-options","ui",{"override":True},
     "assert 'audit override' in got['html'] and 'mod-run' not in got['html'],got",["ui_override"])
both("app_single_contract","app","app",{},"assert got['built'],got",["app","sas_app"])
for language in ("python","r"):
    add("app_duplicate_"+language,"app",f"expect_exception({language!r},'app',{{'duplicate':True}},'duplicate')",
        ["app","sas_app","duplicate ids"])
both("module_id_rules","app","module_id",
     {"names":["Cars Explorer.sas","2nd-report.sas","Report.SAS","dir/report.sas","a"*40+".sas"]},
     f"assert got=={['cars_explorer','p_2nd_report','report','report','a'*32]!r},got",["default_module_id"])
for region in ("us1","us2","eu1","ap1","ap2"):
    both("connect_oda_"+region,"connection-configuration","connect",
         {"kwargs":{"profile":"oda","region":region,"java":"/usr/bin/java"}},
         "assert got['iomport']==8591 and got['authkey']=='oda',got",["connect","sas_connect","ODA"])
for kwargs in [
    {"profile":"viya","url":"https://synthetic.invalid","context":"audit"},
    {"profile":"sas94","host":"synthetic.invalid","port":8592,"java":"/usr/bin/java"},
    {"profile":"sas94","host":"synthetic.invalid","saspath":"/synthetic/sas","ssh_user":"audit"},
]:
    both("connect_"+str(kwargs),"connection-configuration","connect",{"kwargs":kwargs},
         "assert got,got",["connect","sas_connect","Viya","IOM","SSH"])
for language in ("python","r"):
    add("connect_unknown_"+language,"connection-configuration",
        f"expect_exception({language!r},'connect',{{'kwargs':{{'profile':'unknown'}}}},'unknown profile')",
        ["connect errors"])
    add("preflight_no_java_"+language,"connection-configuration",
        f"expect_exception({language!r},'preflight',{{'config':{{'iomhost':'synthetic.invalid'}}}},'java')",
        ["preflight","no live credentials"])
both("profiles_read_yaml","connection-configuration","profiles",
     {"yaml":"default: offline\nprofiles:\n  offline:\n    type: mock\n"},
     "assert got['default']=='offline' and got['profiles']['offline']['type']=='mock',got",["load_profiles"])

for name,program,want in [
    ("assigned","%let MSRP = 5; %put &MSRP;",[("L001","/inputs/price")]),
    ("unreferenced","proc print; run;",[("L002","/inputs/price")]),
    ("guarded","%if not %symexist(MSRP) %then %do; %let MSRP=5; %end; %put &MSRP;",[]),
]:
    data=normal({"price":{"type":"numeric","label":"P","macro":"MSRP"}})
    both("lint_"+name,"lint","lint",{"data":data,"program":program},
         f"assert sorted((i['code'],i['path']) for i in got)=={want!r},got",["lint",name])
both("lint_guard_else_override","lint","lint",
     {"data":normal({"price":{"type":"numeric","label":"P","macro":"MSRP"}}),
      "program":"%if not %symexist(MSRP) %then %do; %let MSRP=5; %end;\n%let MSRP=99;\n%put &MSRP;"},
     "assert ('L001','/inputs/price') in [(i['code'],i['path']) for i in got],got",["L001"])

for language in ("python","r"):
    add("installed_inventory_"+language,"dependencies",
        f"got=value({language!r},'inventory',{{}})\nassert all(got['backends'].values()),got\n"
        "assert len(got['versions'])>=10,got",["all declared dependencies","exports","installed artifacts"])

# True HTTP + WebSocket tests run from the separate client VM.
for scenario in ("initial_card","run_success","run_result_error","run_exception","run_coalescing",
                 "disconnect","unavailable_download","available_download","auto_run",
                 "choices_error","run_button_disabled","upload_size"):
    for language in ("python","r"):
        add(f"shiny_{language}_{scenario}","shiny-wire",
            f"from wire import exercise\nexercise({language!r},{scenario!r})",
            ["program_server","HTTP","WebSocket",scenario])

(HERE/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
assert len(manifest)>=100
assert len({m["sha256"] for m in manifest})==len(manifest)
print(json.dumps({"scripts":len(manifest),"categories":sorted({m["category"] for m in manifest})}))
