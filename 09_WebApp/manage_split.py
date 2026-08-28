#!/usr/bin/env python3
"""Start, stop, and inspect the local split frontend/backend deployment."""
from __future__ import annotations
import json, os, signal, socket, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent; LOCAL=ROOT/"local"; RUNTIME=ROOT/"runtime"
PID_FILE=RUNTIME/"split_services.json"
SERVICES={"frontend": (4173, "/"), "backend": (4174, "/api/health")}

def alive(pid):
    try: os.kill(pid,0); return True
    except PermissionError: return True
    except (OSError,ProcessLookupError): return False
def load():
    return json.loads(PID_FILE.read_text()) if PID_FILE.exists() else {}
def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(.25)
        return sock.connect_ex(("127.0.0.1",port)) == 0
def http_ready(port,path):
    try:
        with urlopen(f"http://127.0.0.1:{port}{path}",timeout=1.5) as response:
            return 200 <= response.status < 500
    except Exception:
        return False
def status():
    data=load()
    for name in ("frontend","backend"):
        item=data.get(name,{}); pid=item.get("pid"); port,path=SERVICES[name]
        process_ok=bool(pid and alive(pid)); ready=http_ready(port,path)
        state="READY" if process_ok and ready else "UNHEALTHY" if process_ok or port_open(port) else "STOPPED"
        print(f"{name}: {state}"+(f" pid={pid}" if pid else "")+f" http={port}{path}")
def stop():
    for item in load().values():
        pid=item.get("pid")
        if pid and alive(pid): os.kill(pid,signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True); print("split services stopped")
def start():
    data=load()
    if any(item.get("pid") and alive(item["pid"]) for item in data.values()):
        print("services already running; use status or stop"); return
    occupied=[str(port) for port,_ in SERVICES.values() if port_open(port)]
    if occupied:
        sys.exit("ports already occupied: "+", ".join(occupied)+"; inspect with lsof before restarting")
    RUNTIME.mkdir(exist_ok=True)
    specs={
        "backend":([sys.executable,str(LOCAL/"server.py")],{"GPX_SERVER_ROLE":"backend"}),
        "frontend":([sys.executable,str(LOCAL/"frontend_server.py")],{}),
    }; result={}
    for name,(command,extra_env) in specs.items():
        log=(RUNTIME/f"{name}.log").open("ab")
        process=subprocess.Popen(command,cwd=ROOT,env={**os.environ,**extra_env},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        result[name]={"pid":process.pid,"log":str(RUNTIME/f"{name}.log")}
    PID_FILE.write_text(json.dumps(result,indent=2)+"\n")
    deadline=time.time()+8
    while time.time()<deadline:
        if all(alive(item["pid"]) for item in result.values()) and all(http_ready(*SERVICES[name]) for name in SERVICES):
            status(); return
        time.sleep(.25)
    status()
    for item in result.values():
        if alive(item["pid"]): os.kill(item["pid"],signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    sys.exit("split services failed readiness checks; inspect 09_WebApp/runtime/*.log")

def restart():
    stop(); time.sleep(.5); start()

if __name__=="__main__":
    action=sys.argv[1] if len(sys.argv)>1 else "status"
    {"start":start,"stop":stop,"restart":restart,"status":status}.get(action,lambda:sys.exit("usage: manage_split.py start|stop|restart|status"))()
