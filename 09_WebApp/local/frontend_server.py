#!/usr/bin/env python3
"""Static frontend plus optional same-origin proxy for split deployment."""
import os
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
WEB_ROOT=Path(__file__).resolve().parent
HOST=os.getenv("GPX_FRONTEND_HOST","127.0.0.1"); PORT=int(os.getenv("GPX_FRONTEND_PORT","4173"))
UPSTREAM=os.getenv("GPX_UPSTREAM_URL","").rstrip("/")
UPSTREAM_TIMEOUT=int(os.getenv("GPX_UPSTREAM_TIMEOUT","600"))
PROXY_PREFIXES=("/api/","/generated/","/downloads/")
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(WEB_ROOT),**kwargs)
    def end_headers(self):
        if self.path=="/" or self.path.split("?",1)[0].endswith((".html",".js")):
            self.send_header("Cache-Control","no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()
    def is_proxy_request(self):
        path=self.path.split("?",1)[0]
        return bool(UPSTREAM) and any(path.startswith(prefix) for prefix in PROXY_PREFIXES)
    def proxy(self):
        length=int(self.headers.get("Content-Length","0") or 0)
        if length>30_000_000:
            self.send_error(413,"request too large"); return
        body=self.rfile.read(length) if length else None
        headers={key:value for key,value in self.headers.items() if key.lower() in {"content-type","accept"}}
        request=Request(UPSTREAM+self.path,data=body,headers=headers,method=self.command)
        try:
            with urlopen(request,timeout=UPSTREAM_TIMEOUT) as response:
                self.send_response(response.status)
                for key,value in response.headers.items():
                    if key.lower() not in {"connection","transfer-encoding","server","date"}: self.send_header(key,value)
                self.end_headers()
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    self.wfile.write(chunk)
        except HTTPError as error:
            payload=error.read(); self.send_response(error.code)
            self.send_header("Content-Type",error.headers.get("Content-Type","application/json; charset=utf-8")); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
        except (URLError,TimeoutError) as error:
            payload=(f'{{"ok":false,"error":"计算服务暂时不可用：{error.reason if isinstance(error,URLError) else error}"}}').encode()
            self.send_response(502); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        if self.is_proxy_request(): self.proxy()
        else: super().do_GET()
    def do_POST(self):
        if self.is_proxy_request(): self.proxy()
        else: self.send_error(404)
    def do_OPTIONS(self):
        if self.is_proxy_request(): self.proxy()
        else: self.send_response(204); self.end_headers()
if __name__=="__main__":
    mode=f" proxying {UPSTREAM}" if UPSTREAM else " static-only"
    print(f"GPX Terrain Lab frontend: http://{HOST}:{PORT}/ ({mode})")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
