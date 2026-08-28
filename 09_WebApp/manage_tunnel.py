#!/usr/bin/env python3
"""Install, inspect and repair the Neo -> Shanghai reverse SSH tunnel.

The launch agent owns the long-running ssh process.  This command supplies a
repeatable health contract around it and never reports ONLINE from process
existence alone: both the local backend and the Shanghai tunnel endpoint must
answer /api/health.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
LABEL = "com.gpxterrainlab.reverse-tunnel"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOCAL_HEALTH = "http://127.0.0.1:4174/api/health"
REMOTE_HEALTH_COMMAND = "curl -fsS --max-time 5 http://127.0.0.1:4174/api/health"
PUBLIC_HEALTH = os.getenv("GPX_PUBLIC_HEALTH", "http://124.222.145.225:4173/api/health")
SSH_HOST = os.getenv("GPX_TUNNEL_HOST", "gpx-shanghai-web")


def run(command: list[str], timeout: int = 12) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout)


def http_probe(url: str, timeout: int = 5) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", "replace")
            return {"ok": 200 <= response.status < 300, "status": response.status, "body": body}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def remote_probe() -> dict:
    command = [
        "/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
        SSH_HOST, REMOTE_HEALTH_COMMAND,
    ]
    try:
        result = run(command, timeout=12)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH_TIMEOUT"}
    if result.returncode == 0:
        return {"ok": True, "body": result.stdout.strip()}
    message = (result.stderr + result.stdout).strip()
    auth_markers = ("permission denied", "authentication", "扫码", "qr code")
    reason = "AUTH_REQUIRED" if any(item in message.lower() for item in auth_markers) else "REMOTE_UNREACHABLE"
    return {"ok": False, "error": reason, "detail": message[-800:]}


def launch_state() -> dict:
    uid = os.getuid()
    result = run(["/bin/launchctl", "print", f"gui/{uid}/{LABEL}"])
    if result.returncode != 0:
        return {"loaded": False}
    state = "unknown"
    pid = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("state ="):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid ="):
            pid = stripped.split("=", 1)[1].strip()
    return {"loaded": True, "state": state, "pid": pid}


def diagnosis() -> dict:
    local = http_probe(LOCAL_HEALTH)
    launch = launch_state()
    remote = remote_probe() if local["ok"] else {"ok": False, "error": "LOCAL_BACKEND_OFFLINE"}
    public = http_probe(PUBLIC_HEALTH)
    online = bool(local["ok"] and remote["ok"] and public["ok"])
    if online:
        reason = "ONLINE"
    elif not local["ok"]:
        reason = "LOCAL_BACKEND_OFFLINE"
    elif remote.get("error") == "AUTH_REQUIRED":
        reason = "SSH_AUTH_REQUIRED"
    elif not launch["loaded"]:
        reason = "LAUNCH_AGENT_NOT_INSTALLED"
    else:
        reason = "TUNNEL_DOWN"
    return {"online": online, "reason": reason, "launchd": launch, "local": local, "remote": remote, "public": public}


def plist_payload() -> dict:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    ssh_args = [
        "/usr/bin/ssh", "-NT", "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=20",
        "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=10",
        "-o", "TCPKeepAlive=yes", "-R", "127.0.0.1:4174:127.0.0.1:4174",
        SSH_HOST,
    ]
    return {
        "Label": LABEL,
        "ProgramArguments": ssh_args,
        "RunAtLoad": True,
        "KeepAlive": {"NetworkState": True, "SuccessfulExit": False},
        "ThrottleInterval": 15,
        "ProcessType": "Background",
        "StandardOutPath": str(RUNTIME / "reverse_tunnel.log"),
        "StandardErrorPath": str(RUNTIME / "reverse_tunnel.error.log"),
    }


def install() -> None:
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(plist_payload(), sort_keys=False))
    uid = os.getuid()
    subprocess.run(["/bin/launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
    result = run(["/bin/launchctl", "bootstrap", f"gui/{uid}", str(PLIST)])
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    subprocess.run(["/bin/launchctl", "enable", f"gui/{uid}/{LABEL}"], check=False)
    subprocess.run(["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/{LABEL}"], check=False)
    print(f"INSTALLED={PLIST}")


def repair(wait_seconds: int = 8) -> dict:
    before = diagnosis()
    if not before["local"]["ok"]:
        return {"repaired": False, "action": "START_LOCAL_BACKEND_FIRST", "before": before}
    if not before["launchd"]["loaded"]:
        install()
        action = "INSTALL_AND_START"
    else:
        uid = os.getuid()
        run(["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/{LABEL}"])
        action = "KICKSTART"
    deadline = time.time() + wait_seconds
    after = diagnosis()
    while not after["online"] and time.time() < deadline:
        time.sleep(2)
        after = diagnosis()
    return {"repaired": after["online"], "action": action, "before": before, "after": after}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "install", "repair", "restart", "uninstall"), nargs="?", default="status")
    parser.add_argument("--wait", type=int, default=8)
    args = parser.parse_args()
    if args.action == "status":
        result = diagnosis()
    elif args.action == "install":
        install()
        result = diagnosis()
    elif args.action in {"repair", "restart"}:
        result = repair(args.wait)
    else:
        uid = os.getuid()
        subprocess.run(["/bin/launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
        PLIST.unlink(missing_ok=True)
        result = {"uninstalled": True, "plist": str(PLIST)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get("online") is False:
        raise SystemExit(2)
    if isinstance(result, dict) and "repaired" in result and not result["repaired"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
