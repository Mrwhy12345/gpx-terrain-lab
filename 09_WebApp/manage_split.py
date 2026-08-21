#!/usr/bin/env python3
"""Start, stop, and inspect the local split frontend/backend deployment."""
from __future__ import annotations
import json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent; LOCAL=ROOT/"local"; RUNTIME=ROOT/"runtime"
PID_FILE=RUNTIME/"split_services.json"

def alive(pid):
    try: os.kill(pid,0); return True
    except PermissionError: return True
    except (OSError,ProcessLookupError): return False
def load():
    return json.loads(PID_FILE.read_text()) if PID_FILE.exists() else {}
def status():
    data=load()
    for name in ("frontend","backend"):
        item=data.get(name,{}); pid=item.get("pid"); print(f"{name}: {'RUNNING' if pid and alive(pid) else 'STOPPED'}"+(f" pid={pid}" if pid else ""))
def stop():
    for item in load().values():
        pid=item.get("pid")
        if pid and alive(pid): os.kill(pid,signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True); print("split services stopped")
def start():
    data=load()
    if any(item.get("pid") and alive(item["pid"]) for item in data.values()):
        print("services already running; use status or stop"); return
    RUNTIME.mkdir(exist_ok=True)
    specs={
        "backend":([sys.executable,str(LOCAL/"server.py")],{"GPX_SERVER_ROLE":"backend"}),
        "frontend":([sys.executable,str(LOCAL/"frontend_server.py")],{}),
    }; result={}
    for name,(command,extra_env) in specs.items():
        log=(RUNTIME/f"{name}.log").open("ab")
        process=subprocess.Popen(command,cwd=ROOT,env={**os.environ,**extra_env},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        result[name]={"pid":process.pid,"log":str(RUNTIME/f"{name}.log")}
    PID_FILE.write_text(json.dumps(result,indent=2)+"\n"); time.sleep(.7); status()

def restart():
    stop(); time.sleep(.5); start()

if __name__=="__main__":
    action=sys.argv[1] if len(sys.argv)>1 else "status"
    {"start":start,"stop":stop,"restart":restart,"status":status}.get(action,lambda:sys.exit("usage: manage_split.py start|stop|restart|status"))()
