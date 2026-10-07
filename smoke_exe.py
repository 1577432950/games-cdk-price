# -*- coding: utf-8 -*-
"""临时冒烟测试：新 exe 起得来、页面正常、匹歪登录态正常、Fanatical 修复生效。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

EXE = r"C:\Users\cat\WorkBuddy AI\2026-10-07-04-20-58\game-cdk-price\dist\游戏CDK比价.exe"
PORT = 8795
BASE = f"http://127.0.0.1:{PORT}"


def api(path, method="GET", timeout=30):
    req = urllib.request.Request(BASE + path, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())


def main():
    tmp = tempfile.mkdtemp(prefix="smoke_")
    proc = subprocess.Popen([EXE, "--no-browser", "--port", str(PORT)],
                            env={**os.environ, "APPDATA": tmp},
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                api("/api/login/status", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        print("[1] 服务就绪, PID =", proc.pid)

        html = api("/")
        print("[2] 首页 %d 字节 | 含登录态脚本: %s | 含 alt 兜底无关"
              % (len(html), "/api/login/check" in html))

        # 用临时 APPDATA，所以这里应报 none（没登录过）
        print("[3] /api/login/check ->", api("/api/login/check"))

        print("[4] 只勾 Fanatical 搜 Hogwarts Legacy …")
        j = post("/api/search", {"cn": "Hogwarts Legacy", "en": "Hogwarts Legacy",
                                 "sites": ["fanatical"], "all": False})
        for _ in range(180):
            d = json.loads(api("/api/job?id=" + j["id"]))
            if d["state"] != "running":
                break
            time.sleep(1)
        print("    state=%s" % d["state"])
        for r in d.get("rows", []):
            print("    %-10s | %-9s | %s" % (r["site"], r["cny"], r["title"][:52]))
    finally:
        try:
            api("/api/quit", "POST", timeout=5)
        except Exception:
            pass
        time.sleep(3)
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    main()
