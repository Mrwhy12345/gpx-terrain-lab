#!/usr/bin/env python3
"""Static-only frontend server for split local deployment."""
import os
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
WEB_ROOT=Path(__file__).resolve().parent
HOST=os.getenv("GPX_FRONTEND_HOST","127.0.0.1"); PORT=int(os.getenv("GPX_FRONTEND_PORT","4173"))
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(WEB_ROOT),**kwargs)
    def end_headers(self):
        if self.path=="/" or self.path.split("?",1)[0].endswith((".html",".js")):
            self.send_header("Cache-Control","no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()
if __name__=="__main__":
    print(f"GPX Terrain Lab frontend: http://{HOST}:{PORT}/")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
