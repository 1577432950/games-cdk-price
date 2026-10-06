# -*- coding: utf-8 -*-
"""给页脚声明确认区域截图。"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable
PORT = 8791

p = subprocess.Popen(
    [PY, str(HERE / "web_app.py"), "--port", str(PORT), "--no-browser"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    cwd=str(HERE),
)
time.sleep(3.5)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = None
        for ch in ("msedge", "chrome"):
            try:
                b = pw.chromium.launch(channel=ch)
                break
            except Exception:
                continue
        if b is None:
            b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 900})
        pg.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
        pg.wait_for_timeout(600)
        el = pg.query_selector("footer")
        el.screenshot(path=str(HERE / "assets" / "footer_disclaimer.png"))
        print("title:", pg.title())
        print("footer 文本长度:", len(pg.inner_text("footer")))
        b.close()
finally:
    try:
        import urllib.request
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{PORT}/api/quit", method="POST"),
            timeout=5)
    except Exception:
        pass
    time.sleep(0.5)
    p.terminate()
