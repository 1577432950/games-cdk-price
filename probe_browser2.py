# -*- coding: utf-8 -*-
"""对比：Playwright 自带 chromium vs Edge，看是谁连不上"""
from playwright.sync_api import sync_playwright

URLS = [
    ("2Game", "https://www.2game.com/zh-cn/search?q=cyberpunk"),
    ("InstantGaming", "https://www.instant-gaming.com/zh/search/?query=cyberpunk"),
    ("Gamesplanet", "https://us.gamesplanet.com/search?query=cyberpunk"),
]

with sync_playwright() as p:
    for label, launch_kw in [("bundled-chromium", {}), ("msedge", {"channel": "msedge"})]:
        try:
            b = p.chromium.launch(headless=True, args=["--no-sandbox"], **launch_kw)
        except Exception as e:
            print(f"[{label}] 启动失败 {e}")
            continue
        for name, url in URLS:
            pg = b.new_page()
            try:
                r = pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                print(f"[{label}] {name:15s} status={r.status if r else '?'} "
                      f"len={len(pg.content()):>7} title={pg.title()[:40]}")
            except Exception as e:
                print(f"[{label}] {name:15s} ERR {str(e).splitlines()[0][:90]}")
            pg.close()
        b.close()
