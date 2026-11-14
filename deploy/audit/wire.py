"""Drive the actual remote Shiny protocol, not an in-process test double."""
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from websockets.sync.client import connect
from client import BASE, CASE, TRACE


class ShinyClient:
    def __init__(self, language):
        self.language=language
        self.url=os.environ["AUDIT_"+language.upper()+"_SHINY"].rstrip("/")
        self.values={}
        self.messages=[]
        self.sid=None
        self.ws=connect(self.url.replace("https:","wss:").replace("http:","ws:")+"/websocket/",
                        open_timeout=20,close_timeout=2)
        self.token=uuid.uuid4().hex
        data={}
        for ns in ("normal","auto","broken","choices","slowchoices"):
            data.update({f"{ns}-run:shiny.action":0,f"{ns}-token":self.token+"-"+ns,
                         f"{ns}-delay":0,f"{ns}-failure":"none",f"{ns}-data":None,
                         f"{ns}-selected":"a"})
            for oid in ("status","log","out_table","out_report","dl_csv"):
                data[f".clientdata_output_{ns}-{oid}_hidden"]=False
        self.ws.send(json.dumps({"method":"init","data":data}))
        self.read_for(2.5)
        assert self.sid, self.messages

    def read_one(self,timeout=0.1):
        try:
            raw=self.ws.recv(timeout=timeout)
        except TimeoutError:
            return None
        message=json.loads(raw)
        self.messages.append(message)
        if "config" in message:
            self.sid=message["config"].get("sessionId")
        self.values.update(message.get("values",{}))
        return message

    def read_for(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.read_one(min(0.2,end-time.monotonic()))

    def update(self,data):
        self.ws.send(json.dumps({"method":"update","data":data}))

    def until(self,predicate,timeout=6):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:
            self.read_one(0.1)
        assert predicate(), self.values

    def run(self,ns="normal",count=1,**kw):
        data={f"{ns}-{k}":v for k,v in kw.items()}
        data[f"{ns}-run:shiny.action"]=count
        self.update(data)

    def close(self):
        self.ws.close()
        (TRACE/f"{CASE}-wire.json").write_text(json.dumps(
            {"url":self.url,"token":self.token,"session_id":self.sid,
             "messages":self.messages},indent=2))


def exercise(language,scenario):
    c=ShinyClient(language)
    try:
        if scenario=="initial_card":
            text=str(c.values.get("normal-out_table",""))
            assert "Running..." not in text,text
        elif scenario=="auto_run":
            c.until(lambda:"status: success" in str(c.values.get("auto-status","")))
        elif scenario=="choices_error":
            assert "could not read choices" in str(c.values.get("broken-status","")),c.values
        elif scenario in ("run_success","available_download"):
            c.run()
            c.until(lambda:"status: success" in str(c.values.get("normal-status","")))
            c.until(lambda:"7" in str(c.values.get("normal-out_table","")))
            if scenario=="available_download":
                res=httpx.get(c.url+f"/session/{c.sid}/download/normal-dl_csv?w=",timeout=15)
                assert res.status_code==200 and res.content==b"value\n7\n",(res.status_code,res.text)
                assert "audit.csv" in res.headers.get("content-disposition",""),res.headers
        elif scenario in ("run_result_error","run_exception"):
            c.run(failure="result" if scenario=="run_result_error" else "raise")
            c.until(lambda:"error" in str(c.values.get("normal-status",""))
                    or bool(c.messages[-1].get("errors")))
            c.read_for(0.3)
            assert "Running..." not in str(c.values.get("normal-out_table","")),c.values
        elif scenario=="run_coalescing":
            c.run(delay=0.9)
            if language=="python":
                c.until(lambda:c.values.get("normal-status")=="running...")
            for n in range(2,7):
                c.run(count=n,delay=0.9)
            c.read_for(6)
            events=httpx.get(BASE+f"/spy-events/{language}",timeout=10).json()
            starts=[e for e in events if e["token"]==c.token+"-normal" and e["event"]=="started"]
            assert len(starts)==1,starts
        elif scenario=="disconnect":
            c.run(delay=1.5)
            if language=="python":
                c.until(lambda:c.values.get("normal-status")=="running...")
            else:
                time.sleep(0.15)
            c.ws.close()
            time.sleep(1.8)
            events=httpx.get(BASE+f"/spy-events/{language}",timeout=10).json()
            finished=[e for e in events if e["token"]==c.token+"-normal" and e["event"]=="completed"]
            assert not finished,finished
        elif scenario=="unavailable_download":
            res=httpx.get(c.url+f"/session/{c.sid}/download/normal-dl_csv?w=",timeout=15)
            assert res.status_code==404,(res.status_code,dict(res.headers),res.text)
        elif scenario=="run_button_disabled":
            from playwright.sync_api import sync_playwright
            # Test the actual browser state, not just the presence of an update message.
            with sync_playwright() as p:
                b=p.chromium.launch(headless=True,args=["--no-sandbox"])
                page=b.new_page()
                page.goto(c.url,wait_until="networkidle",timeout=30000)
                page.locator("#normal-delay").fill("1.5")
                page.locator("#normal-run").click()
                page.wait_for_timeout(100)
                disabled=page.locator("#normal-run").is_disabled()
                b.close()
                assert disabled,"Run button remains enabled while engine is running"
        elif scenario=="upload_size":
            size=160000
            c.ws.send(json.dumps({"method":"uploadInit","args":[[{
                "name":"large.csv","size":size,"type":"text/csv"}]],"tag":100}))
            end=time.monotonic()+5
            response=None
            while time.monotonic()<end:
                msg=c.read_one()
                if msg and "response" in msg:
                    candidate=msg["response"]
                    if candidate.get("tag")==100:
                        response=candidate
                        break
            assert response,response
            if response.get("error"):
                return
            job=response["value"]["jobId"]
            res=httpx.post(c.url+f"/session/{c.sid}/upload/{job}?w=&fileId=0",
                           content=b"age\n"+b"1\n"*((size-4)//2),timeout=20)
            assert res.status_code==413,(res.status_code,"uploaded beyond contract 0.1 MiB limit")
        else:
            raise AssertionError("unknown scenario "+scenario)
    finally:
        c.close()
