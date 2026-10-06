# -*- coding: utf-8 -*-
"""启动本地服务并截一张界面图（用于 README）"""
import sys
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, ".")
import web_app

port = web_app.free_port()
srv = ThreadingHTTPServer(("127.0.0.1", port), web_app.Handler)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()

from playwright.sync_api import sync_playwright

with sync_playwright() as sp:
    b = sp.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 700}, device_scale_factor=2)
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_timeout(900)
    pg.screenshot(path="assets/ui.png")
    b.close()

srv.shutdown()
print("ok")
