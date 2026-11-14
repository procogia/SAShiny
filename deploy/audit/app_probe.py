from pathlib import Path
import sashiny
from sashiny.upload import file_sha256

root=Path("/tmp/audit")
class Engine(sashiny.MockEngine):
    def run(self,contract,values,**kwargs):
        r=super().run(contract,values,**kwargs)
        r.outputs["report"]=[{"level":"note","text":file_sha256(root/"program.sas")}]
        return r
contracts=[sashiny.Contract({"sashiny":1,"program":"program.sas","id":name,"title":name,
                             "outputs":{"report":{"type":"log"}}},root)
           for name in ("alpha","beta")]
app=sashiny.app(contracts,Engine())
